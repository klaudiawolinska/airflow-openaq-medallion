"""Unit tests for the OpenAQ v3 client.

Runs entirely offline against fake sessions and virtual time.
"""

from datetime import UTC, datetime, timedelta, timezone

import pytest
import requests

from include.openaq.client import (
    OpenAQClient,
    filter_sensors_by_parameter,
    measurement_identity,
    sensors_from_location,
)
from include.openaq.errors import (
    OpenAQAuthError,
    OpenAQInvalidJSONResponseError,
    OpenAQRateLimitError,
    OpenAQRequestError,
    OpenAQResponseError,
    OpenAQServerError,
    OpenAQTransportError,
)
from include.openaq.ratelimit import SlidingWindowLimiter, Window
from tests.openaq_fakes import (
    FakeClock,
    FakeResponse,
    FakeSession,
    envelope,
    location,
    measurement,
    sensor,
)

WINDOW_FROM = datetime(2026, 7, 1, tzinfo=UTC)
WINDOW_TO = datetime(2026, 7, 2, tzinfo=UTC)


def build_client(responses: list[object], *, page_size: int = 2, **kwargs: object) -> tuple:
    """Build a client wired to test doubles.

    The limiter uses a large budget so rate limiting never affects these tests.
    """
    session = FakeSession(responses)
    clock = FakeClock()
    limiter = SlidingWindowLimiter(
        (Window(max_requests=10**6, seconds=60.0),), clock=clock, sleep=clock.sleep
    )
    client = OpenAQClient(
        "test-key",
        session=session,
        page_size=page_size,
        limiter=limiter,
        sleep=clock.sleep,
        rng=_ConstantRandom(),
        **kwargs,
    )
    return client, session, clock


class _ConstantRandom:
    """Deterministic stand-in for ``random.Random`` — always the top of the range."""

    def uniform(self, low: float, high: float) -> float:
        return high


# --------------------------------------------------------------- pagination


def test_walks_every_page_until_a_short_one() -> None:
    client, session, _ = build_client(
        [
            FakeResponse(json_body=envelope([measurement(utc="2026-07-01T00:00:00Z"),
                                             measurement(utc="2026-07-01T01:00:00Z")])),
            FakeResponse(json_body=envelope([measurement(utc="2026-07-01T02:00:00Z")])),
        ]
    )

    result = client.list_measurements(
        1, datetime_from=WINDOW_FROM, datetime_to=WINDOW_TO
    )

    assert len(result.records) == 3
    assert result.pages_fetched == 2
    assert [call["params"]["page"] for call in session.calls] == [1, 2]


def test_incomplete_last_page_ends_the_walk_without_an_extra_request() -> None:
    """A page shorter than `limit` is the last one — asking again wastes budget."""
    client, session, _ = build_client(
        [FakeResponse(json_body=envelope([measurement(utc="2026-07-01T00:00:00Z")]))]
    )

    result = client.list_measurements(1, datetime_from=WINDOW_FROM, datetime_to=WINDOW_TO)

    assert len(result.records) == 1
    assert len(session.calls) == 1
    assert session.exhausted


def test_empty_first_page_is_a_legitimate_empty_window() -> None:
    """An empty result is a valid response, not an error."""
    client, session, _ = build_client([FakeResponse(json_body=envelope([]))])

    result = client.list_measurements(1, datetime_from=WINDOW_FROM, datetime_to=WINDOW_TO)

    assert result.records == []
    assert result.duplicate_count == 0
    assert len(session.calls) == 1


def test_exactly_full_final_page_triggers_one_confirming_request() -> None:
    """When the last page is exactly `limit` long, only an empty page proves the end."""
    client, session, _ = build_client(
        [
            FakeResponse(json_body=envelope([measurement(utc="2026-07-01T00:00:00Z"),
                                             measurement(utc="2026-07-01T01:00:00Z")])),
            FakeResponse(json_body=envelope([])),
        ]
    )

    result = client.list_measurements(1, datetime_from=WINDOW_FROM, datetime_to=WINDOW_TO)

    assert len(result.records) == 2
    assert len(session.calls) == 2


