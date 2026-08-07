"""Contract checks for the dbt-driven transformation DAG."""


def test_transform_dag_renders_the_typed_staging_models() -> None:
    from dags.openaq_transform import openaq_transform

    assert openaq_transform.dag_id == "openaq_transform"
    assert openaq_transform.max_active_runs == 1
    assert set(openaq_transform.tags) == {"openaq", "silver", "transform", "dbt"}

    rendered_model_tasks = {
        task.task_id for task in openaq_transform.tasks if task.task_id.startswith("stg_")
    }
    assert rendered_model_tasks == {
        "stg_location_sensors_run",
        "stg_locations_run",
        "stg_measurements_run",
    }


def test_staging_models_keep_raw_payloads() -> None:
    from pathlib import Path

    models_dir = Path(__file__).resolve().parent.parent / "dbt" / "openaq" / "models" / "staging"

    assert "raw_measurement" in (models_dir / "stg_measurements.sql").read_text()
    assert "raw_location" in (models_dir / "stg_locations.sql").read_text()
    assert "raw_sensor" in (models_dir / "stg_location_sensors.sql").read_text()
