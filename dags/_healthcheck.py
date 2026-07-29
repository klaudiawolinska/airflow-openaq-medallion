"""Healthcheck DAG.

A dependency-free DAG that verifies that the Airflow runtime is operational.
It touches no external systems, so it is safe to trigger in any environment.
"""

from datetime import UTC, datetime

from airflow.sdk import dag, task

DEFAULT_ARGS = {
    "retries": 0,
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
        return "ok"

    ping()


healthcheck()