@pytest.mark.parametrize("found", [">1000", None, 0, "unknown"])
def test_pagination_ignores_meta_found_entirely(found: object) -> None:
    """`meta.found` is typed integer|string|null in the spec, so it is never trusted."""
    client, _, _ = build_client(
        [
            FakeResponse(json_body=envelope([measurement(utc="2026-07-01T00:00:00Z"),
                                             measurement(utc="2026-07-01T01:00:00Z")],
                                            found=found)),
            FakeResponse(json_body=envelope([measurement(utc="2026-07-01T02:00:00Z")],
                                            found=found)),
        ]
    )

    result = client.list_measurements(1, datetime_from=WINDOW_FROM, datetime_to=WINDOW_TO)

    assert len(result.records) == 3


def test_max_pages_guard_stops_a_server_that_never_returns_a_short_page() -> None:
    client, _, _ = build_client(
        [
            FakeResponse(json_body=envelope([measurement(utc=f"2026-07-01T{h:02d}:00:00Z"),
                                             measurement(utc=f"2026-07-01T{h:02d}:30:00Z")]))
            for h in range(5)
        ],
        max_pages=3,
    )

    with pytest.raises(OpenAQResponseError, match="max_pages=3"):
        client.list_measurements(1, datetime_from=WINDOW_FROM, datetime_to=WINDOW_TO)


def test_identical_consecutive_pages_raise_instead_of_looping() -> None:
    """A server ignoring `page` must fail loudly, not spin until max_pages."""
    page = [measurement(utc="2026-07-01T00:00:00Z"), measurement(utc="2026-07-01T01:00:00Z")]
    client, _, _ = build_client(
        [FakeResponse(json_body=envelope(page)), FakeResponse(json_body=envelope(page))]
    )

    with pytest.raises(OpenAQResponseError, match="pagination is not advancing"):
        client.list_measurements(1, datetime_from=WINDOW_FROM, datetime_to=WINDOW_TO)


def test_max_pages_below_one_is_rejected_at_construction() -> None:
    """Otherwise the walk reports exhaustion without having sent a request."""
    with pytest.raises(ValueError, match="max_pages must be"):
        OpenAQClient("k", max_pages=0)


# --------------------------------------------------- duplicates and identity


def test_cross_page_duplicates_are_counted_but_never_dropped() -> None:
    """Duplicate records are counted but preserved."""
    repeated = measurement(utc="2026-07-01T01:00:00Z")
    client, _, _ = build_client(
        [
            FakeResponse(json_body=envelope([measurement(utc="2026-07-01T00:00:00Z"), repeated])),
            FakeResponse(json_body=envelope([repeated])),
        ]
    )

    result = client.list_measurements(1, datetime_from=WINDOW_FROM, datetime_to=WINDOW_TO)

    assert len(result.records) == 3, "duplicates must survive into bronze"
    assert result.duplicate_count == 1
    assert result.duplicate_sample == (("2026-07-01T01:00:00Z", 2),)


def test_duplicates_within_one_page_are_not_counted_as_cross_page_duplicates() -> None:
    repeated = measurement(utc="2026-07-01T01:00:00Z")
    client, _, _ = build_client(
        [FakeResponse(json_body=envelope([repeated, dict(repeated)]))], page_size=3
    )

    result = client.list_measurements(1, datetime_from=WINDOW_FROM, datetime_to=WINDOW_TO)

    assert len(result.records) == 2
    assert result.duplicate_count == 0


def test_same_timestamp_on_a_different_parameter_is_not_a_duplicate() -> None:
    client, _, _ = build_client(
        [
            FakeResponse(
                json_body=envelope(
                    [
                        measurement(utc="2026-07-01T00:00:00Z", parameter="pm25", parameter_id=2),
                        measurement(utc="2026-07-01T00:00:00Z", parameter="pm10", parameter_id=1),
                    ]
                )
            ),
            FakeResponse(json_body=envelope([])),
        ]
    )

    result = client.list_measurements(1, datetime_from=WINDOW_FROM, datetime_to=WINDOW_TO)

    assert result.duplicate_count == 0


