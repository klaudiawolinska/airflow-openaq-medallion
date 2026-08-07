{% macro prepare_ci_sources() %}
    {% set measurements_sql %}
        create or replace table {{ target.database }}.{{ target.schema }}.measurements as
        select
            sensor_id,
            parameter_id,
            measurement_period_from_utc,
            parse_json(raw_measurement) as raw_measurement,
            load_id,
            loaded_at
        from {{ ref('measurements') }}
    {% endset %}

    {% set locations_sql %}
        create or replace table {{ target.database }}.{{ target.schema }}.location_snapshots as
        select
            load_id,
            snapshot_at,
            parse_json(raw_location) as raw_location,
            loaded_at
        from {{ ref('location_snapshots') }}
    {% endset %}

    {% set load_summary_sql %}
        create or replace table {{ target.database }}.{{ target.schema }}.load_summary as
        select
            load_id,
            refresh_from_utc,
            refresh_to_utc,
            completed_at
        from {{ ref('load_summary') }}
    {% endset %}

    {% do run_query(measurements_sql) %}
    {% do run_query(locations_sql) %}
    {% do run_query(load_summary_sql) %}
{% endmacro %}
