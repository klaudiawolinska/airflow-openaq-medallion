"""Manual OpenAQ sensor audit for a requested UTC time window.

Large windows can require several paginated API requests per sensor. The client
enforces the OpenAQ request limits, so the audit can take substantially longer
when its request volume reaches those limits.
"""

import logging
from datetime import UTC, datetime

from airflow.providers.snowflake.hooks.snowflake import SnowflakeHook
from airflow.sdk import Param, Variable, dag, get_current_context, task

from include.openaq.audit import SensorAuditResult, audit_sensors, parse_audit_window
from include.openaq.client import OpenAQClient

log = logging.getLogger(__name__)

OPENAQ_API_KEY_VARIABLE = "openaq_api_key"
SNOWFLAKE_CONN_ID = "snowflake_default"

DEFAULT_ARGS = {
    "retries": 0,
}

AUDIT_INSERT_SQL = """
INSERT INTO OPENAQ.BRONZE.SENSOR_AUDIT_RESULTS (
    AUDIT_ID,
    AUDIT_FROM_UTC,
    AUDIT_TO_UTC,
    PROVIDER_ID,
    PROVIDER_NAME,
    LOCATION_ID,
    LOCATION_NAME,
    SENSOR_ID,
    SENSOR_NAME,
    PARAMETER_ID,
    PARAMETER_NAME,
    AUDIT_RESULT,
    RECORD_COUNT,
    OLDEST_MEASUREMENT_AT,
    NEWEST_MEASUREMENT_AT,
    ERROR_DETAIL
) VALUES (
    %(audit_id)s,
    %(window_started_at)s,
    %(window_ended_at)s,
    %(provider_id)s,
    %(provider_name)s,
    %(location_id)s,
    %(location_name)s,
    %(sensor_id)s,
    %(sensor_name)s,
    %(parameter_id)s,
    %(parameter_name)s,
    %(audit_result)s,
    %(record_count)s,
    %(oldest_measurement_at)s,
    %(newest_measurement_at)s,
    %(error_detail)s
)
"""


@dag(
    dag_id="openaq_audit",
    schedule=None,
    start_date=datetime(2026, 1, 1, tzinfo=UTC),
    catchup=False,
    default_args=DEFAULT_ARGS,
    params={
        "from": Param(
            None,
            type=["null", "string"],
            format="date-time",
            description="UTC start of the audit window.",
        ),
        "to": Param(
            None,
            type=["null", "string"],
            format="date-time",
            description="UTC end of the audit window.",
        ),
    },
    tags=["openaq", "audit", "manual"],
    doc_md=__doc__,
)
def openaq_audit():
    @task
    def audit() -> None:
        context = get_current_context()
        window_started_at, window_ended_at = parse_audit_window(
            context["params"]["from"], context["params"]["to"]
        )
        results = audit_sensors(
            OpenAQClient(Variable.get(OPENAQ_API_KEY_VARIABLE)),
            window_started_at=window_started_at,
            window_ended_at=window_ended_at,
        )
        _insert_audit_results(
            audit_id=context["run_id"],
            window_started_at=window_started_at,
            window_ended_at=window_ended_at,
            results=results,
        )
        result_counts = {
            result_type: sum(result.audit_result == result_type for result in results)
            for result_type in ("data", "empty", "error")
        }
        log.info("OpenAQ audit completed: %s", result_counts)

    audit()


def _insert_audit_results(
    *,
    audit_id: str,
    window_started_at: datetime,
    window_ended_at: datetime,
    results: list[SensorAuditResult],
) -> None:
    if not results:
        log.warning("OpenAQ audit discovered no target-parameter sensors")
        return

    rows = [
        {
            "audit_id": audit_id,
            "window_started_at": window_started_at,
            "window_ended_at": window_ended_at,
            "provider_id": result.provider_id,
            "provider_name": result.provider_name,
            "location_id": result.location_id,
            "location_name": result.location_name,
            "sensor_id": result.sensor_id,
            "sensor_name": result.sensor_name,
            "parameter_id": result.parameter_id,
            "parameter_name": result.parameter_name,
            "audit_result": result.audit_result,
            "record_count": result.record_count,
            "oldest_measurement_at": result.oldest_measurement_at,
            "newest_measurement_at": result.newest_measurement_at,
            "error_detail": result.error_detail,
        }
        for result in results
    ]
    hook = SnowflakeHook(snowflake_conn_id=SNOWFLAKE_CONN_ID)
    connection = hook.get_conn()
    try:
        with connection.cursor() as cursor:
            cursor.executemany(AUDIT_INSERT_SQL, rows)
        connection.commit()
    finally:
        connection.close()


openaq_audit()