def test_records_without_an_identity_key_pass_through_unaccounted() -> None:
    """Two unidentifiable records must not be mistaken for each other."""
    shapeless = measurement(utc="2026-07-01T00:00:00Z")
    shapeless["parameter"] = None
    client, _, _ = build_client(
        [FakeResponse(json_body=envelope([shapeless, dict(shapeless)]))], page_size=5
    )

    result = client.list_measurements(1, datetime_from=WINDOW_FROM, datetime_to=WINDOW_TO)

    assert len(result.records) == 2
    assert result.duplicate_count == 0


def test_measurement_identity_returns_none_without_every_identity_component() -> None:
    assert measurement_identity({"value": 3.0}) is None
    assert measurement_identity({"period": {"datetimeFrom": None}}) is None
    without_parameter_id = {"period": {"datetimeFrom": {"utc": "2026-07-01T00:00:00Z"}}}
    assert measurement_identity(without_parameter_id) is None


def test_records_are_returned_verbatim_for_variant_storage() -> None:
    """No renaming, casting or pruning — bronze lands exactly what arrived."""
    raw = measurement(utc="2026-07-01T00:00:00Z")
    client, _, _ = build_client([FakeResponse(json_body=envelope([raw]))])

    result = client.list_measurements(1, datetime_from=WINDOW_FROM, datetime_to=WINDOW_TO)

    assert result.records[0] == raw


# ------------------------------------------------------------ retry / errors


def test_rate_limit_is_retried_and_then_succeeds() -> None:
    client, session, clock = build_client(
        [
            FakeResponse(status_code=429, text="Too Many Requests"),
            FakeResponse(json_body=envelope([measurement(utc="2026-07-01T00:00:00Z")])),
        ]
    )

    result = client.list_measurements(1, datetime_from=WINDOW_FROM, datetime_to=WINDOW_TO)

    assert len(result.records) == 1
    assert len(session.calls) == 2
    assert clock.total_slept > 0, "a 429 must be followed by a wait"


def test_retry_after_header_overrides_computed_backoff() -> None:
    client, _, clock = build_client(
        [
            FakeResponse(status_code=429, headers={"Retry-After": "17"}),
            FakeResponse(json_body=envelope([])),
        ]
    )

    client.list_measurements(1, datetime_from=WINDOW_FROM, datetime_to=WINDOW_TO)

    assert clock.slept == [17.0]


def test_ratelimit_reset_as_epoch_becomes_a_relative_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    """OpenAQ documents the reset only as 'a timestamp'; an absolute one must not be slept."""
    monkeypatch.setattr("include.openaq.client.time.time", lambda: 1_800_000_000.0)
    client, _, clock = build_client(
        [
            FakeResponse(status_code=429, headers={"x-ratelimit-reset": "1800000025"}),
            FakeResponse(json_body=envelope([])),
        ]
    )

    client.list_measurements(1, datetime_from=WINDOW_FROM, datetime_to=WINDOW_TO)

    assert clock.slept == [25.0]


def test_ratelimit_reset_as_small_number_is_read_as_seconds_remaining() -> None:
    client, _, clock = build_client(
        [
            FakeResponse(status_code=429, headers={"x-ratelimit-reset": "12"}),
            FakeResponse(json_body=envelope([])),
        ]
    )

    client.list_measurements(1, datetime_from=WINDOW_FROM, datetime_to=WINDOW_TO)

    assert clock.slept == [12.0]


def test_server_hint_is_capped_so_a_bad_header_cannot_stall_a_run() -> None:
    client, _, clock = build_client(
        [
            FakeResponse(status_code=429, headers={"Retry-After": "99999"}),
            FakeResponse(json_body=envelope([])),
        ],
        backoff_cap=30.0,
    )

    client.list_measurements(1, datetime_from=WINDOW_FROM, datetime_to=WINDOW_TO)

    assert clock.slept == [30.0]


