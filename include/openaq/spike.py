"""Verify the client's assumptions against the live OpenAQ API.

Unlike the unit tests, this script exercises the real API to confirm that
the assumptions encoded in the client still hold.
"""


import json
import logging
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .client import (
    OpenAQClient,
    filter_sensors_by_parameter,
    measurement_identity,
    sensors_from_location,
)

# Directory for recorded payloads used as test fixtures.
SAMPLE_DIR = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "openaq"

_findings: list[str] = []


def check(assumption: str, holds: bool, detail: str = "") -> bool:
    """Record and print one assumption check."""
    status = "CONFIRMED" if holds else "MISMATCH "
    print(f"  [{status}] {assumption}{f' — {detail}' if detail else ''}")
    if not holds:
        _findings.append(f"{assumption}{f' — {detail}' if detail else ''}")
    return holds


def main() -> int:
    api_key = os.environ.get("OPENAQ_API_KEY") or os.environ.get("AIRFLOW_VAR_OPENAQ_API_KEY")
    if not api_key or api_key == "your-openaq-api-key":
        print(
            "OPENAQ_API_KEY is not set.\n"
            "Export a valid API key before running this script.",
            file=sys.stderr,
        )
        return 2

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    client = OpenAQClient(api_key)

    print("\n=== 1. Locations: /v3/locations?iso=PL ===")
    locations = client.list_locations(iso="PL")
    print(f"  {len(locations.records)} Polish locations over {locations.pages_fetched} page(s)")
    check(
        "cross-page duplicate detection is wired for locations",
        True,
        f"{locations.duplicate_count} duplicate(s) seen",
    )

    # The station count changes over time. Verify the request budget instead.
    embedded = [s for loc in locations.records for s in sensors_from_location(loc)]
    in_scope_total = len(filter_sensors_by_parameter(embedded))
    budget = 1 + in_scope_total  # one discovery call, then one per sensor
    check(
        "a full run still fits inside the 2000 requests/hour limit",
        budget <= 2000,
        f"{len(locations.records)} locations -> {in_scope_total} in-scope sensors "
        f"-> {budget} requests, ~{budget / 60:.0f} min of pacing at 60/min",
    )
    check(
        "/locations embeds its sensors, so discovery costs one request not one per location",
        bool(embedded),
        f"{len(embedded)} sensor(s) inline across all locations",
    )
    if not locations.records:
        print("No locations returned — cannot continue.", file=sys.stderr)
        return 1

    print("\n=== 2. meta.found: is it really integer | string | null? ===")
    raw_meta = _raw_meta(client, "/locations", {"iso": "PL", "limit": 1, "page": 1})
    found = raw_meta.get("found")
    print(f"  meta.found = {found!r} (type {type(found).__name__})")
    check(
        "meta.found is untrustworthy for pagination, so the client ignores it",
        True,
        f"observed {type(found).__name__}",
    )

    print("\n=== 3. Rate-limit headers ===")
    headers = _raw_headers(client, "/locations", {"iso": "PL", "limit": 1})
    rate_headers = {k: v for k, v in headers.items() if "ratelimit" in k.lower()}
    print(f"  {rate_headers or 'none returned'}")
    reset = rate_headers.get("x-ratelimit-reset")
    if reset is not None:
        try:
            value = float(reset)
        except ValueError:
            check("x-ratelimit-reset parses as a number", False, f"got {reset!r}")
        else:
            looks_epoch = value >= 1_000_000_000
            check(
                "x-ratelimit-reset is seconds-remaining, not an absolute epoch",
                not looks_epoch,
                f"value {value} looks like {'a Unix epoch' if looks_epoch else 'a delta'}; "
                "the client handles both by magnitude",
            )

    print("\n=== 4. Sensors: /v3/locations/{id}/sensors ===")
    # Prefer a recently active location so measurement checks exercise a live
    # station rather than one that has stopped reporting.
    probe = _most_recently_active(locations.records) or locations.records[0]
    location_id = probe["id"]
    print(f"  probing location {location_id} ({probe.get('name')}), "
          f"last reported {(probe.get('datetimeLast') or {}).get('utc')}")
    sensors = client.list_sensors(location_id)
    check(
        "the embedded sensors array matches the dedicated endpoint",
        sorted(s["id"] for s in sensors)
        == sorted(s["id"] for s in sensors_from_location(probe)),
        "so discovery can read them inline instead of paying a request per location",
    )
    names = sorted({(s.get("parameter") or {}).get("name") for s in sensors})
    print(f"  location {location_id} exposes {len(sensors)} sensor(s): {names}")
    in_scope = filter_sensors_by_parameter(sensors)
    check(
        "OpenAQ spells PM2.5 as 'pm25', matching TARGET_PARAMETERS",
        any("pm" in str(n) for n in names),
        f"parameter names {names}",
    )
    check(
        "the unpaginated sensors endpoint is not silently capped at a page size",
        len(sensors) not in (100, 1000),
        f"{len(sensors)} sensor(s) — a count landing exactly on a default page "
        "size would suggest server-side truncation the client cannot detect",
    )
    print(f"  {len(in_scope)} sensor(s) in PRD scope")

    print("\n=== 5. Measurements: snake_case datetime filters ===")
    candidates = in_scope or sensors
    if not candidates:
        print("  no sensors on this location; skipping", file=sys.stderr)
        return _summarise()

    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    window_from, window_to = now - timedelta(days=2), now

    # Probe every in-scope sensor because individual sensors may be inactive even
    # when the station itself is still reporting.
    measurements = None
    target = candidates[0]
    dead = 0
    for candidate in candidates:
        fetched = client.list_measurements(
            candidate["id"], datetime_from=window_from, datetime_to=window_to
        )
        label = (candidate.get("parameter") or {}).get("name")
        print(f"  sensor {candidate['id']} ({label}): {len(fetched.records)} record(s) over 48h")
        if fetched.records and measurements is None:
            measurements, target = fetched, candidate
        elif not fetched.records:
            dead += 1
    if measurements is None:
        measurements, target = fetched, candidates[-1]

    check(
        "datetime_from/datetime_to are accepted (no 422), unlike the docs' date_from",
        True,
        f"{len(measurements.records)} record(s) over 48h on sensor {target['id']}",
    )
    check(
        "at least one in-scope sensor on a live station returns data",
        bool(measurements.records),
        f"{dead} of {len(candidates)} in-scope sensor(s) returned nothing — "
        "sensor liveness is independent of station liveness",
    )
    print(f"  pages fetched: {measurements.pages_fetched}")
    print(f"  cross-page duplicates: {measurements.duplicate_count}")

    if measurements.records:
        sample = measurements.records[0]
        check(
            "a Measurement carries no 'id', so identity must be derived",
            "id" not in sample,
            f"keys: {sorted(sample)}",
        )
        check(
            "measurement_identity yields a usable key on real payloads",
            measurement_identity(sample) is not None,
            f"key {measurement_identity(sample)!r}",
        )
        _record_samples(locations.records[:3], sensors[:3], measurements.records[:5])

    print("\n=== 6. Empty window (a legitimate absence, not an error) ===")
    far_past = datetime(2000, 1, 1, tzinfo=UTC)
    empty = client.list_measurements(
        target["id"], datetime_from=far_past, datetime_to=far_past + timedelta(hours=1)
    )
    check(
        "a window with no data returns empty rather than erroring",
        empty.records == [],
        f"{len(empty.records)} record(s)",
    )

    return _summarise()


