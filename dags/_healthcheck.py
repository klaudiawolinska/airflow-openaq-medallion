"""Healthcheck DAG.

A trivial, dependency-free DAG that verifies the Airflow runtime is up and that
DAGs parse and run. It touches no external systems (no Snowflake, OpenAQ or
SMTP), so it is safe to trigger in any environment, including a fresh
`astro dev start`. The leading underscore keeps it sorted to the top of the UI
and marks it as an operational, non-data DAG.
"""

from datetime import UTC, datetime

from airflow.sdk import dag, task

DEFAULT_ARGS = {
    "owner": "data-platform",
    "retries": 2,
}


@dag(
    dag_id="_healthcheck",
    schedule=None,
    start_date=datetime(2026, 1, 1, tzinfo=UTC),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["ops", "healthcheck"],
    doc_md=__doc__,
)
def healthcheck():
    @task
    def ping() -> str:
        """Return a constant so a successful run is observable in UI and logs."""
        return "ok"

    ping()


healthcheck()
