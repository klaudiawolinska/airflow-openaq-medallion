select
    sensor.load_id,
    sensor.snapshot_at,
    sensor.location_id,
    sensor.provider_id,
    sensor.provider_name,
    sensor.sensor_id,
    sensor.sensor_name,
    sensor.parameter_id,
    lower(trim(sensor.parameter_name)) as parameter_name,
    sensor.parameter_display_name,
    trim(sensor.parameter_unit) as parameter_unit,
    sensor.raw_sensor
from {{ ref('stg_location_sensors') }} as sensor
where exists (
    select 1
    from {{ ref('int_locations_current') }} as location
    where location.load_id = sensor.load_id
        and location.location_id = sensor.location_id
)
