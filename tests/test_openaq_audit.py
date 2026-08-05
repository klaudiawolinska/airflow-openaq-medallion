"""Offline tests for the OpenAQ source audit."""

import logging
from datetime import UTC, datetime

import pytest

from include.openaq.audit import SensorAuditResult, audit_sensors, parse_audit_window
from include.openaq.client import FetchResult
from include.openaq.errors import OpenAQServerError
from tests.openaq_fakes import location, measurement, sensor

WINDOW_STARTED_AT = datetime(2026, 1, 1, tzinfo=UTC)
WINDOW_ENDED_AT = datetime(2026, 1, 2, tzinfo=UTC)


class FakeAuditClient:
    """Returns scripted measurement results for the sensors discovered by an audit."""

    def __init__(
        self,
        locations: list[dict],
        measurements: dict[int, FetchResult | Exception],
    ) -> None:
        self._locations = locations
        self._measurements = measurements
        self.measurement_calls: list[tuple[int, datetime, datetime]] = []

    def list_locations(self, *, iso: str = "PL") -> FetchResult:
        assert iso == "PL"
        return FetchResult(records=self._locations, pages_fetched=1)

    def list_measurements(
        self,
        sensor_id: int,
        *,
        datetime_from: datetime,
        datetime_to: datetime,
    ) -> FetchResult:
        self.measurement_calls.append((sensor_id, datetime_from, datetime_to))
        response = self._measurements[sensor_id]
        if isinstance(response, Exception):
            raise response
        return response


def test_audit_records_data_and_source_metadata(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="include.openaq.audit")
    target_sensor = sensor(sensor_id=11, parameter="pm25", parameter_id=2)
    ignored_sensor = sensor(sensor_id=12, parameter="pm1", parameter_id=19)
    client = FakeAuditClient(
        [
            location(
                location_id=4,
                name="Warszawa",
                provider_id=99,
                provider_name="Example provider",
                sensors=[target_sensor, ignored_sensor],
            )
        ],
        {
            11: FetchResult(
                records=[
                    measurement(utc="2026-01-01T04:00:00Z"),
                    measurement(utc="2026-01-01T01:00:00Z"),
                ],
                pages_fetched=1,
            )
        },
    )

    results = audit_sensors(
        client,
        window_started_at=WINDOW_STARTED_AT,
        window_ended_at=WINDOW_ENDED_AT,
    )

    assert len(results) == 1
    result = results[0]
    assert result.audit_result == "data"
    assert result.record_count == 2
    assert result.oldest_measurement_at == "2026-01-01T01:00:00Z"
    assert result.newest_measurement_at == "2026-01-01T04:00:00Z"
    assert (result.provider_id, result.provider_name) == (99, "Example provider")
    assert (result.location_id, result.location_name) == (4, "Warszawa")
    assert (result.sensor_id, result.parameter_id, result.parameter_name) == (11, 2, "pm25")
    assert client.measurement_calls == [(11, WINDOW_STARTED_AT, WINDOW_ENDED_AT)]
    assert "discovered 1 locations and 1 target-parameter sensors" in caplog.text
    assert "progress: 1/1 sensors complete; data=1 empty=0 error=0" in caplog.text


def test_audit_records_empty_response() -> None:
    client = FakeAuditClient(
        [location(location_id=4, sensors=[sensor(sensor_id=11, parameter="pm25")])],
        {11: FetchResult(records=[], pages_fetched=1)},
    )

    result = audit_sensors(
        client,
        window_started_at=WINDOW_STARTED_AT,
        window_ended_at=WINDOW_ENDED_AT,
    )[0]

    assert result.audit_result == "empty"
    assert result.record_count == 0
    assert result.oldest_measurement_at is None
    assert result.newest_measurement_at is None
    assert result.error_detail is None


