"""Stage measurements and call the Snowflake bronze refresh procedure."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


class Cursor(Protocol):
    """Database cursor operations used by this module."""

    def __enter__(self) -> "Cursor": """Provide the cursor for use within a context manager.

Returns:
    Cursor: The cursor instance.
"""
...

    def __exit__(self, *_: object) -> None: """
Exit the database cursor context.
"""
...

    def execute(self, sql: str, params: dict[str, object] | None = None) -> None: """
Execute a SQL statement with optional named parameters.

Parameters:
	sql (str): SQL statement to execute
	params (dict[str, object] | None): Optional named parameters for the statement
"""
...

    def executemany(self, sql: str, rows: list[dict[str, object]]) -> None: """
Execute a SQL statement for multiple parameter mappings.

Parameters:
	sql (str): The SQL statement to execute.
	rows (list[dict[str, object]]): Parameter mappings for each execution.
"""
...

    def fetchone(self) -> tuple[object, ...] | None: """
Fetch the next row from the current result set.

Returns:
    tuple[object, ...] | None: The next row, or `None` when no row is available.
"""
...


class Connection(Protocol):
    """Database connection operations used by this module."""

    def cursor(self) -> Cursor: """
Provide a cursor for executing database operations.

Returns:
    Cursor: A database cursor.
"""
...

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
) VALUES (
    %(load_id)s,
    %(sensor_id)s,
    %(parameter_id)s,
    %(measurement_period_from_utc)s,
    PARSE_JSON(%(raw_measurement)s)
)
"""

REFRESH_STAGED_MEASUREMENTS_SQL = """
CALL OPENAQ.BRONZE.REFRESH_STAGED_MEASUREMENTS(
    %(load_id)s,
    %(refresh_from)s,
    %(refresh_to)s
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
        """
        Create a staged measurement from an OpenAQ measurement response.
        
        Parameters:
        	sensor_id (int): Sensor identifier associated with the measurement.
        	raw_measurement (dict[str, Any]): Measurement payload containing the parameter identifier and UTC start time.
        
        Returns:
        	StagedMeasurement: Measurement with validated identity fields and the original payload.
        
        Raises:
        	ValueError: If the sensor ID, parameter ID, or UTC start time is invalid or missing.
        """
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
        """
        Parse a Snowflake refresh procedure result into a refresh summary.
        
        Parameters:
            value (object): A mapping or JSON string containing refresh counts and the
                oldest new measurement timestamp.
        
        Returns:
            RefreshResult: The parsed refresh summary.
        
        Raises:
            RuntimeError: If the value is malformed or contains invalid result fields.
        """
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
        """Indicate whether the refresh produced any bronze record changes.
        
        Returns:
            bool: `true` if any records were added, changed, or marked absent, `false` otherwise.
        """
        return any(
            (
                self.new_record_count,
                self.changed_record_count,
                self.absent_record_count,
            )
        )


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
    """
    Reconcile staged measurements within a validated time window.
    
    Parameters:
    	load_id (str): Identifier for the staging load.
    	refresh_from (datetime): Timezone-aware start of the refresh window.
    	refresh_to (datetime): Timezone-aware end of the refresh window.
    
    Returns:
    	RefreshResult: Counts of new, changed, and absent records, plus the oldest new measurement timestamp.
    
    Raises:
    	RuntimeError: If the refresh procedure returns no result.
    	ValueError: If the load ID or refresh window is invalid.
    """
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


def _require_integer(value: object, *, argument: str) -> int:
    """
    Validate and return an integer argument.
    
    Parameters:
        value (object): The value to validate.
        argument (str): The argument name used in the validation error.
    
    Returns:
        int: The validated integer.
    
    Raises:
        ValueError: If `value` is not an integer.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{argument} must be an integer")
    return value


def _require_load_id(load_id: str) -> None:
    """
    Validate that a load identifier is a non-empty string.
    
    Parameters:
    	load_id (str): Load identifier to validate.
    
    Raises:
    	ValueError: If `load_id` is not a string or is empty.
    """
    if not isinstance(load_id, str) or not load_id:
        raise ValueError("load_id must be a non-empty string")


def _validate_refresh_window(refresh_from: datetime, refresh_to: datetime) -> None:
    """
    Validate that a refresh interval uses timezone-aware datetimes and has a positive duration.
    
    Parameters:
    	refresh_from (datetime): Start of the refresh interval.
    	refresh_to (datetime): End of the refresh interval.
    
    Raises:
    	ValueError: If either datetime lacks timezone information or the start is not earlier than the end.
    """
    for argument, value in (("refresh_from", refresh_from), ("refresh_to", refresh_to)):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{argument} must include timezone information")
    if refresh_from >= refresh_to:
        raise ValueError("refresh_from must be earlier than refresh_to")


def _result_integer(value: Mapping[object, object], *, field: str) -> int:
    """
    Extract a required integer field from a Snowflake result mapping.
    
    Parameters:
    	value (Mapping[object, object]): The result mapping to inspect.
    	field (str): The field whose integer value should be returned.
    
    Returns:
    	int: The field value.
    
    Raises:
    	RuntimeError: If the field value is not an integer.
    """
    result = value.get(field)
    if isinstance(result, bool) or not isinstance(result, int):
        raise RuntimeError(f"Snowflake returned an invalid {field}: {result!r}")
    return result


def _result_timestamp(value: object) -> datetime | None:
    """
    Parse an optional Snowflake timestamp result.
    
    Parameters:
    	value (object): A timestamp, ISO-formatted timestamp string, or `None`.
    
    Returns:
    	datetime | None: The parsed timestamp, or `None` when no timestamp is provided.
    
    Raises:
    	RuntimeError: If the value is not a datetime, `None`, or a valid ISO-formatted timestamp string.
    """
    if value is None or isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise RuntimeError(f"Snowflake returned an invalid timestamp: {value!r}")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError(f"Snowflake returned an invalid timestamp: {value!r}") from exc
