{{
    config(
        materialized='incremental',
        unique_key=['sensor_id', 'parameter_id', 'measurement_period_from_utc'],
        incremental_strategy='merge',
        on_schema_change='fail',
        pre_hook="{% if is_incremental() %} delete from {{ this }} where measurement_period_from_utc >= (select refresh_from_utc from {{ source('bronze', 'load_summary') }} qualify row_number() over (order by completed_at desc, load_id desc) = 1) and measurement_period_from_utc < (select refresh_to_utc from {{ source('bronze', 'load_summary') }} qualify row_number() over (order by completed_at desc, load_id desc) = 1) {% endif %}"
    )
}}

with identified as (
    select
        sensor_id,
        parameter_id,
        measurement_period_from_utc,
        measurement_value,
        lower(trim(parameter_name)) as parameter_name,
        trim(parameter_unit) as parameter_unit,
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
        loaded_at,
        raw_measurement,
        count(*) over (
            partition by sensor_id, parameter_id, measurement_period_from_utc
        ) as identity_row_count
    from {{ ref('stg_measurements') }}
    {% if is_incremental() %}
        where measurement_period_from_utc >= (
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
), assessed as (
    select
        *,
        identity_row_count > 1 as is_duplicate_identity,
        case
            when sensor_id is null
                or parameter_id is null
                or measurement_period_from_utc is null
                or identity_row_count > 1
                or measurement_value is null
                or measurement_value < 0
                or parameter_name is null
                or parameter_name not in ('bc', 'co', 'no2', 'o3', 'pm10', 'pm25', 'so2')
                or parameter_unit is null
                or parameter_unit <> 'µg/m³'
                then false
            else true
        end as is_valid,
        array_to_string(
            array_construct_compact(
                iff(sensor_id is null, 'missing_sensor_id', null),
                iff(parameter_id is null, 'missing_parameter_id', null),
                iff(measurement_period_from_utc is null, 'missing_measurement_period', null),
                iff(identity_row_count > 1, 'duplicate_identity', null),
                iff(measurement_value is null, 'missing_measurement_value', null),
                iff(measurement_value < 0, 'negative_measurement_value', null),
                iff(parameter_name is null, 'missing_parameter_name', null),
                iff(
                    parameter_name not in ('bc', 'co', 'no2', 'o3', 'pm10', 'pm25', 'so2'),
                    'unsupported_parameter',
                    null
                ),
                iff(parameter_unit is null, 'missing_parameter_unit', null),
                iff(parameter_unit <> 'µg/m³', 'unsupported_parameter_unit', null)
            ),
            '|'
        ) as invalid_reason
    from identified
)

select *
from assessed
