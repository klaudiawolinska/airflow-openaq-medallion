"""OpenAQ v3 API client.

The client exposes a small wrapper around the OpenAQ v3 REST API and returns
API responses unchanged as Python dictionaries.

Notes about the API:

* datetime filters are `datetime_from` and `datetime_to`;
* OpenAQ's schema defines `meta.found` as an integer, string or `null`, so
  pagination stops when a page contains fewer records than requested;
* `/locations/{id}/sensors` does not support pagination;
* `/locations` already embeds each location's `sensors` array. Use
  `sensors_from_location()` when discovering sensors and `list_sensors()`
  only when refreshing a single location.
"""

import logging
import math
import random
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import requests

from .errors import (
    OpenAQAuthError,
    OpenAQError,
    OpenAQInvalidJSONResponseError,
    OpenAQRateLimitError,
    OpenAQRequestError,
    OpenAQResponseError,
    OpenAQRetryableError,
    OpenAQServerError,
    OpenAQTransportError,
)
from .ratelimit import OPENAQ_FREE_TIER, SlidingWindowLimiter

log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.openaq.org/v3"

# Maximum page size accepted by the OpenAQ v3 API.
MAX_PAGE_SIZE = 1000

TARGET_PARAMETERS: frozenset[str] = frozenset(
    {"pm25", "pm10", "no2", "o3", "so2", "co", "bc"}
)

# Safety limit for pagination.
DEFAULT_MAX_PAGES = 1000

# Threshold for distinguishing Unix timestamps from time deltas.
_EPOCH_THRESHOLD = 1_000_000_000

# Maximum number of duplicate record keys to include in warning logs.
# Duplicate keys indicate that the same record appeared on multiple pages,
# typically due to unstable pagination.
_MAX_DUPLICATE_SAMPLE = 20


@dataclass(frozen=True)
class FetchResult:
    """Result of a paginated fetch.

    Contains the fetched records together with pagination metadata and
    information about duplicate records detected during the fetch.

    Duplicate records are counted but remain in `records`. This preserves the
    raw API response; deduplication is performed later during the silver merge.
    """

    records: list[dict[str, Any]]
    pages_fetched: int
    duplicate_count: int = 0
    duplicate_sample: tuple[Any, ...] = ()

    def __len__(self) -> int:
        return len(self.records)


# Function returning a record's identity key for duplicate detection.
# Returning None disables duplicate tracking for that record.
type IdentityKey = Callable[[dict[str, Any]], Any]


def _is_finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def location_identity(record: dict[str, Any]) -> Any:
    """Return the location's identity key for duplicate detection."""
    return record.get("id")


def measurement_identity(record: dict[str, Any]) -> Any:
    """Return the identity key for a measurement.

    Measurements are identified by their start time and parameter ID.
    Returns None if no stable identity can be determined.
    """
    period = record.get("period") or {}
    datetime_from = period.get("datetimeFrom") or {}
    started_at = datetime_from.get("utc")
    parameter = record.get("parameter") or {}
    parameter_id = parameter.get("id")
    if started_at is None or parameter_id is None:
        return None
    return (started_at, parameter_id)


def _serialise_datetime(value: datetime | str, *, argument: str) -> str:
    """Convert a datetime to an ISO 8601 UTC string.

    Timezone-aware datetimes are converted to UTC. Strings are returned
    unchanged. Naive datetimes raise ValueError.
    """
    if isinstance(value, str):
        return value
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            f"{argument} must include timezone information; got {value!r}."
        )
    return value.astimezone(UTC).isoformat()


