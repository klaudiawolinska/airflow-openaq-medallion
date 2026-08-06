"""Production collection of OpenAQ measurements for Poland."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from .client import (
    INGEST_PROVIDER_IDS,
    FetchResult,
    filter_sensors_by_parameter,
    sensors_from_location,
)
from .errors import OpenAQServerError
from .refresh_bronze import StagedMeasurement

log = logging.getLogger(__name__)

INGEST_LOOKBACK = timedelta(hours=24)
_PROGRESS_LOG_INTERVAL = 25


class IngestClient(Protocol):
    """OpenAQ operations used by scheduled ingestion."""

    def list_locations(self, *, iso: str = "PL", **filters: object) -> FetchResult: ...

    def list_measurements(
        self,
        sensor_id: int,
        *,
        datetime_from: datetime,
        datetime_to: datetime,
    ) -> FetchResult: ...


@dataclass(frozen=True)
class IngestBatch:
    """Location records, measurements and metrics from one API collection."""

    locations: list[dict[str, object]]
    measurements: list[StagedMeasurement]
    location_count: int
    sensor_count: int
    api_record_count: int
    excluded_record_count: int
    server_error_sensor_count: int


def refresh_window_for_interval(
    data_interval_start: datetime,
    data_interval_end: datetime,
) -> tuple[datetime, datetime]:
    """Return the rolling UTC refresh window anchored to an Airflow data interval."""
    interval_start = _normalise_utc(data_interval_start, argument="data_interval_start")
    interval_end = _normalise_utc(data_interval_end, argument="data_interval_end")
    if interval_start > interval_end:
        raise ValueError("data_interval_start must not be later than data_interval_end")
    refresh_to = interval_end.replace(minute=0, second=0, microsecond=0)
    return refresh_to - INGEST_LOOKBACK, refresh_to


def collect_ingest_batch(
    client: IngestClient,
    *,
    window_started_at: datetime,
    window_ended_at: datetime,
) -> IngestBatch:
    """Collect one location snapshot and measurement window for bronze."""
    window_started_at = _normalise_utc(window_started_at, argument="window_started_at")
    window_ended_at = _normalise_utc(window_ended_at, argument="window_ended_at")
    if window_started_at >= window_ended_at:
        raise ValueError("window_started_at must be earlier than window_ended_at")

    provider_filter = ",".join(str(provider_id) for provider_id in sorted(INGEST_PROVIDER_IDS))
    discovered_locations = client.list_locations(
        iso="PL", providers_id=provider_filter
    ).records
    locations = [
        location
        for location in discovered_locations
        if _provider_id(location) in INGEST_PROVIDER_IDS
    ]
    sensors = [
        sensor
        for location in locations
        for sensor in filter_sensors_by_parameter(sensors_from_location(location))
    ]
    log.info(
        "OpenAQ ingest received %d locations, matched %d production-provider "
        "locations and discovered %d target-parameter sensors for [%s, %s)",
        len(discovered_locations),
        len(locations),
        len(sensors),
        window_started_at.isoformat(),
        window_ended_at.isoformat(),
    )

    staged_measurements: list[StagedMeasurement] = []
    api_record_count = 0
    excluded_record_count = 0
    server_error_sensor_count = 0
    for position, sensor in enumerate(sensors, start=1):
        sensor_id = _integer(sensor.get("id"), argument="sensor.id")
        try:
            result = client.list_measurements(
                sensor_id,
                datetime_from=window_started_at,
                datetime_to=window_ended_at,
            )
        except OpenAQServerError as exc:
            server_error_sensor_count += 1
            log.warning(
                "OpenAQ ingest skipped sensor %d after persistent server error %d: %s",
                sensor_id,
                exc.status_code,
                exc,
            )
        else:
            api_record_count += len(result.records)
            for raw_measurement in result.records:
                measurement = StagedMeasurement.from_api(sensor_id, raw_measurement)
                measured_at = _parse_api_timestamp(
                    measurement.measurement_period_from_utc,
                    argument="measurement period.datetimeFrom.utc",
                )
                if window_started_at <= measured_at < window_ended_at:
                    staged_measurements.append(measurement)
                else:
                    excluded_record_count += 1
        _log_progress(
            completed=position,
            total=len(sensors),
            api_record_count=api_record_count,
            staged_record_count=len(staged_measurements),
            server_error_sensor_count=server_error_sensor_count,
        )

    _reject_duplicate_identities(staged_measurements)
    if excluded_record_count:
        log.warning(
            "OpenAQ ingest excluded %d measurement(s) outside [%s, %s)",
            excluded_record_count,
            window_started_at.isoformat(),
            window_ended_at.isoformat(),
        )
    return IngestBatch(
        locations=discovered_locations,
        measurements=staged_measurements,
        location_count=len(discovered_locations),
        sensor_count=len(sensors),
        api_record_count=api_record_count,
        excluded_record_count=excluded_record_count,
        server_error_sensor_count=server_error_sensor_count,
    )


def _provider_id(location: dict[str, object]) -> object:
    provider = location.get("provider")
    return provider.get("id") if isinstance(provider, dict) else None


def _integer(value: object, *, argument: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{argument} must be an integer")
    return value


def _normalise_utc(value: datetime, *, argument: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{argument} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{argument} must include timezone information")
    # Airflow supplies Pendulum datetimes, whose timedelta arithmetic can drop tzinfo.
    return datetime.fromtimestamp(value.timestamp(), tz=UTC)


def _parse_api_timestamp(value: str, *, argument: str) -> datetime:
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{argument} must be an ISO 8601 timestamp: {value!r}") from exc
    return _normalise_utc(timestamp, argument=argument)


def _reject_duplicate_identities(measurements: list[StagedMeasurement]) -> None:
    identities: set[tuple[int, int, str]] = set()
    for measurement in measurements:
        identity = (
            measurement.sensor_id,
            measurement.parameter_id,
            measurement.measurement_period_from_utc,
        )
        if identity in identities:
            raise ValueError(f"OpenAQ returned duplicate measurement identity {identity!r}")
        identities.add(identity)


def _log_progress(
    *,
    completed: int,
    total: int,
    api_record_count: int,
    staged_record_count: int,
    server_error_sensor_count: int,
) -> None:
    if completed % _PROGRESS_LOG_INTERVAL and completed != total:
        return
    log.info(
        "OpenAQ ingest progress: %d/%d sensors processed; API records=%d accepted=%d "
        "server_errors=%d",
        completed,
        total,
        api_record_count,
        staged_record_count,
        server_error_sensor_count,
    )