def test_audit_records_error_and_continues_with_later_sensors() -> None:
    first_sensor = sensor(sensor_id=11, parameter="pm25")
    second_sensor = sensor(sensor_id=12, parameter="pm10", parameter_id=1)
    client = FakeAuditClient(
        [location(location_id=4, sensors=[first_sensor, second_sensor])],
        {
            11: OpenAQServerError("service unavailable", status_code=503),
            12: FetchResult(
                records=[measurement(utc="2026-01-01T01:00:00Z", parameter_id=1)],
                pages_fetched=1,
            ),
        },
    )

    results = audit_sensors(
        client,
        window_started_at=WINDOW_STARTED_AT,
        window_ended_at=WINDOW_ENDED_AT,
    )

    assert [result.audit_result for result in results] == ["error", "data"]
    assert results[0].error_detail == "service unavailable"
    assert [call[0] for call in client.measurement_calls] == [11, 12]


@pytest.mark.parametrize(
    ("window_from", "window_to"),
    [
        (None, "2026-01-02T00:00:00Z"),
        ("2026-01-01T00:00:00", "2026-01-02T00:00:00Z"),
        ("2026-01-02T00:00:00Z", "2026-01-01T00:00:00Z"),
    ],
)
def test_manual_audit_window_requires_a_positive_timezone_aware_range(
    window_from: object, window_to: object
) -> None:
    with pytest.raises(ValueError):
        parse_audit_window(window_from, window_to)


def test_manual_audit_window_is_normalised_to_utc() -> None:
    window_started_at, window_ended_at = parse_audit_window(
        "2026-01-01T01:00:00+01:00", "2026-01-02T00:00:00Z"
    )

    assert window_started_at == datetime(2026, 1, 1, tzinfo=UTC)
    assert window_ended_at == WINDOW_ENDED_AT


def test_audit_dag_writes_every_result_to_snowflake(monkeypatch: pytest.MonkeyPatch) -> None:
    from dags import openaq_audit

    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    hook = FakeHook(connection)

    def build_hook(*, snowflake_conn_id: str) -> FakeHook:
        hook.snowflake_conn_id = snowflake_conn_id
        return hook

    monkeypatch.setattr(openaq_audit, "SnowflakeHook", build_hook)
    result = SensorAuditResult(
        provider_id=99,
        provider_name="Example provider",
        location_id=4,
        location_name="Warszawa",
        sensor_id=11,
        sensor_name="pm25 sensor",
        parameter_id=2,
        parameter_name="pm25",
        audit_result="data",
        record_count=1,
        oldest_measurement_at="2026-01-01T01:00:00Z",
        newest_measurement_at="2026-01-01T01:00:00Z",
        error_detail=None,
    )

    openaq_audit._insert_audit_results(
        audit_id="manual__2026-01-02",
        window_started_at=WINDOW_STARTED_AT,
        window_ended_at=WINDOW_ENDED_AT,
        results=[result],
    )

    assert hook.snowflake_conn_id == "snowflake_default"
    assert cursor.sql == openaq_audit.AUDIT_INSERT_SQL
    assert cursor.rows == [
        {
            "audit_id": "manual__2026-01-02",
            "window_started_at": WINDOW_STARTED_AT,
            "window_ended_at": WINDOW_ENDED_AT,
            "provider_id": 99,
            "provider_name": "Example provider",
            "location_id": 4,
            "location_name": "Warszawa",
            "sensor_id": 11,
            "sensor_name": "pm25 sensor",
            "parameter_id": 2,
            "parameter_name": "pm25",
            "audit_result": "data",
            "record_count": 1,
            "oldest_measurement_at": "2026-01-01T01:00:00Z",
            "newest_measurement_at": "2026-01-01T01:00:00Z",
            "error_detail": None,
        }
    ]
    assert connection.committed
    assert connection.closed


class FakeCursor:
    """Records one bulk insert issued by the audit DAG."""

    def __init__(self) -> None:
        self.sql: str | None = None
        self.rows: list[dict] | None = None

    def __enter__(self):
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def executemany(self, sql: str, rows: list[dict]) -> None:
        self.sql = sql
        self.rows = rows


class FakeConnection:
    """Records the transaction boundaries used by the audit DAG."""

    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor
        self.committed = False
        self.closed = False

    def cursor(self) -> FakeCursor:
        return self._cursor

    def commit(self) -> None:
        self.committed = True

    def close(self) -> None:
        self.closed = True


class FakeHook:
    """Returns the connection recorded by the audit DAG test."""

    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection
        self.snowflake_conn_id: str | None = None

    def get_conn(self) -> FakeConnection:
        return self._connection
