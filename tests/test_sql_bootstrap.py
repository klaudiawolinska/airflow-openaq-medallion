"""Static idempotency checks for Snowflake bootstrap SQL."""

import re
from pathlib import Path

import pytest

BOOTSTRAP_DIR = Path(__file__).resolve().parent.parent / "include" / "sql" / "bootstrap"

PROVISION_SCRIPTS = sorted(BOOTSTRAP_DIR.glob("[0-8][0-9]_*.sql"))

CREATE_OR_REPLACE_STATEFUL = re.compile(
    r"create\s+or\s+replace\s+(?:transient\s+)?"
    r"(database|schema|warehouse|user|table)\b",
    re.IGNORECASE,
)

CREATE_STATEFUL_UNGUARDED = re.compile(
    r"^\s*create\s+(?:transient\s+)?(database|schema|warehouse|user|role|table)\b"
    r"(?!\s+if\s+not\s+exists)",
    re.IGNORECASE,
)


def _statements(sql: str) -> list[str]:
    without_comments = re.sub(r"--[^\n]*", "", sql)
    return [s.strip() for s in without_comments.split(";") if s.strip()]


def test_provision_scripts_present() -> None:
    names = [p.name for p in PROVISION_SCRIPTS]
    for prefix in ("00_", "01_", "02_", "03_", "04_"):
        assert any(n.startswith(prefix) for n in names), (
            f"Missing bootstrap script {prefix}*.sql; found {names}"
        )


def test_bronze_tables_are_provisioned() -> None:
    sql = (BOOTSTRAP_DIR / "04_bronze_tables.sql").read_text()

    for table in ("MEASUREMENTS", "SENSOR_AUDIT_RESULTS", "LOAD_SUMMARY"):
        assert re.search(
            rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+OPENAQ\.BRONZE\.{table}\b",
            sql,
            re.IGNORECASE,
        ), f"04_bronze_tables.sql must provision OPENAQ.BRONZE.{table}"


def test_bronze_time_and_change_columns_are_documented() -> None:
    sql = (BOOTSTRAP_DIR / "04_bronze_tables.sql").read_text()

    for table, column in (
        ("MEASUREMENTS", "MEASUREMENT_PERIOD_FROM_UTC"),
        ("SENSOR_AUDIT_RESULTS", "AUDIT_FROM_UTC"),
        ("SENSOR_AUDIT_RESULTS", "AUDIT_TO_UTC"),
        ("SENSOR_AUDIT_RESULTS", "OLDEST_MEASUREMENT_AT"),
        ("SENSOR_AUDIT_RESULTS", "NEWEST_MEASUREMENT_AT"),
        ("LOAD_SUMMARY", "REFRESH_FROM_UTC"),
        ("LOAD_SUMMARY", "REFRESH_TO_UTC"),
        ("LOAD_SUMMARY", "ABSENT_RECORD_COUNT"),
        ("LOAD_SUMMARY", "OLDEST_NEW_MEASUREMENT_AT"),
    ):
        assert re.search(
            rf"COMMENT\s+ON\s+COLUMN\s+OPENAQ\.BRONZE\.{table}\.{column}\s+IS\s+'",
            sql,
            re.IGNORECASE,
        ), f"04_bronze_tables.sql must document OPENAQ.BRONZE.{table}.{column}"


@pytest.mark.parametrize("script", PROVISION_SCRIPTS, ids=lambda p: p.name)
def test_script_non_empty(script: Path) -> None:
    assert script.read_text().strip(), f"{script.name} is empty"


@pytest.mark.parametrize("script", PROVISION_SCRIPTS, ids=lambda p: p.name)
def test_no_create_or_replace_on_stateful_objects(script: Path) -> None:
    hits = CREATE_OR_REPLACE_STATEFUL.findall(script.read_text())
    assert not hits, (
        f"{script.name} uses CREATE OR REPLACE on a stateful object "
        f"(breaks idempotency): {hits}"
    )


@pytest.mark.parametrize("script", PROVISION_SCRIPTS, ids=lambda p: p.name)
def test_stateful_create_uses_if_not_exists(script: Path) -> None:
    offenders = [
        stmt[:80]
        for stmt in _statements(script.read_text())
        if CREATE_STATEFUL_UNGUARDED.search(stmt)
    ]
    assert not offenders, (
        f"{script.name} has a stateful CREATE without IF NOT EXISTS "
        f"(breaks idempotency): {offenders}"
    )
