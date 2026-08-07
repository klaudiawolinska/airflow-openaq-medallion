"""Contract checks for the dbt-driven transformation DAG."""


def test_transform_dag_renders_the_typed_staging_models() -> None:
    from dags.openaq_transform import openaq_transform

    assert openaq_transform.dag_id == "openaq_transform"
    assert openaq_transform.max_active_runs == 1
    assert set(openaq_transform.tags) == {"openaq", "silver", "transform", "dbt"}

    rendered_model_tasks = {
        task.task_id.removesuffix(".run")
        for task in openaq_transform.tasks
        if task.task_id.startswith("stg_") and task.task_id.endswith(".run")
    }
    assert rendered_model_tasks == {
        "stg_location_sensors",
        "stg_locations",
        "stg_measurements",
    }


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
