"""Test doubles for the OpenAQ client.

Provides fake implementations of the session, clock and response objects used
by the unit tests.
"""


from typing import Any

import requests


class FakeResponse:
    """The slice of ``requests.Response`` that the client actually touches."""

    def __init__(
        self,
        *,
        status_code: int = 200,
        json_body: Any = None,
        text: str = "",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._json_body = json_body
        self.text = text if text else ("" if json_body is None else str(json_body))
        # Match requests.Response by exposing case-insensitive headers.
        self.headers = requests.structures.CaseInsensitiveDict(headers or {})

    def json(self) -> Any:
        if self._json_body is None:
            raise ValueError("no JSON body")
        return self._json_body


class FakeSession:
    """Replay scripted responses and record every request.

    Queued exceptions are raised to simulate transport failures.
    """

    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> FakeResponse:
        self.calls.append(
            {"url": url, "params": params or {}, "headers": headers or {}, "timeout": timeout}
        )
        if not self._responses:
            raise AssertionError(
                f"FakeSession ran out of scripted responses on call "
                f"{len(self.calls)} to {url} with params {params}"
            )
        item = self._responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    @property
    def exhausted(self) -> bool:
        return not self._responses


class FakeClock:
    """Monotonic virtual time: ``sleep`` advances ``now`` without blocking."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds

    @property
    def total_slept(self) -> float:
        return sum(self.slept)


def envelope(results: list[dict[str, Any]], *, found: Any = None, **meta: Any) -> dict[str, Any]:
    """Wrap records in the v3 ``{meta, results}`` envelope."""
    return {
        "meta": {"name": "openaq-api", "website": "/", "found": found, **meta},
        "results": results,
    }


def measurement(
    *, utc: str, value: float = 12.5, parameter_id: int = 2, parameter: str = "pm25"
) -> dict[str, Any]:
    """Return a sample measurement payload.

    Measurements intentionally omit an ``id`` field.
    """
    return {
        "value": value,
        "parameter": {"id": parameter_id, "name": parameter, "units": "µg/m³"},
        "period": {
            "label": "1hour",
            "interval": "01:00:00",
            "datetimeFrom": {"utc": utc, "local": utc},
            "datetimeTo": {"utc": utc, "local": utc},
        },
        "coordinates": None,
        "summary": None,
        "coverage": None,
    }


def location(*, location_id: int, name: str = "Kraków-Aleje") -> dict[str, Any]:
    """Return a sample location payload."""
    return {
        "id": location_id,
        "name": name,
        "country": {"id": 1, "code": "PL", "name": "Poland"},
    }


def sensor(*, sensor_id: int, parameter: str, parameter_id: int = 2) -> dict[str, Any]:
    """Return a sample sensor payload."""
    return {
        "id": sensor_id,
        "name": f"{parameter} sensor",
        "parameter": {"id": parameter_id, "name": parameter, "units": "µg/m³"},
    }
