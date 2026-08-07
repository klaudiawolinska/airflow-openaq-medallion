"""Contract checks for the dbt-driven transformation DAG."""


def test_transform_dag_renders_the_staging_and_intermediate_models() -> None:
    from dags.openaq_transform import openaq_transform

    assert openaq_transform.dag_id == "openaq_transform"
    assert openaq_transform.max_active_runs == 1
    assert set(openaq_transform.tags) == {"openaq", "silver", "transform", "dbt"}

    expected_models = {
        "int_location_sensors_current",
        "int_locations_current",
        "int_measurements_conformed",
        "int_measurements_rejected",
        "int_measurements_validated",
        "stg_location_sensors",
        "stg_locations",
        "stg_measurements",
    }
    rendered_task_ids = {task.task_id for task in openaq_transform.tasks}
    assert {
        model_name
        for model_name in expected_models
        if any(task_id.startswith(model_name) for task_id in rendered_task_ids)
    } == expected_models

    test_tasks = [task for task in openaq_transform.tasks if task.task_id == "openaq_test"]
    assert len(test_tasks) == 1
    upstream_task_ids = {
        task.task_id for task in test_tasks[0].get_flat_relatives(upstream=True)
    }
    assert {
        model_name
        for model_name in expected_models
        if any(task_id.startswith(model_name) for task_id in upstream_task_ids)
    } == expected_models


def test_staging_models_keep_raw_payloads() -> None:
    from pathlib import Path

    models_dir = Path(__file__).resolve().parent.parent / "dbt" / "openaq" / "models" / "staging"

    assert "raw_measurement" in (models_dir / "stg_measurements.sql").read_text()
    assert "raw_location" in (models_dir / "stg_locations.sql").read_text()
    assert "raw_sensor" in (models_dir / "stg_location_sensors.sql").read_text()


def test_ci_fixture_macro_materializes_variant_sources() -> None:
    from pathlib import Path

    project_dir = next(
        directory
        for directory in Path(__file__).resolve().parents
        if (directory / "pyproject.toml").is_file()
    )
    macro_path = project_dir / "dbt" / "openaq" / "macros" / "ci" / "prepare_ci_sources.sql"
    macro = macro_path.read_text()

    assert "create or replace table {{ target.database }}.{{ target.schema }}.measurements" in macro
    assert "from {{ ref('measurements') }}" in macro
    assert "parse_json(raw_measurement) as raw_measurement" in macro
    assert "{% do run_query(measurements_sql) %}" in macro

    assert (
        "create or replace table {{ target.database }}.{{ target.schema }}.location_snapshots"
        in macro
    )
    assert "from {{ ref('location_snapshots') }}" in macro
    assert "parse_json(raw_location) as raw_location" in macro
    assert "{% do run_query(locations_sql) %}" in macro

    assert "create or replace table {{ target.database }}.{{ target.schema }}.load_summary" in macro
    assert "from {{ ref('load_summary') }}" in macro
    assert "{% do run_query(load_summary_sql) %}" in macro
