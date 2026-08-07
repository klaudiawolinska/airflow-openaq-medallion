{{
    config(
        materialized='incremental',
        unique_key=['sensor_id', 'parameter_id', 'measurement_period_from_utc'],
        incremental_strategy='merge',
        on_schema_change='fail',
        pre_hook="{% if is_incremental() %} delete from {{ this }} where measurement_period_from_utc >= (select refresh_from_utc from {{ source('bronze', 'load_summary') }} qualify row_number() over (order by completed_at desc, load_id desc) = 1) and measurement_period_from_utc < (select refresh_to_utc from {{ source('bronze', 'load_summary') }} qualify row_number() over (order by completed_at desc, load_id desc) = 1) {% endif %}"
    )
}}

select
    sensor_id,
    parameter_id,
    measurement_period_from_utc,
    measurement_value,
    parameter_name,
    parameter_unit,
    parameter_display_name,
    period_label,
    period_interval,
    period_started_at_utc,
    period_ended_at_utc,
    coverage_started_at_utc,
    coverage_ended_at_utc,
    coverage_expected_interval,
    coverage_observed_interval,
    coverage_expected_count,
    coverage_observed_count,
    coverage_percent_complete,
    coverage_percent_coverage,
    has_flags,
    measurement_coordinates,
    measurement_summary,
    load_id,
    loaded_at
from {{ ref('int_measurements_validated') }}
where is_valid
{% if is_incremental() %}
    and measurement_period_from_utc >= (
        select refresh_from_utc
        from {{ source('bronze', 'load_summary') }}
        qualify row_number() over (order by completed_at desc, load_id desc) = 1
    )
    and measurement_period_from_utc < (
        select refresh_to_utc
        from {{ source('bronze', 'load_summary') }}
        qualify row_number() over (order by completed_at desc, load_id desc) = 1
    )
{% endif %}