def test_exhausted_retries_raise_the_underlying_rate_limit_error() -> None:
    client, session, _ = build_client(
        [FakeResponse(status_code=429) for _ in range(3)], max_attempts=3
    )

    with pytest.raises(OpenAQRateLimitError):
        client.list_measurements(1, datetime_from=WINDOW_FROM, datetime_to=WINDOW_TO)

    assert len(session.calls) == 3


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_server_errors_are_retried(status: int) -> None:
    client, session, _ = build_client(
        [
            FakeResponse(status_code=status, text="boom"),
            FakeResponse(json_body=envelope([])),
        ]
    )

    client.list_measurements(1, datetime_from=WINDOW_FROM, datetime_to=WINDOW_TO)

    assert len(session.calls) == 2


def test_persistent_server_error_surfaces_the_status_code() -> None:
    client, _, _ = build_client([FakeResponse(status_code=503) for _ in range(5)], max_attempts=2)

    with pytest.raises(OpenAQServerError) as excinfo:
        client.list_measurements(1, datetime_from=WINDOW_FROM, datetime_to=WINDOW_TO)

    assert excinfo.value.status_code == 503


@pytest.mark.parametrize(
    "exc",
    [
        requests.exceptions.Timeout("read timed out"),
        requests.exceptions.ConnectionError("connection reset"),
    ],
)
def test_transport_failures_are_retried(exc: Exception) -> None:
    client, session, _ = build_client([exc, FakeResponse(json_body=envelope([]))])

    client.list_measurements(1, datetime_from=WINDOW_FROM, datetime_to=WINDOW_TO)

    assert len(session.calls) == 2


def test_persistent_timeout_raises_transport_error() -> None:
    client, _, _ = build_client(
        [requests.exceptions.Timeout("read timed out") for _ in range(4)], max_attempts=2
    )

    with pytest.raises(OpenAQTransportError, match="request failed"):
        client.list_measurements(1, datetime_from=WINDOW_FROM, datetime_to=WINDOW_TO)


@pytest.mark.parametrize("status", [401, 403])
def test_auth_failure_is_not_retried(status: int) -> None:
    """A bad key fails identically on every attempt — retrying only burns budget."""
    client, session, _ = build_client([FakeResponse(status_code=status)] * 4)

    with pytest.raises(OpenAQAuthError):
        client.list_measurements(1, datetime_from=WINDOW_FROM, datetime_to=WINDOW_TO)

    assert len(session.calls) == 1


def test_malformed_query_is_not_retried() -> None:
    """422 means we built the request wrong; the server will refuse it every time."""
    client, session, _ = build_client(
        [FakeResponse(status_code=422, text="invalid datetime")] * 4
    )

    with pytest.raises(OpenAQRequestError) as excinfo:
        client.list_measurements(1, datetime_from=WINDOW_FROM, datetime_to=WINDOW_TO)

    assert excinfo.value.status_code == 422
    assert len(session.calls) == 1


def test_backoff_grows_exponentially_between_attempts() -> None:
    client, _, clock = build_client(
        [FakeResponse(status_code=503) for _ in range(4)],
        max_attempts=4,
        backoff_base=1.0,
        backoff_cap=100.0,
    )

    with pytest.raises(OpenAQServerError):
        client.list_measurements(1, datetime_from=WINDOW_FROM, datetime_to=WINDOW_TO)

    # _ConstantRandom returns the ceiling, so jitter resolves to 1, 2, 4.
    assert clock.slept == [1.0, 2.0, 4.0]


def test_non_json_body_is_retried() -> None:
    client, session, clock = build_client(
        [
            FakeResponse(status_code=200, text="<html>temporary proxy response</html>"),
            FakeResponse(json_body=envelope([])),
        ],
        backoff_base=1.0,
    )

    result = client.list_measurements(1, datetime_from=WINDOW_FROM, datetime_to=WINDOW_TO)

    assert result.records == []
    assert len(session.calls) == 2
    assert clock.slept == [1.0]


def test_non_json_body_raises_a_retryable_response_error_after_final_attempt() -> None:
    client, _, _ = build_client(
        [FakeResponse(status_code=200, text="<html>oops</html>")], max_attempts=1
    )

    with pytest.raises(OpenAQInvalidJSONResponseError, match="not JSON"):
        client.list_measurements(1, datetime_from=WINDOW_FROM, datetime_to=WINDOW_TO)


