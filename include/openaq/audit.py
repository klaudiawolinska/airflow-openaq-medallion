"""Source audit for the currently discoverable OpenAQ sensors in Poland."""

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol

from .client import FetchResult, filter_sensors_by_parameter, sensors_from_location
from .errors import OpenAQError

AuditResultType = Literal["data", "empty", "error"]

log = logging.getLogger(__name__)
_PROGRESS_LOG_INTERVAL = 25


class AuditClient(Protocol):
    """OpenAQ operations used by the source audit."""

    def list_locations(self, *, iso: str = "PL") -> FetchResult: ...

    def list_measurements(
        self,
        sensor_id: int,
        *,
        datetime_from: datetime,
        datetime_to: datetime,
    ) -> FetchResult: ...


@dataclass(frozen=True)
class SensorAuditResult:
    """The result of auditing one sensor over one requested window."""

    provider_id: int | None
    provider_name: str | None
    location_id: int
    location_name: str | None
    sensor_id: int
    sensor_name: str | None
    parameter_id: int
    parameter_name: str
    audit_result: AuditResultType
    record_count: int
    oldest_measurement_at: str | None
    newest_measurement_at: str | None
    error_detail: str | None


def parse_audit_window(window_from: object, window_to: object) -> tuple[datetime, datetime]:
    """Parse and validate the manual audit window as UTC datetimes."""
    started_at = _parse_timestamp(window_from, argument="from")
    ended_at = _parse_timestamp(window_to, argument="to")
    if started_at >= ended_at:
        raise ValueError("from must be earlier than to")
    return started_at, ended_at


def audit_sensors(
    client: AuditClient,
    *,
    window_started_at: datetime,
    window_ended_at: datetime,
) -> list[SensorAuditResult]:
    """Audit every target-parameter sensor found in Poland."""
    _validate_window(window_started_at, window_ended_at)
    results: list[SensorAuditResult] = []
    locations = client.list_locations(iso="PL").records
    sensors = [
        (location, sensor)
        for location in locations
        for sensor in filter_sensors_by_parameter(sensors_from_location(location))
    ]
    log.info(
        "OpenAQ audit discovered %d locations and %d target-parameter sensors",
        len(locations),
        len(sensors),
    )

    for position, (location, sensor) in enumerate(sensors, start=1):
        provider = location.get("provider") or {}
        location_id = location["id"]
        location_name = location.get("name")

        parameter = sensor["parameter"]
        sensor_id = sensor["id"]
        try:
            measurements = client.list_measurements(
                sensor_id,
                datetime_from=window_started_at,
                datetime_to=window_ended_at,
            ).records
        except OpenAQError as exc:
            results.append(
                SensorAuditResult(
                    provider_id=provider.get("id"),
                    provider_name=provider.get("name"),
                    location_id=location_id,
                    location_name=location_name,
                    sensor_id=sensor_id,
                    sensor_name=sensor.get("name"),
                    parameter_id=parameter["id"],
                    parameter_name=parameter["name"],
                    audit_result="error",
                    record_count=0,
                    oldest_measurement_at=None,
                    newest_measurement_at=None,
                    error_detail=str(exc),
                )
            )
        else:
            measurement_times = sorted(_measurement_ended_at(measurements))
            results.append(
                SensorAuditResult(
                    provider_id=provider.get("id"),
                    provider_name=provider.get("name"),
                    location_id=location_id,
                    location_name=location_name,
                    sensor_id=sensor_id,
                    sensor_name=sensor.get("name"),
                    parameter_id=parameter["id"],
                    parameter_name=parameter["name"],
                    audit_result="data" if measurements else "empty",
                    record_count=len(measurements),
                    oldest_measurement_at=measurement_times[0] if measurement_times else None,
                    newest_measurement_at=measurement_times[-1] if measurement_times else None,
                    error_detail=None,
                )
            )
        _log_progress(position, len(sensors), results)

    return results


def _log_progress(completed: int, total: int, results: list[SensorAuditResult]) -> None:
    if completed % _PROGRESS_LOG_INTERVAL and completed != total:
        return
    result_counts = {
        result_type: sum(result.audit_result == result_type for result in results)
        for result_type in ("data", "empty", "error")
    }
    log.info(
        "OpenAQ audit progress: %d/%d sensors complete; data=%d empty=%d error=%d",
        completed,
        total,
        result_counts["data"],
        result_counts["empty"],
        result_counts["error"],
    )


def _parse_timestamp(value: object, *, argument: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{argument} must be a non-empty ISO 8601 timestamp")

    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{argument} must be an ISO 8601 timestamp: {value!r}") from exc

    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError(f"{argument} must include timezone information")
    return timestamp.astimezone(UTC)


def _validate_window(window_started_at: datetime, window_ended_at: datetime) -> None:
    bounds = (
        ("window_started_at", window_started_at),
        ("window_ended_at", window_ended_at),
    )
    for argument, value in bounds:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{argument} must include timezone information")
    if window_started_at >= window_ended_at:
        raise ValueError("window_started_at must be earlier than window_ended_at")


def _measurement_ended_at(measurements: Iterable[dict[str, object]]) -> Iterable[str]:
    for measurement in measurements:
        period = measurement.get("period")
        if not isinstance(period, dict):
            continue
        datetime_to = period.get("datetimeTo")
        if not isinstance(datetime_to, dict):
            continue
        utc = datetime_to.get("utc")
        if isinstance(utc, str) and utc:
            yield utc
