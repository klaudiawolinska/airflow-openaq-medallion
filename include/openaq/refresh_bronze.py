"""Stage measurements and call the Snowflake bronze refresh procedure."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


class Cursor(Protocol):
    """Database cursor operations used by this module."""

    def __enter__(self) -> "Cursor": ...

    def __exit__(self, *_: object) -> None: ...

    def execute(self, sql: str, params: dict[str, object] | None = None) -> None: ...

    def executemany(self, sql: str, rows: list[dict[str, object]]) -> None: ...

    def fetchone(self) -> tuple[object, ...] | None: ...


class Connection(Protocol):
    """Database connection operations used by this module."""

    def cursor(self) -> Cursor: ...

    def commit(self) -> None: ...


STAGING_DELETE_SQL = """
DELETE FROM OPENAQ.BRONZE.MEASUREMENT_STAGING
WHERE LOAD_ID = %(load_id)s
"""

STAGING_INSERT_SQL = """
INSERT INTO OPENAQ.BRONZE.MEASUREMENT_STAGING (
    LOAD_ID,
    SENSOR_ID,
    PARAMETER_ID,
    MEASUREMENT_PERIOD_FROM_UTC,
    RAW_MEASUREMENT
)
SELECT
    column1,
    column2,
    column3,
    column4,
    PARSE_JSON(column5)