def test_envelope_without_results_raises() -> None:
    client, _, _ = build_client([FakeResponse(json_body={"meta": {"found": 3}})])

    with pytest.raises(OpenAQResponseError, match="no 'results' key"):
        client.list_measurements(1, datetime_from=WINDOW_FROM, datetime_to=WINDOW_TO)


def test_null_results_is_treated_as_an_empty_page() -> None:
    client, _, _ = build_client([FakeResponse(json_body={"meta": {}, "results": None})])

    result = client.list_measurements(1, datetime_from=WINDOW_FROM, datetime_to=WINDOW_TO)

    assert result.records == []


# ------------------------------------------------------- request construction


def test_api_key_travels_in_the_x_api_key_header() -> None:
    client, session, _ = build_client([FakeResponse(json_body=envelope([]))])

    client.list_measurements(1, datetime_from=WINDOW_FROM, datetime_to=WINDOW_TO)

    assert session.calls[0]["headers"]["X-API-Key"] == "test-key"


def test_api_key_is_never_placed_in_the_query_string() -> None:
    """A key in the URL leaks into logs and proxy history."""
    client, session, _ = build_client([FakeResponse(json_body=envelope([]))])

    client.list_measurements(1, datetime_from=WINDOW_FROM, datetime_to=WINDOW_TO)

    assert "test-key" not in str(session.calls[0]["params"])


def test_empty_api_key_is_rejected_at_construction() -> None:
    with pytest.raises(ValueError, match="api_key must not be empty"):
        OpenAQClient("")


def test_window_bounds_use_the_snake_case_filter_names() -> None:
    client, session, _ = build_client([FakeResponse(json_body=envelope([]))])

    client.list_measurements(7, datetime_from=WINDOW_FROM, datetime_to=WINDOW_TO)

    params = session.calls[0]["params"]
    assert params["datetime_from"].startswith("2026-07-01T00:00:00")
    assert params["datetime_to"].startswith("2026-07-02T00:00:00")
    assert session.calls[0]["url"].endswith("/sensors/7/measurements")


def test_aware_datetimes_are_converted_to_utc() -> None:
    client, session, _ = build_client([FakeResponse(json_body=envelope([]))])
    warsaw_summer = timezone(timedelta(hours=2))

    client.list_measurements(
        1,
        datetime_from=datetime(2026, 7, 1, 12, 0, tzinfo=warsaw_summer),
        datetime_to=WINDOW_TO,
    )

    assert session.calls[0]["params"]["datetime_from"] == "2026-07-01T10:00:00+00:00"


@pytest.mark.parametrize("argument", ["datetime_from", "datetime_to"])
def test_naive_datetimes_are_rejected(argument: str) -> None:
    client, _, _ = build_client([FakeResponse(json_body=envelope([]))])
    bounds = {"datetime_from": WINDOW_FROM, "datetime_to": WINDOW_TO}
    bounds[argument] = datetime(2026, 7, 1, 12, 0)

    with pytest.raises(ValueError, match=f"{argument} must include timezone information"):
        client.list_measurements(1, **bounds)


def test_preformatted_string_bounds_pass_through() -> None:
    client, session, _ = build_client([FakeResponse(json_body=envelope([]))])

    client.list_measurements(
        1, datetime_from="2026-07-01T00:00:00Z", datetime_to="2026-07-02T00:00:00Z"
    )

    assert session.calls[0]["params"]["datetime_from"] == "2026-07-01T00:00:00Z"


@pytest.mark.parametrize("page_size", [0, -1, 1.5, 1001])
def test_invalid_page_size_is_rejected(page_size: int | float) -> None:
    with pytest.raises(ValueError, match="page_size must be"):
        OpenAQClient("k", page_size=page_size)


@pytest.mark.parametrize(("argument", "value"), [("max_attempts", 1.5), ("max_pages", 1.5)])
def test_non_integer_pagination_limits_are_rejected(argument: str, value: float) -> None:
    with pytest.raises(ValueError, match=f"{argument} must be"):
        OpenAQClient("k", **{argument: value})


