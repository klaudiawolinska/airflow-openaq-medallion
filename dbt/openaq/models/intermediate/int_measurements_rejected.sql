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
    identity_row_count,
    is_duplicate_identity,
    invalid_reason,
    load_id,
    loaded_at,
    raw_measurement
from {{ ref('int_measurements_validated') }}
where not is_valid
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