FROM VALUES (
    %(load_id)s,
    %(sensor_id)s,
    %(parameter_id)s,
    %(measurement_period_from_utc)s,
    %(raw_measurement)s
)
"""

REFRESH_STAGED_MEASUREMENTS_SQL = """
CALL OPENAQ.BRONZE.REFRESH_STAGED_MEASUREMENTS(
    %(load_id)s,
    %(refresh_from)s,
    %(refresh_to)s
)
"""

LOAD_SUMMARY_MERGE_SQL = """
MERGE INTO OPENAQ.BRONZE.LOAD_SUMMARY AS target
USING (
    SELECT
        %(load_id)s AS LOAD_ID,
        %(load_type)s AS LOAD_TYPE,
        %(refresh_from)s AS REFRESH_FROM_UTC,
        %(refresh_to)s AS REFRESH_TO_UTC,
        %(api_record_count)s AS API_RECORD_COUNT,
        %(new_record_count)s AS NEW_RECORD_COUNT,
        %(changed_record_count)s AS CHANGED_RECORD_COUNT,
        %(absent_record_count)s AS ABSENT_RECORD_COUNT,
        %(oldest_new_measurement_at)s AS OLDEST_NEW_MEASUREMENT_AT,
        %(bronze_changed)s AS BRONZE_CHANGED
) AS source
ON target.LOAD_ID = source.LOAD_ID
WHEN MATCHED THEN UPDATE SET
    LOAD_TYPE = source.LOAD_TYPE,
    REFRESH_FROM_UTC = source.REFRESH_FROM_UTC,
    REFRESH_TO_UTC = source.REFRESH_TO_UTC,
    API_RECORD_COUNT = source.API_RECORD_COUNT,
    NEW_RECORD_COUNT = source.NEW_RECORD_COUNT,
    CHANGED_RECORD_COUNT = source.CHANGED_RECORD_COUNT,
    ABSENT_RECORD_COUNT = source.ABSENT_RECORD_COUNT,
    OLDEST_NEW_MEASUREMENT_AT = source.OLDEST_NEW_MEASUREMENT_AT,
    BRONZE_CHANGED = source.BRONZE_CHANGED,
    COMPLETED_AT = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN INSERT (
    LOAD_ID,
    LOAD_TYPE,
    REFRESH_FROM_UTC,
    REFRESH_TO_UTC,
    API_RECORD_COUNT,
    NEW_RECORD_COUNT,
    CHANGED_RECORD_COUNT,
    ABSENT_RECORD_COUNT,
    OLDEST_NEW_MEASUREMENT_AT,
    BRONZE_CHANGED
) VALUES (
    source.LOAD_ID,
    source.LOAD_TYPE,
    source.REFRESH_FROM_UTC,
    source.REFRESH_TO_UTC,
    source.API_RECORD_COUNT,
    source.NEW_RECORD_COUNT,
    source.CHANGED_RECORD_COUNT,
    source.ABSENT_RECORD_COUNT,
    source.OLDEST_NEW_MEASUREMENT_AT,
    source.BRONZE_CHANGED
)
"""


@dataclass(frozen=True)
class StagedMeasurement:
    """One API measurement prepared for the shared Snowflake staging table."""

    sensor_id: int
    parameter_id: int
    measurement_period_from_utc: str
    raw_measurement: dict[str, Any]

    @classmethod
    def from_api(cls, sensor_id: int, raw_measurement: dict[str, Any]) -> "StagedMeasurement":
        """Extract the bronze identity fields from an OpenAQ measurement response."""
        parameter = raw_measurement.get("parameter")
        period = raw_measurement.get("period")
        datetime_from = period.get("datetimeFrom") if isinstance(period, dict) else None
        started_at = datetime_from.get("utc") if isinstance(datetime_from, dict) else None
        if not isinstance(started_at, str) or not started_at:
            raise ValueError("measurement period.datetimeFrom.utc must be a non-empty string")
        return cls(
            sensor_id=_require_integer(sensor_id, argument="sensor_id"),
            parameter_id=_require_integer(
                parameter.get("id") if isinstance(parameter, dict) else None,
                argument="measurement parameter.id",
            ),
            measurement_period_from_utc=started_at,
            raw_measurement=raw_measurement,
        )

    def staging_row(self, load_id: str) -> dict[str, object]:
        """Return Snowflake bind values for this measurement."""
        return {
            "load_id": load_id,
            "sensor_id": self.sensor_id,
            "parameter_id": self.parameter_id,
            "measurement_period_from_utc": self.measurement_period_from_utc,
            "raw_measurement": json.dumps(
                self.raw_measurement, separators=(",", ":"), sort_keys=True
            ),
        }


@dataclass(frozen=True)
class RefreshResult:
    """Counts returned by the bronze refresh procedure."""

    new_record_count: int
    changed_record_count: int
    absent_record_count: int
    oldest_new_measurement_at: datetime | None

    @classmethod
    def from_snowflake(cls, value: object) -> "RefreshResult":
        """Build a diff from the object returned by the refresh procedure."""
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"Snowflake returned an invalid refresh result: {value!r}"
                ) from exc
        if not isinstance(value, Mapping):
            raise RuntimeError(f"Snowflake returned an invalid refresh result: {value!r}")
        return cls(
            new_record_count=_result_integer(value, field="new_record_count"),
            changed_record_count=_result_integer(value, field="changed_record_count"),
            absent_record_count=_result_integer(value, field="absent_record_count"),
            oldest_new_measurement_at=_result_timestamp(
                value.get("oldest_new_measurement_at")
            ),
        )

    @property
    def bronze_changed(self) -> bool:
        return any(
            (
                self.new_record_count,
                self.changed_record_count,
                self.absent_record_count,
            )
        )

    def xcom_value(self) -> dict[str, object]:
        """Return a JSON-serialisable representation for task hand-off."""
        oldest_new_measurement_at = self.oldest_new_measurement_at
        return {
            "new_record_count": self.new_record_count,
            "changed_record_count": self.changed_record_count,
            "absent_record_count": self.absent_record_count,
            "oldest_new_measurement_at": (
                oldest_new_measurement_at.isoformat()
                if oldest_new_measurement_at is not None
                else None
            ),
            "bronze_changed": self.bronze_changed,
        }


def stage_measurements(
    connection: Connection, *, load_id: str, measurements: list[StagedMeasurement]
) -> None:
    """Replace the staged rows associated with one load ID."""
    _require_load_id(load_id)
    with connection.cursor() as cursor:
        cursor.execute(STAGING_DELETE_SQL, {"load_id": load_id})
        if measurements:
            cursor.executemany(
                STAGING_INSERT_SQL,
                [measurement.staging_row(load_id) for measurement in measurements],
            )
    connection.commit()


def refresh_window(
    connection: Connection,
    *,
    load_id: str,
    refresh_from: datetime,
    refresh_to: datetime,
) -> RefreshResult:
    """Call the procedure that atomically reconciles one staged time window."""
    _require_load_id(load_id)
    _validate_refresh_window(refresh_from, refresh_to)
    parameters = {
        "load_id": load_id,
        "refresh_from": refresh_from,
        "refresh_to": refresh_to,
    }
    with connection.cursor() as cursor:
        cursor.execute(REFRESH_STAGED_MEASUREMENTS_SQL, parameters)
        row = cursor.fetchone()
    if row is None:
        raise RuntimeError("Snowflake refresh procedure returned no result")
    return RefreshResult.from_snowflake(row[0])


def record_load_summary(
    connection: Connection,
    *,
    load_id: str,
    load_type: str,
    refresh_from: datetime,
    refresh_to: datetime,
    api_record_count: int,
    refresh_result: RefreshResult,
) -> None:
    """Upsert the durable summary for one completed bronze refresh."""
    _require_load_id(load_id)
    if not isinstance(load_type, str) or not load_type:
        raise ValueError("load_type must be a non-empty string")
    _validate_refresh_window(refresh_from, refresh_to)
    _require_non_negative_integer(api_record_count, argument="api_record_count")
    parameters = {
        "load_id": load_id,
        "load_type": load_type,
        "refresh_from": refresh_from,
        "refresh_to": refresh_to,
        "api_record_count": api_record_count,
        "new_record_count": refresh_result.new_record_count,
        "changed_record_count": refresh_result.changed_record_count,
        "absent_record_count": refresh_result.absent_record_count,
        "oldest_new_measurement_at": refresh_result.oldest_new_measurement_at,
        "bronze_changed": refresh_result.bronze_changed,
    }
    with connection.cursor() as cursor:
        cursor.execute(LOAD_SUMMARY_MERGE_SQL, parameters)
    connection.commit()


def _require_integer(value: object, *, argument: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{argument} must be an integer")
    return value


def _require_non_negative_integer(value: object, *, argument: str) -> int:
    result = _require_integer(value, argument=argument)
    if result < 0:
        raise ValueError(f"{argument} must not be negative")
    return result


def _require_load_id(load_id: str) -> None:
    if not isinstance(load_id, str) or not load_id:
        raise ValueError("load_id must be a non-empty string")


def _validate_refresh_window(refresh_from: datetime, refresh_to: datetime) -> None:
    for argument, value in (("refresh_from", refresh_from), ("refresh_to", refresh_to)):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{argument} must include timezone information")
    if refresh_from >= refresh_to:
        raise ValueError("refresh_from must be earlier than refresh_to")


def _result_integer(value: Mapping[object, object], *, field: str) -> int:
    result = value.get(field)
    if isinstance(result, bool) or not isinstance(result, int):
        raise RuntimeError(f"Snowflake returned an invalid {field}: {result!r}")
    return result


def _result_timestamp(value: object) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise RuntimeError(f"Snowflake returned an invalid timestamp: {value!r}")
    try:
        return datetime.fromisoformat(value.replace(" Z", "+00:00").replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError(f"Snowflake returned an invalid timestamp: {value!r}") from exc
