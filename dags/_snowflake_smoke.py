"""Snowflake smoke-test DAG.

Verifies that Airflow can reach Snowflake.
"""

import logging
from datetime import UTC, datetime

from airflow.providers.snowflake.hooks.snowflake import SnowflakeHook
from airflow.sdk import dag, task

log = logging.getLogger(__name__)

SNOWFLAKE_CONN_ID = "snowflake_default"

DEFAULT_ARGS = {
    "retries": 0,
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
    def select_version() -> None:
        hook = SnowflakeHook(snowflake_conn_id=SNOWFLAKE_CONN_ID)
        version, role, warehouse, database = hook.get_first(
            "SELECT CURRENT_VERSION(), CURRENT_ROLE(), "
            "CURRENT_WAREHOUSE(), CURRENT_DATABASE()"
        )

        context = {
            "snowflake_version": version,
            "current_role": role,
            "current_warehouse": warehouse,
            "current_database": database,
        }
        log.info("Snowflake smoke OK: %s", context)

    select_version()


snowflake_smoke()
