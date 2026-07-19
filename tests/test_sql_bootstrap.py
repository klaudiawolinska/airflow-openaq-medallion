"""Static idempotency guards for the Snowflake bootstrap scripts.

The bootstrap SQL (``include/sql/bootstrap/``) is run once by an admin and must
be safe to re-run: a second execution converges settings without destroying
data. Live idempotency is verified against a real account (see the bootstrap
README); these checks run in CI *without* Snowflake and fail fast on the
anti-patterns that break re-runnability — chiefly ``CREATE OR REPLACE`` on
stateful objects and unguarded ``CREATE`` (missing ``IF NOT EXISTS``).

Only the ordered provisioning scripts (00..03) are checked. ``99_teardown.sql``
is intentionally destructive and excluded.
"""

import re
from pathlib import Path

import pytest

BOOTSTRAP_DIR = Path(__file__).resolve().parent.parent / "include" / "sql" / "bootstrap"

# Provisioning scripts only: 00..89. Excludes 90..99 (teardown).
PROVISION_SCRIPTS = sorted(BOOTSTRAP_DIR.glob("[0-8][0-9]_*.sql"))

# CREATE OR REPLACE on a stateful object drops and recreates it — for a
# database/schema/warehouse/user/table that destroys data or resets state.
CREATE_OR_REPLACE_STATEFUL = re.compile(
    r"create\s+or\s+replace\s+(?:transient\s+)?"
    r"(database|schema|warehouse|user|table)\b",
    re.IGNORECASE,
)

# A stateful CREATE not immediately followed by IF NOT EXISTS. "table" is absent
# on purpose: bootstrap creates none, and "GRANT CREATE TABLE ..." would false-
# positive. CREATE OR REPLACE is caught by the rule above, so exclude "or" here.
CREATE_STATEFUL_UNGUARDED = re.compile(
    r"create\s+(?:transient\s+)?(database|schema|warehouse|user|role)\b"
    r"(?!\s+if\s+not\s+exists)",
    re.IGNORECASE,
)


def _statements(sql: str) -> list[str]:
    """Strip ``--`` line comments, then split into statements on ``;``."""
    without_comments = re.sub(r"--[^\n]*", "", sql)
    return [s.strip() for s in without_comments.split(";") if s.strip()]


def test_provision_scripts_present() -> None:
    names = [p.name for p in PROVISION_SCRIPTS]
    for prefix in ("00_", "01_", "02_", "03_"):
        assert any(n.startswith(prefix) for n in names), (
            f"Missing bootstrap script {prefix}*.sql; found {names}"
        )


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
