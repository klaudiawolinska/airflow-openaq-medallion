"""Tests for Snowflake bronze staging and refresh operations."""

import json
from datetime import UTC, datetime

import pytest

from include.openaq.refresh_bronze import (
    REFRESH_STAGED_MEASUREMENTS_SQL,
    STAGING_DELETE_SQL,
    STAGING_INSERT_SQL,
    StagedMeasurement,
    refresh_window,
    stage_measurements,
)
from tests.openaq_fakes import measurement

REFRESH_FROM = datetime(2026, 1, 1, tzinfo=UTC)
REFRESH_TO = datetime(2026, 1, 2, tzinfo=UTC)


class FakeCursor:
    def __init__(self, refresh_result: object | None) -> None:
        """Initialize a fake database cursor with a configurable refresh result and empty execution records."""
        self._refresh_result = refresh_result
        self.executions: list[tuple[str, dict[str, object] | None]] = []
        self.bulk_sql: str | None = None
        self.bulk_rows: list[dict[str, object]] | None = None

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, sql: str, params: dict[str, object] | None = None) -> None:
        """
        Record a SQL statement and its parameters.
        
        Parameters:
        	sql (str): SQL statement to record.
        	params (dict[str, object] | None): Parameters supplied to the statement.
        """
        self.executions.append((sql, params))

    def executemany(self, sql: str, rows: list[dict[str, object]]) -> None:
        """Records a bulk SQL statement and its rows for later inspection.
        
        Parameters:
        	sql (str): SQL statement executed for the bulk operation.
        	rows (list[dict[str, object]]): Rows supplied to the bulk operation.
        """
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
        """Mark the fake connection as committed."""
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