class OpenAQClient:
    """Client for the OpenAQ v3 API.

    Provides methods for fetching locations, sensors and measurements.
    Requests are rate-limited and retried on transient failures.

    Args:
        api_key: OpenAQ API key.
        base_url: Base URL of the OpenAQ API.
        session: Optional requests session.
        timeout: Request timeout in seconds.
        max_attempts: Maximum number of request attempts.
        backoff_base: Initial retry backoff in seconds.
        backoff_cap: Maximum retry backoff in seconds.
        page_size: Number of records requested per page.
        max_pages: Safety limit for pagination.
        limiter: Optional rate limiter.
        sleep: Sleep function used between retries.
        rng: Random number generator used for retry jitter.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        session: requests.Session | None = None,
        timeout: float = 30.0,
        max_attempts: int = 5,
        backoff_base: float = 1.0,
        backoff_cap: float = 60.0,
        page_size: int = MAX_PAGE_SIZE,
        max_pages: int = DEFAULT_MAX_PAGES,
        limiter: SlidingWindowLimiter | None = None,
        sleep: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("api_key must not be empty")
        if (
            isinstance(page_size, bool)
            or not isinstance(page_size, int)
            or not 1 <= page_size <= MAX_PAGE_SIZE
        ):
            raise ValueError(
                f"page_size must be an integer from 1 to {MAX_PAGE_SIZE}, got {page_size!r}"
            )
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or max_attempts < 1:
            raise ValueError(f"max_attempts must be a positive integer, got {max_attempts!r}")
        if isinstance(max_pages, bool) or not isinstance(max_pages, int) or max_pages < 1:
            raise ValueError(f"max_pages must be a positive integer, got {max_pages!r}")
        if not _is_finite_number(timeout) or timeout <= 0:
            raise ValueError(f"timeout must be a positive finite number, got {timeout!r}")
        if not _is_finite_number(backoff_base) or backoff_base < 0:
            raise ValueError(
                f"backoff_base must be a non-negative finite number, got {backoff_base!r}"
            )
        if not _is_finite_number(backoff_cap) or backoff_cap < 0:
            raise ValueError(
                f"backoff_cap must be a non-negative finite number, got {backoff_cap!r}"
            )

        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._session = session if session is not None else requests.Session()
        self._timeout = timeout
        self._max_attempts = max_attempts
        self._backoff_base = backoff_base
        self._backoff_cap = backoff_cap
        self._page_size = page_size
        self._max_pages = max_pages
        self._limiter = limiter if limiter is not None else SlidingWindowLimiter(OPENAQ_FREE_TIER)
        self._sleep = sleep
        self._rng = rng if rng is not None else random.Random()

    # ---------------------------------------------------------------- public

    def list_locations(self, *, iso: str = "PL", **filters: Any) -> FetchResult:
        """Fetch monitoring locations for a country.

        Args:
            iso: ISO 3166-1 alpha-2 country code.
            **filters: Additional OpenAQ query parameters.

        Returns:
            Fetched locations and pagination metadata.
        """
        return self._paginate(
            "/locations",
            params={"iso": iso, **filters},
            identity=location_identity,
        )

    def list_sensors(self, location_id: int) -> list[dict[str, Any]]:
        """Fetch sensors for a location.

        Location records already include their sensors. Use
        `sensors_from_location()` when working with data returned by
        `list_locations()`.

        Args:
            location_id: OpenAQ location ID.

        Returns:
            List of sensors attached to the location.
        """
        payload = self._request(f"/locations/{location_id}/sensors", params={})
        return _extract_results(payload, f"/locations/{location_id}/sensors")

    def list_measurements(
        self,
        sensor_id: int,
        *,
        datetime_from: datetime | str,
        datetime_to: datetime | str,
    ) -> FetchResult:
        """Fetch measurements for a sensor within a time window.

        Args:
            sensor_id: OpenAQ sensor ID.
            datetime_from: Start of the time window as a timezone-aware
            ``datetime`` or an ISO 8601 timestamp.
            datetime_to: End of the time window as a timezone-aware
            ``datetime`` or an ISO 8601 timestamp.

        Returns:
            Measurements and pagination metadata.
        """
        return self._paginate(
            f"/sensors/{sensor_id}/measurements",
            params={
                "datetime_from": _serialise_datetime(datetime_from, argument="datetime_from"),
                "datetime_to": _serialise_datetime(datetime_to, argument="datetime_to"),
            },
            identity=measurement_identity,
        )

    # ------------------------------------------------------------ pagination

    def _paginate(
        self,
        path: str,
        *,
        params: dict[str, Any],
        identity: IdentityKey,
    ) -> FetchResult:
        """Fetch all pages for an endpoint.

        Stops when a short or empty page is returned, detects repeated pages and
        tracks duplicate records across pages.
        """
        records: list[dict[str, Any]] = []
        previous_page_keys: set[Any] = set()
        duplicates: list[Any] = []
        duplicate_count = 0
        previous_results: list[dict[str, Any]] | None = None
        page = 1

        while page <= self._max_pages:
            payload = self._request(
                path, params={**params, "limit": self._page_size, "page": page}
            )
            results = _extract_results(payload, path)

            # An empty page ends pagination.
            if not results:
                break

            if results == previous_results:
                # Consecutive identical pages indicate broken pagination.
                # Abort rather than looping until max_pages.

                # Compare raw records rather than identity keys: records without an
                # identity would otherwise all compare as None.
                raise OpenAQResponseError(
                    f"{path} returned an identical page for page={page - 1} and "
                    f"page={page} ({len(results)} records) — pagination is not "
                    "advancing; refusing to loop."
                )
            previous_results = results

            page_keys = [identity(record) for record in results]
            for record, key in zip(results, page_keys, strict=True):
                if key is not None and key in previous_page_keys:
                    duplicate_count += 1
                    if len(duplicates) < _MAX_DUPLICATE_SAMPLE:
                        duplicates.append(key)
                records.append(record)
            previous_page_keys.update(key for key in page_keys if key is not None)

            # A short page marks the end of the result set.
            # `meta.found` is not guaranteed to be numeric, so it cannot end the walk.
            if len(results) < self._page_size:
                break
            page += 1
        else:
            raise OpenAQResponseError(
                f"{path} still returned full pages after max_pages={self._max_pages}; "
                "refusing to keep paginating. Narrow the window or raise max_pages."
            )

        if duplicate_count:
            log.warning(
                "%s returned %d duplicate record(s) across pages (sample: %s). ",
                path,
                duplicate_count,
                duplicates,
            )

        return FetchResult(
            records=records,
            pages_fetched=page,
            duplicate_count=duplicate_count,
            duplicate_sample=tuple(duplicates),
        )

    # --------------------------------------------------------------- request

    def _request(self, path: str, *, params: dict[str, Any]) -> dict[str, Any]:
        """Execute a single API request.

        Requests are rate-limited, retried on transient failures and returned as the
        decoded OpenAQ v3 JSON envelope."""
        url = f"{self._base_url}{path}"

        for attempt in range(self._max_attempts):
            slept = self._limiter.acquire()
            if slept:
                log.debug("Paced %.2fs before %s to stay inside the rate limit", slept, path)

            # Holds the retryable error that triggered the next retry attempt.
            # Non-retryable errors propagate directly from _decode().
            error: OpenAQRetryableError
            try:
                response = self._session.get(
                    url,
                    params=params,
                    headers={"X-API-Key": self._api_key, "Accept": "application/json"},
                    timeout=self._timeout,
                )
            except requests.exceptions.RequestException as exc:
                # Covers transport failures such as timeouts, connection resets and
                # DNS errors, where no HTTP response is received.
                error = OpenAQTransportError(f"{path} request failed: {exc}")
            else:
                try:
                    return self._decode(response, path)
                except OpenAQRetryableError as exc:
                    error = exc

            # Final attempt: re-raise the original error.
            if attempt == self._max_attempts - 1:
                raise error

            delay = self._backoff_delay(attempt, error)
            log.warning(
                "%s request failed (attempt %d/%d): %s — retrying in %.2fs",
                path,
                attempt + 1,
                self._max_attempts,
                error,
                delay,
            )
            self._sleep(delay)

        # Defensive fallback. The retry loop should always return or raise
        # because max_attempts >= 1 is validated in __init__.
        raise OpenAQError(f"{path}: retry loop exited without a result")

    def _decode(self, response: requests.Response, path: str) -> dict[str, Any]:
        """Decode an HTTP response or raise the appropriate OpenAQ error."""
        status = response.status_code

        if status == 429:
            raise OpenAQRateLimitError(
                f"{path} was rate limited (429). The client paces itself, so this "
                "signals another process sharing the key or a mismatch between "
                "the client and server rate-limit accounting.",
                retry_after=_parse_retry_after(response.headers),
            )
        if status in (401, 403):
            raise OpenAQAuthError(
                f"{path} rejected the API key ({status}). Check the OpenAQ key — "
                "it is missing, malformed or revoked."
            )
        if 500 <= status < 600:
            raise OpenAQServerError(f"{path} returned {status}", status_code=status)
        if 400 <= status < 500:
            # Client errors (including 422) are not retried because the request
            # itself must be fixed.
            raise OpenAQRequestError(
                f"{path} returned {status}: {response.text[:500]}", status_code=status
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise OpenAQInvalidJSONResponseError(
                f"{path} returned {status} with a body that is not JSON: "
                f"{response.text[:200]!r}"
            ) from exc

        if not isinstance(payload, dict):
            raise OpenAQResponseError(
                f"{path} returned JSON of type {type(payload).__name__}, expected the "
                "v3 object envelope with a 'results' key"
            )
        return payload

    def _backoff_delay(self, attempt: int, error: OpenAQRetryableError | None) -> float:
        """Compute the retry delay using full-jitter exponential backoff.

        When the server provides a Retry-After value, it takes precedence over the
        client-side backoff calculation.
        """
        if isinstance(error, OpenAQRateLimitError) and error.retry_after is not None:
            # Prefer the server's retry hint over the client-side backoff calculation.
            return min(error.retry_after, self._backoff_cap)
        ceiling = min(self._backoff_base * (2**attempt), self._backoff_cap)
        return self._rng.uniform(0.0, ceiling)


def _extract_results(payload: dict[str, Any], path: str) -> list[dict[str, Any]]:
    """Return the ``results`` array from an OpenAQ v3 response envelope.

    Treat an explicit ``null`` value as an empty result set.
    """
    results = payload.get("results")
    if results is None:
        if "results" not in payload:
            raise OpenAQResponseError(
                f"{path} response has no 'results' key (keys: {sorted(payload)})"
            )
        return []
    if not isinstance(results, list):
        raise OpenAQResponseError(
            f"{path} returned 'results' of type {type(results).__name__}, expected a list"
        )
    return results


def _parse_retry_after(headers: Any) -> float | None:
    """Parse the server's retry hint, if available.

    Supports both ``Retry-After`` and ``x-ratelimit-reset``. Returns ``None``
    when neither header contains a usable value so the caller can fall back to
    exponential backoff.
    """
    for header in ("Retry-After", "x-ratelimit-reset"):
        raw = headers.get(header)
        if raw is None:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            # RFC 9110 also allows an HTTP-date for Retry-After. OpenAQ has not been
            # observed to return one, so fall back to exponential backoff.
            continue
        # Treat large values as Unix timestamps rather than relative delays.
        if value >= _EPOCH_THRESHOLD:
            value -= time.time()
        if value > 0:
            return value
    return None


def sensors_from_location(location: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the sensors embedded in a ``/locations`` record.

    Use this helper with records returned by ``list_locations()``. A missing or
    ``null`` ``sensors`` field is treated as an empty list.
    """
    return list(location.get("sensors") or [])


def filter_sensors_by_parameter(
    sensors: Iterable[dict[str, Any]],
    parameters: Iterable[str] = TARGET_PARAMETERS,
) -> list[dict[str, Any]]:
    """Keep only sensors measuring the requested pollutants.

    The ``parameters_id`` filter on ``/locations`` selects locations, not
    individual sensors. Matching locations still include all of their sensors,
    so the sensor list is filtered client-side before requesting measurements.
    """
    wanted = {name.lower() for name in parameters}
    return [
        sensor
        for sensor in sensors
        if ((sensor.get("parameter") or {}).get("name") or "").lower() in wanted
    ]
