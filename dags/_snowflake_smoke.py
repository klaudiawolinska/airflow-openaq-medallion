"""Snowflake smoke-test DAG.

Verifies that Airflow can reach Snowflake with the least-privilege pipeline
credentials provisioned in milestone 1 (see ``include/sql/bootstrap/``). It runs
a dependency-free ``SELECT CURRENT_VERSION()`` — plus the current role, warehouse
and database — through the ``snowflake_default`` connection, so a green run
confirms the connection, key-pair auth, and role wiring end to end.

The task **fails** if the session is not running as ``OPENAQ_PIPELINE``: an
over-privileged connection (``ACCOUNTADMIN``, say) would otherwise log green and
quietly break the least-privilege contract this DAG exists to prove.

Manual-trigger only (``schedule=None``): it touches Snowflake, so it must not run
on a bare ``astro dev start`` without credentials. The leading underscore keeps
it sorted to the top of the UI and marks it as an operational, non-data DAG.
"""

import logging
from datetime import UTC, datetime

from airflow.providers.snowflake.hooks.snowflake import SnowflakeHook
from airflow.sdk import dag, task

log = logging.getLogger(__name__)

SNOWFLAKE_CONN_ID = "snowflake_default"

# The pipeline must never run with broader rights than this (ADR-0016).
EXPECTED_ROLE = "OPENAQ_PIPELINE"

DEFAULT_ARGS = {
    "owner": "data-platform",
    "retries": 2,
}


@dag(
    dag_id="_snowflake_smoke",
    schedule=None,
    start_date=datetime(2026, 1, 1, tzinfo=UTC),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["ops", "snowflake", "smoke"],
    doc_md=__doc__,
)
def snowflake_smoke():
    @task
    def select_version() -> dict[str, str | None]:
        """Run a trivial query and return the connection context.

        The ``SnowflakeHook`` is built inside the task (not at import time) so
        the DAG parses without a live connection — DAG-integrity stays offline.
        """
        hook = SnowflakeHook(snowflake_conn_id=SNOWFLAKE_CONN_ID)
        version, role, warehouse, database = hook.get_first(
            "SELECT CURRENT_VERSION(), CURRENT_ROLE(), "
            "CURRENT_WAREHOUSE(), CURRENT_DATABASE()"
        )
        if (role or "").upper() != EXPECTED_ROLE:
            raise RuntimeError(
                f"Snowflake session runs as {role!r}, expected {EXPECTED_ROLE!r}. "
                "Check the `role` key in the connection extra — the pipeline must "
                "not hold broader privileges than the ones bootstrap grants it."
            )

        context = {
            "snowflake_version": version,
            "current_role": role,
            "current_warehouse": warehouse,
            "current_database": database,
        }
        log.info("Snowflake smoke OK: %s", context)
        return context

    select_version()


snowflake_smoke()
