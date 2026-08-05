"""Load a deterministic rolling OpenAQ window into Snowflake bronze."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from airflow.providers.snowflake.hooks.snowflake import SnowflakeHook
from airflow.sdk import Asset, AssetAlias, Variable, dag, get_current_context, task

from include.openaq.client import OpenAQClient
from include.openaq.ingest import collect_measurements, refresh_window_for_interval
from include.openaq.refresh_bronze import (
    RefreshResult,
    record_load_summary,
    refresh_window,
    stage_measurements,
)

log = logging.getLogger(__name__)

OPENAQ_API_KEY_VARIABLE = "openaq_api_key"
SNOWFLAKE_CONN_ID = "snowflake_default"

BRONZE_MEASUREMENTS_ASSET = Asset("openaq://snowflake/bronze/measurements")
BRONZE_MEASUREMENTS_CHANGE_ALIAS = AssetAlias("openaq_bronze_measurements_changed")

DEFAULT_ARGS = {
    "retries": 1,
    "retry_delay": timedelta(minutes=1),
}


def _run_identity_and_window(context: dict[str, Any]) -> tuple[str, datetime, datetime]:
    dag_run = context["dag_run"]
    refresh_from, refresh_to = refresh_window_for_interval(
        context["data_interval_start"], context["data_interval_end"]
    )
    return dag_run.run_id, refresh_from, refresh_to


@dag(
    dag_id="openaq_ingest",
    schedule=None,
    start_date=datetime(2026, 1, 1, tzinfo=UTC),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["openaq", "bronze", "ingest"],
    doc_md=__doc__,
)
def openaq_ingest():
    @task(retries=0)
    def fetch_api_and_stage() -> dict[str, object]:
        context = get_current_context()
        load_id, refresh_from, refresh_to = _run_identity_and_window(context)
        batch = collect_measurements(
            OpenAQClient(Variable.get(OPENAQ_API_KEY_VARIABLE)),
            window_started_at=refresh_from,
            window_ended_at=refresh_to,
        )

        hook = SnowflakeHook(snowflake_conn_id=SNOWFLAKE_CONN_ID)
        connection = hook.get_conn()
        try:
            stage_measurements(
                connection,
                load_id=load_id,
                measurements=batch.measurements,
            )
        finally:
            connection.close()

        summary = {
            "load_id": load_id,
            "location_count": batch.location_count,
            "sensor_count": batch.sensor_count,
            "api_record_count": batch.api_record_count,
            "staged_record_count": len(batch.measurements),
            "excluded_record_count": batch.excluded_record_count,
            "server_error_sensor_count": batch.server_error_sensor_count,
        }
        log.info("OpenAQ API fetch and staging completed: %s", summary)
        return summary

    @task(retries=0)
    def refresh_bronze(staging_summary: dict[str, object]) -> dict[str, object]:
        context = get_current_context()
        load_id, refresh_from, refresh_to = _run_identity_and_window(context)
        if staging_summary["load_id"] != load_id:
            raise RuntimeError("staging summary belongs to a different DAG run")

        hook = SnowflakeHook(snowflake_conn_id=SNOWFLAKE_CONN_ID)
        connection = hook.get_conn()
        try:
            result = refresh_window(
                connection,
                load_id=load_id,
                refresh_from=refresh_from,
                refresh_to=refresh_to,
            )
        finally:
            connection.close()

        refresh_summary = {**staging_summary, **result.xcom_value()}
        log.info("Snowflake bronze refresh completed: %s", result.xcom_value())
        return refresh_summary

    @task(outlets=[BRONZE_MEASUREMENTS_CHANGE_ALIAS])
    def record_summary_and_emit_asset(
        refresh_summary: dict[str, object],
        *,
        outlet_events,
    ) -> None:
        context = get_current_context()
        load_id, refresh_from, refresh_to = _run_identity_and_window(context)
        if refresh_summary["load_id"] != load_id:
            raise RuntimeError("refresh summary belongs to a different DAG run")
        api_record_count = refresh_summary["api_record_count"]
        if isinstance(api_record_count, bool) or not isinstance(api_record_count, int):
            raise RuntimeError("staging summary contains an invalid API record count")
        result = RefreshResult.from_snowflake(refresh_summary)

        hook = SnowflakeHook(snowflake_conn_id=SNOWFLAKE_CONN_ID)
        connection = hook.get_conn()
        try:
            record_load_summary(
                connection,
                load_id=load_id,
                load_type="ingest",
                refresh_from=refresh_from,
                refresh_to=refresh_to,
                api_record_count=api_record_count,
                refresh_result=result,
            )
        finally:
            connection.close()

        run_summary = {
            "load_id": load_id,
            "refresh_from": refresh_from.isoformat(),
            "refresh_to": refresh_to.isoformat(),
            "api_record_count": api_record_count,
            "server_error_sensor_count": refresh_summary["server_error_sensor_count"],
            **result.xcom_value(),
        }
        if result.bronze_changed:
            outlet_events[BRONZE_MEASUREMENTS_CHANGE_ALIAS].add(
                BRONZE_MEASUREMENTS_ASSET,
                extra=run_summary,
            )
            log.info(
                "OpenAQ ingest recorded its summary and emitted the bronze Asset: %s",
                run_summary,
            )
        else:
            log.info(
                "OpenAQ ingest recorded its summary; bronze was unchanged, so no Asset "
                "was emitted: %s",
                run_summary,
            )

    staging_summary = fetch_api_and_stage()
    refresh_summary = refresh_bronze(staging_summary)
    record_summary_and_emit_asset(refresh_summary)


openaq_ingest()
