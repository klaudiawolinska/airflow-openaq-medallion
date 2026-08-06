"""Tests for Snowflake bronze staging and refresh operations."""

import json
from datetime import UTC, datetime

import pytest

from include.openaq.refresh_bronze import (
    LOAD_SUMMARY_MERGE_SQL,
    LOCATION_STAGING_DELETE_SQL,
    LOCATION_STAGING_INSERT_SQL,
    REFRESH_STAGED_MEASUREMENTS_SQL,
    STAGING_DELETE_SQL,
    STAGING_INSERT_SQL,
    RefreshResult,
    StagedMeasurement,
    record_load_summary,
    refresh_window,
    stage_locations,
    stage_measurements,
)
from tests.openaq_fakes import location, measurement, sensor

REFRESH_FROM = datetime(2026, 1, 1, tzinfo=UTC)
REFRESH_TO = datetime(2026, 1, 2, tzinfo=UTC)


class FakeCursor:
    def __init__(self, refresh_result: object | None) -> None:
        self._refresh_result = refresh_result
        self.executions: list[tuple[str, dict[str, object] | None]] = []
        self.bulk_sql: str | None = None
        self.bulk_rows: list[dict[str, object]] | None = None

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, sql: str, params: dict[str, object] | None = None) -> None:
        self.executions.append((sql, params))

    def executemany(self, sql: str, rows: list[dict[str, object]]) -> None:
        self.bulk_sql = sql
        self.bulk_rows = rows

    def fetchone(self) -> tuple[object, ...] | None:
        return (self._refresh_result,) if self._refresh_result is not None else None


class FakeConnection:
    def __init__(self, refresh_result: object | None) -> None:
        self.cursor_instance = FakeCursor(refresh_result)
        self.committed = False

    def cursor(self) -> FakeCursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.committed = True


def test_staged_measurement_extracts_the_bronze_identity_and_raw_response() -> None:
    raw_measurement = measurement(utc="2026-01-01T01:00:00Z", parameter_id=1, parameter="pm10")

    staged = StagedMeasurement.from_api(11, raw_measurement)

    assert staged.sensor_id == 11
    assert staged.parameter_id == 1
    assert staged.measurement_period_from_utc == "2026-01-01T01:00:00Z"
    assert json.loads(staged.staging_row("load-1")["raw_measurement"]) == raw_measurement


def test_staged_measurement_rejects_a_response_without_a_complete_identity() -> None:
    raw_measurement = measurement(utc="2026-01-01T01:00:00Z")
    raw_measurement["period"]["datetimeFrom"] = {}

    with pytest.raises(ValueError, match="datetimeFrom.utc"):
        StagedMeasurement.from_api(11, raw_measurement)


def test_stage_measurements_replaces_only_the_current_loads_staging_rows() -> None:
    connection = FakeConnection(refresh_result=None)
    staged = StagedMeasurement.from_api(11, measurement(utc="2026-01-01T01:00:00Z"))

    stage_measurements(connection, load_id="load-1", measurements=[staged])

    assert connection.cursor_instance.executions == [
        (STAGING_DELETE_SQL, {"load_id": "load-1"})
    ]
    assert connection.cursor_instance.bulk_sql == STAGING_INSERT_SQL
    assert connection.cursor_instance.bulk_rows is not None
    assert connection.cursor_instance.bulk_rows[0]["load_id"] == "load-1"
    assert connection.committed


def test_stage_locations_replaces_the_loads_staging_rows_with_raw_records() -> None:
    connection = FakeConnection(refresh_result=None)
    raw_location = location(
        location_id=4,
        sensors=[sensor(sensor_id=11, parameter="pm25")],
    )

    stage_locations(connection, load_id="load-1", locations=[raw_location])

    assert connection.cursor_instance.executions == [
        (LOCATION_STAGING_DELETE_SQL, {"load_id": "load-1"})
    ]
    assert connection.cursor_instance.bulk_sql == LOCATION_STAGING_INSERT_SQL
    assert connection.cursor_instance.bulk_rows is not None
    staged = connection.cursor_instance.bulk_rows[0]
    assert staged["load_id"] == "load-1"
    assert json.loads(staged["raw_location"]) == raw_location
    assert connection.committed