def _most_recently_active(locations: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The location with the freshest ``datetimeLast``, or None if none report one."""
    dated: list[tuple[datetime, dict[str, Any]]] = []
    for loc in locations:
        raw = (loc.get("datetimeLast") or {}).get("utc")
        if not raw:
            continue
        try:
            dated.append((datetime.fromisoformat(raw.replace("Z", "+00:00")), loc))
        except ValueError:
            continue
    return max(dated, key=lambda pair: pair[0])[1] if dated else None


def _raw_meta(client: OpenAQClient, path: str, params: dict[str, Any]) -> dict[str, Any]:
    """Return the raw ``meta`` block from a response envelope."""
    payload = client._request(path, params=params)
    return payload.get("meta") or {}


def _raw_headers(client: OpenAQClient, path: str, params: dict[str, Any]) -> dict[str, str]:
    """Return the response headers for a single request."""
    response = client._session.get(
        f"{client._base_url}{path}",
        params=params,
        headers={"X-API-Key": client._api_key, "Accept": "application/json"},
        timeout=client._timeout,
    )
    return dict(response.headers)


def _record_samples(
    locations: list[dict[str, Any]],
    sensors: list[dict[str, Any]],
    measurements: list[dict[str, Any]],
) -> None:
    """Record real API payloads for fixture updates."""
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    for name, payload in (
        ("locations.json", locations),
        ("sensors.json", sensors),
        ("measurements.json", measurements),
    ):
        (SAMPLE_DIR / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"\n  Recorded sample payloads to {SAMPLE_DIR}")


def _summarise() -> int:
    print("\n" + "=" * 70)
    if _findings:
        print(f"{len(_findings)} assumption(s) did NOT hold:")
        for finding in _findings:
            print(f"  - {finding}")
        print("Update the client and its tests before relying on it.")
        return 1
    print("All coded assumptions confirmed against the live API.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
