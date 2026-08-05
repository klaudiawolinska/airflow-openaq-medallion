"""Offline tests for production OpenAQ ingestion."""

import logging
from datetime import UTC, datetime

import pendulum
import pytest

from include.openaq.client import FetchResult
from include.openaq.errors import OpenAQServerError
from include.openaq.ingest import collect_measurements, refresh_window_for_interval
from tests.openaq_fakes import location, measurement, sensor

WINDOW_STARTED_AT = datetime(2026, 1, 1, tzinfo=UTC)
WINDOW_ENDED_AT = datetime(2026, 1, 2, tzinfo=UTC)


class FakeIngestClient:
    """Returns scripted locations and measurements for an ingest window."""

    def __init__(
        self,
        locations: list[dict],
        measurements: dict[int, FetchResult | BaseException],
    ) -> None:
        self._locations = locations
        self._measurements = measurements
        self.location_calls: list[tuple[str, object]] = []
        self.measurement_calls: list[tuple[int, datetime, datetime]] = []

    def list_locations(self, *, iso: str = "PL", **filters: object) -> FetchResult:
        self.location_calls.append((iso, filters.get("providers_id")))
        return FetchResult(records=self._locations, pages_fetched=1)

    def list_measurements(
        self,
        sensor_id: int,
        *,
        datetime_from: datetime,
        datetime_to: datetime,
    ) -> FetchResult:
        self.measurement_calls.append((sensor_id, datetime_from, datetime_to))
        result = self._measurements[sensor_id]
        if isinstance(result, BaseException):
            raise result
        return result


def test_collect_measurements_limits_discovery_and_fetches_target_sensors(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="include.openaq.ingest")
    included_sensor = sensor(sensor_id=11, parameter="pm25", parameter_id=2)
    ignored_parameter = sensor(sensor_id=12, parameter="pm1", parameter_id=19)
    ignored_provider_sensor = sensor(sensor_id=13, parameter="pm10", parameter_id=1)
    client = FakeIngestClient(
        [
            location(
                location_id=4,
                provider_id=66,
                provider_name="AirGradient",
                sensors=[included_sensor, ignored_parameter],
            ),
            location(
                location_id=5,
                provider_id=999,
                provider_name="Unexpected provider",
                sensors=[ignored_provider_sensor],
            ),
        ],
        {
            11: FetchResult(
                records=[measurement(utc="2026-01-01T01:00:00Z")],
                pages_fetched=1,
            )
        },
    )

    batch = collect_measurements(
        client,
        window_started_at=WINDOW_STARTED_AT,
        window_ended_at=WINDOW_ENDED_AT,
    )

    assert client.location_calls == [("PL", "66,70")]
    assert client.measurement_calls == [(11, WINDOW_STARTED_AT, WINDOW_ENDED_AT)]
    assert (batch.location_count, batch.sensor_count, batch.api_record_count) == (1, 1, 1)
    assert len(batch.measurements) == 1
    assert batch.measurements[0].sensor_id == 11
    assert batch.server_error_sensor_count == 0
    assert "progress: 1/1 sensors processed; API records=1 accepted=1" in caplog.text


def test_collect_measurements_enforces_the_half_open_window() -> None:
    client = FakeIngestClient(
        [
            location(
                location_id=4,
                provider_id=70,
                sensors=[sensor(sensor_id=11, parameter="pm25")],
            )
        ],
        {
            11: FetchResult(
                records=[
                    measurement(utc="2025-12-31T23:00:00Z"),
                    measurement(utc="2026-01-01T00:00:00Z"),
                    measurement(utc="2026-01-01T23:00:00Z"),
                    measurement(utc="2026-01-02T00:00:00Z"),
                ],
                pages_fetched=1,
            )
        },
    )

    batch = collect_measurements(
        client,
        window_started_at=WINDOW_STARTED_AT,
        window_ended_at=WINDOW_ENDED_AT,
    )

    assert batch.api_record_count == 4
    assert batch.excluded_record_count == 2
    assert [
        staged.measurement_period_from_utc for staged in batch.measurements
    ] == ["2026-01-01T00:00:00Z", "2026-01-01T23:00:00Z"]