@pytest.mark.parametrize(
    ("argument", "value"),
    [
        ("timeout", 0.0),
        ("timeout", float("nan")),
        ("backoff_base", -1.0),
        ("backoff_base", float("inf")),
        ("backoff_cap", -1.0),
        ("backoff_cap", float("nan")),
    ],
)
def test_invalid_request_timing_configuration_is_rejected(argument: str, value: float) -> None:
    with pytest.raises(ValueError, match=f"{argument} must be"):
        OpenAQClient("k", **{argument: value})


# ----------------------------------------------------- locations and sensors


def test_locations_are_filtered_to_poland_by_default() -> None:
    client, session, _ = build_client(
        [
            FakeResponse(json_body=envelope([location(location_id=1),
                                             location(location_id=2)])),
            FakeResponse(json_body=envelope([location(location_id=3)])),
        ]
    )

    result = client.list_locations()

    assert [rec["id"] for rec in result.records] == [1, 2, 3]
    assert session.calls[0]["params"]["iso"] == "PL"


def test_duplicate_locations_across_pages_are_detected_by_id() -> None:
    client, _, _ = build_client(
        [
            FakeResponse(json_body=envelope([location(location_id=1), location(location_id=2)])),
            FakeResponse(json_body=envelope([location(location_id=2)])),
        ]
    )

    result = client.list_locations()

    assert result.duplicate_count == 1
    assert result.duplicate_sample == (2,)


def test_sensors_endpoint_is_called_without_pagination_parameters() -> None:
    client, session, _ = build_client(
        [FakeResponse(json_body=envelope([sensor(sensor_id=9, parameter="pm25")]))]
    )

    sensors = client.list_sensors(42)

    assert [s["id"] for s in sensors] == [9]
    assert session.calls[0]["params"] == {}
    assert session.calls[0]["url"].endswith("/locations/42/sensors")


def test_sensor_filter_keeps_only_pollutants_in_scope() -> None:
    """Out-of-scope names here are the ones the live API actually returns."""
    sensors = [
        sensor(sensor_id=1, parameter="pm25"),
        sensor(sensor_id=2, parameter="temperature"),
        sensor(sensor_id=3, parameter="pm10"),
        sensor(sensor_id=4, parameter="relativehumidity"),
        sensor(sensor_id=5, parameter="no2"),
        sensor(sensor_id=6, parameter="um003"),
        sensor(sensor_id=7, parameter="O3"),
        sensor(sensor_id=8, parameter="pm1"),
        sensor(sensor_id=9, parameter="so2"),
        sensor(sensor_id=10, parameter="no"),
        sensor(sensor_id=11, parameter="co"),
        sensor(sensor_id=12, parameter="bc"),
    ]

    kept = filter_sensors_by_parameter(sensors)

    assert [s["id"] for s in kept] == [1, 3, 5, 7, 9, 11, 12], "matching is case-insensitive"


def test_sensor_filter_tolerates_a_malformed_sensor_record() -> None:
    kept = filter_sensors_by_parameter([{"id": 1}, {"id": 2, "parameter": None}])

    assert kept == []


def test_sensors_are_read_inline_from_a_location_record() -> None:
    """The discovery path: /locations embeds sensors, so no request per location."""
    record = location(location_id=28)
    record["sensors"] = [sensor(sensor_id=47, parameter="pm25"),
                         sensor(sensor_id=5001, parameter="no2")]

    assert [s["id"] for s in sensors_from_location(record)] == [47, 5001]


@pytest.mark.parametrize("record", [{}, {"sensors": None}, {"sensors": []}])
def test_location_without_embedded_sensors_yields_an_empty_list(record: dict) -> None:
    assert sensors_from_location(record) == []


def test_embedded_sensors_are_not_aliased_into_the_location_record() -> None:
    """Callers filter the returned list; that must not mutate the source payload."""
    record = location(location_id=28)
    record["sensors"] = [sensor(sensor_id=47, parameter="pm25")]

    sensors_from_location(record).clear()

    assert len(record["sensors"]) == 1
