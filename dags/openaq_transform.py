"""Build typed OpenAQ staging views after bronze publishes an Asset."""

from datetime import UTC, datetime, timedelta

from airflow.sdk import Asset
from cosmos import DbtDag
from cosmos.config import ExecutionConfig, ProfileConfig, ProjectConfig, RenderConfig
from cosmos.constants import ExecutionMode, InvocationMode, LoadMode
from cosmos.profiles import SnowflakePrivateKeyFilePemProfileMapping

SNOWFLAKE_CONN_ID = "snowflake_default"
DBT_PROJECT_PATH = "/usr/local/airflow/dbt/openaq"
DBT_EXECUTABLE_PATH = "/usr/local/airflow/dbt-venv/bin/dbt"
BRONZE_DATASET_ASSET = Asset("openaq://snowflake/bronze/dataset")

DEFAULT_ARGS = {
    "retries": 1,
    "retry_delay": timedelta(minutes=1),
}

openaq_transform = DbtDag(
    dag_id="openaq_transform",
    schedule=[BRONZE_DATASET_ASSET],
    start_date=datetime(2026, 1, 1, tzinfo=UTC),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["openaq", "silver", "transform", "dbt"],
    doc_md=__doc__,
    project_config=ProjectConfig(
        dbt_project_path=DBT_PROJECT_PATH,
        install_dbt_deps=False,
        partial_parse=False,
    ),
    profile_config=ProfileConfig(
        profile_name="openaq",
        target_name="pipeline",
        profile_mapping=SnowflakePrivateKeyFilePemProfileMapping(
            conn_id=SNOWFLAKE_CONN_ID,
            profile_args={"schema": "SILVER"},
        ),
    ),
    execution_config=ExecutionConfig(
        execution_mode=ExecutionMode.LOCAL,
        invocation_mode=InvocationMode.SUBPROCESS,
        dbt_executable_path=DBT_EXECUTABLE_PATH,
    ),
    render_config=RenderConfig(
        load_method=LoadMode.DBT_LS,
        invocation_mode=InvocationMode.SUBPROCESS,
        dbt_executable_path=DBT_EXECUTABLE_PATH,
        select=["path:models"],
    ),
)