def test_collect_measurements_rejects_duplicate_bronze_identities() -> None:
    duplicate = measurement(utc="2026-01-01T01:00:00Z")
    client = FakeIngestClient(
        [
            location(
                location_id=4,
                provider_id=66,
                sensors=[sensor(sensor_id=11, parameter="pm25")],
            )
        ],
        {11: FetchResult(records=[duplicate, duplicate], pages_fetched=2)},
    )

    with pytest.raises(ValueError, match="duplicate measurement identity"):
        collect_measurements(
            client,
            window_started_at=WINDOW_STARTED_AT,
            window_ended_at=WINDOW_ENDED_AT,
        )


def test_collect_measurements_logs_a_server_error_and_continues_with_other_sensors(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="include.openaq.ingest")
    client = FakeIngestClient(
        [
            location(
                location_id=4,
                provider_id=66,
                sensors=[
                    sensor(sensor_id=11, parameter="pm25"),
                    sensor(sensor_id=12, parameter="pm10", parameter_id=1),
                ],
            )
        ],
        {
            11: OpenAQServerError("/sensors/11/measurements returned 500", status_code=500),
            12: FetchResult(
                records=[measurement(utc="2026-01-01T01:00:00Z", parameter_id=1)],
                pages_fetched=1,
            ),
        },
    )

    batch = collect_measurements(
        client,
        window_started_at=WINDOW_STARTED_AT,
        window_ended_at=WINDOW_ENDED_AT,
    )

    assert [call[0] for call in client.measurement_calls] == [11, 12]
    assert [measurement.sensor_id for measurement in batch.measurements] == [12]
    assert batch.api_record_count == 1
    assert batch.server_error_sensor_count == 1
    assert "skipped sensor 11 after persistent server error 500" in caplog.text
    assert (
        "progress: 2/2 sensors processed; API records=1 accepted=1 server_errors=1"
        in caplog.text
    )


def test_refresh_window_is_a_utc_lookback_anchored_to_the_data_interval() -> None:
    refresh_from, refresh_to = refresh_window_for_interval(
        datetime.fromisoformat("2026-01-02T00:00:00+01:00"),
        datetime.fromisoformat("2026-01-02T01:00:00+01:00"),
    )

    assert refresh_from == datetime(2026, 1, 1, tzinfo=UTC)
    assert refresh_to == datetime(2026, 1, 2, tzinfo=UTC)


def test_refresh_window_floors_a_manual_interval_to_the_utc_hour() -> None:
    refresh_from, refresh_to = refresh_window_for_interval(
        datetime.fromisoformat("2026-01-02T00:37:42.123456+01:00"),
        datetime.fromisoformat("2026-01-02T01:37:42.123456+01:00"),
    )

    assert refresh_from == datetime(2026, 1, 1, tzinfo=UTC)
    assert refresh_to == datetime(2026, 1, 2, tzinfo=UTC)


def test_refresh_window_preserves_timezone_for_airflow_pendulum_interval() -> None:
    refresh_from, refresh_to = refresh_window_for_interval(
        pendulum.datetime(2026, 1, 2, tz="Europe/Warsaw"),
        pendulum.datetime(2026, 1, 2, 1, tz="Europe/Warsaw"),
    )

    assert type(refresh_from) is datetime
    assert type(refresh_to) is datetime
    assert refresh_from == datetime(2026, 1, 1, tzinfo=UTC)
    assert refresh_to == datetime(2026, 1, 2, tzinfo=UTC)


def test_refresh_window_rejects_a_naive_data_interval() -> None:
    with pytest.raises(ValueError, match="timezone"):
        refresh_window_for_interval(
            datetime(2026, 1, 1),
            WINDOW_ENDED_AT,
        )


def test_ingest_dag_has_the_required_three_task_chain() -> None:
    from dags.openaq_ingest import openaq_ingest

    dag = openaq_ingest()

    assert dag.schedule == "@hourly"
    assert set(dag.task_dict) == {
        "fetch_api_and_stage",
        "refresh_bronze",
        "record_summary_and_emit_asset",
    }
    assert dag.get_task("fetch_api_and_stage").downstream_task_ids == {
        "refresh_bronze"
    }
    assert dag.get_task("refresh_bronze").downstream_task_ids == {
        "record_summary_and_emit_asset"
    }
    assert dag.get_task("fetch_api_and_stage").retries == 0
    assert dag.get_task("refresh_bronze").retries == 0