def test_refresh_window_returns_the_stored_procedures_changed_data_result() -> None:
    oldest_new = datetime(2026, 1, 1, tzinfo=UTC)
    connection = FakeConnection(
        refresh_result={
            "new_record_count": 2,
            "changed_record_count": 3,
            "absent_record_count": 4,
            "oldest_new_measurement_at": oldest_new,
            "bronze_changed": True,
        }
    )
    diff = refresh_window(
        connection, load_id="load-1", refresh_from=REFRESH_FROM, refresh_to=REFRESH_TO
    )

    assert diff.new_record_count == 2
    assert diff.changed_record_count == 3
    assert diff.absent_record_count == 4
    assert diff.oldest_new_measurement_at == oldest_new
    assert diff.bronze_changed
    assert connection.cursor_instance.executions == [
        (
            REFRESH_STAGED_MEASUREMENTS_SQL,
            {
                "load_id": "load-1",
                "refresh_from": REFRESH_FROM,
                "refresh_to": REFRESH_TO,
            },
        )
    ]


def test_refresh_window_parses_a_serialised_stored_procedure_result() -> None:
    connection = FakeConnection(
        refresh_result=(
            '{"new_record_count":0,"changed_record_count":0,'
            '"absent_record_count":0,"oldest_new_measurement_at":null}'
        )
    )
    diff = refresh_window(
        connection, load_id="load-1", refresh_from=REFRESH_FROM, refresh_to=REFRESH_TO
    )

    assert not diff.bronze_changed
    assert [sql for sql, _ in connection.cursor_instance.executions] == [
        REFRESH_STAGED_MEASUREMENTS_SQL
    ]


def test_refresh_window_rejects_a_missing_stored_procedure_result() -> None:
    connection = FakeConnection(refresh_result=None)

    with pytest.raises(RuntimeError, match="returned no result"):
        refresh_window(
            connection, load_id="load-1", refresh_from=REFRESH_FROM, refresh_to=REFRESH_TO
        )


def test_record_load_summary_upserts_the_refresh_counts() -> None:
    oldest_new = datetime(2026, 1, 1, tzinfo=UTC)
    connection = FakeConnection(refresh_result=None)

    record_load_summary(
        connection,
        load_id="load-1",
        load_type="ingest",
        refresh_from=REFRESH_FROM,
        refresh_to=REFRESH_TO,
        api_record_count=10,
        refresh_result=RefreshResult(
            new_record_count=2,
            changed_record_count=3,
            absent_record_count=4,
            oldest_new_measurement_at=oldest_new,
        ),
    )

    assert connection.cursor_instance.executions == [
        (
            LOAD_SUMMARY_MERGE_SQL,
            {
                "load_id": "load-1",
                "load_type": "ingest",
                "refresh_from": REFRESH_FROM,
                "refresh_to": REFRESH_TO,
                "api_record_count": 10,
                "new_record_count": 2,
                "changed_record_count": 3,
                "absent_record_count": 4,
                "oldest_new_measurement_at": oldest_new,
                "bronze_changed": True,
            },
        )
    ]
    assert connection.committed


def test_refresh_result_has_a_small_json_serialisable_xcom_value() -> None:
    result = RefreshResult(
        new_record_count=1,
        changed_record_count=0,
        absent_record_count=0,
        oldest_new_measurement_at=REFRESH_FROM,
    )

    assert result.xcom_value() == {
        "new_record_count": 1,
        "changed_record_count": 0,
        "absent_record_count": 0,
        "oldest_new_measurement_at": "2026-01-01T00:00:00+00:00",
        "bronze_changed": True,
    }
