"""Inspect a few OpenAQ API behaviors required by the client."""


import json
import logging
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .client import OpenAQClient, sensors_from_location
from .errors import OpenAQRequestError

_findings: list[str] = []


def _repository_root() -> Path:
    """Find the repository directory from this module's path."""
    for directory in Path(__file__).resolve().parents:
        if (directory / "pyproject.toml").is_file():
            return directory
    raise RuntimeError("Could not find the repository root")


RECORDED_PAYLOAD_DIR = _repository_root() / "tests" / "fixtures" / "openaq"


def check(assumption: str, holds: bool, detail: str = "") -> bool:
    """Print a check result and save failures for the final summary."""
    suffix = f" — {detail}" if detail else ""
    status = "CONFIRMED" if holds else "MISMATCH "
    print(f"  [{status}] {assumption}{suffix}")
    if not holds:
        _findings.append(f"{assumption}{suffix}")
    return holds


def main() -> int:
    """Run live checks against the OpenAQ API."""
    _findings.clear()
    api_key = os.environ.get("OPENAQ_API_KEY") or os.environ.get("AIRFLOW_VAR_OPENAQ_API_KEY")
    if not api_key or api_key == "your-openaq-api-key":
        print(
            "Set OPENAQ_API_KEY or AIRFLOW_VAR_OPENAQ_API_KEY to a valid API key before "
            "running this script.",
            file=sys.stderr,
        )
        return 2

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    client = OpenAQClient(api_key)

    print("\n=== Locations ===")
    locations = client.list_locations(iso="PL")
    print(
        f"  Fetched {len(locations.records)} locations across {locations.pages_fetched} page(s)."
    )
    print(f"  Cross-page duplicates observed: {locations.duplicate_count}.")
    if not locations.records:
        check("The locations endpoint returned at least one Polish location", False)
        return _summarise()

    print("\n=== Measurements ===")
    probe = _most_recently_active(locations.records) or locations.records[0]
    sensors = sensors_from_location(probe)
    if not sensors:
        check(
            "The selected location includes at least one sensor",
            False,
            f"Location {probe['id']} has no embedded sensors.",
        )
        return _summarise()

    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    window_from, window_to = now - timedelta(days=2), now
    target = sensors[0]
    try:
        measurements = client.list_measurements(
            target["id"], datetime_from=window_from, datetime_to=window_to
        )
    except OpenAQRequestError as exc:
        check(
            "The measurements endpoint accepts datetime_from and datetime_to",
            False,
            f"Sensor {target['id']} returned HTTP {exc.status_code}: {exc}",
        )
        return _summarise()

    check(
        "The measurements endpoint accepts datetime_from and datetime_to",
        measurements.pages_fetched >= 1,
        f"Sensor {target['id']} returned {len(measurements.records)} record(s) across "
        f"{measurements.pages_fetched} page(s).",
    )
    print(f"  Cross-page duplicates observed: {measurements.duplicate_count}.")
    _record_samples(locations.records[:3], sensors[:3], measurements.records[:5])

    return _summarise()


def _most_recently_active(locations: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the location with the latest reported measurement time."""
    dated: list[tuple[datetime, dict[str, Any]]] = []
    for location in locations:
        raw = (location.get("datetimeLast") or {}).get("utc")
        if not isinstance(raw, str) or not raw:
            continue
        try:
            stamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if stamp.utcoffset() is None:
            continue
        dated.append((stamp, location))
    return max(dated, key=lambda pair: pair[0])[1] if dated else None


def _record_samples(
    locations: list[dict[str, Any]],
    sensors: list[dict[str, Any]],
    measurements: list[dict[str, Any]],
) -> None:
    """Save selected live API responses for local inspection."""
    RECORDED_PAYLOAD_DIR.mkdir(parents=True, exist_ok=True)
    for name, payload in (
        ("locations.json", locations),
        ("sensors.json", sensors),
        ("measurements.json", measurements),
    ):
        (RECORDED_PAYLOAD_DIR / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"  Saved sample responses to {RECORDED_PAYLOAD_DIR}.")


def _summarise() -> int:
    """Print the final result and return the process exit code."""
    print("\n" + "=" * 70)
    if _findings:
        print(f"{len(_findings)} live API check(s) failed:")
        for finding in _findings:
            print(f"  - {finding}")
        print("Review the client before relying on the affected behavior.")
        return 1
    print("All live API checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
