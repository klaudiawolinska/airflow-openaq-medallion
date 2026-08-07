select
    location.load_id,
    location.snapshot_at,
    location.location_id,
    location.provider_id,
    location.provider_name,
    sensor.value:id::number(38, 0) as sensor_id,
    sensor.value:name::varchar as sensor_name,
    sensor.value:parameter:id::number(38, 0) as parameter_id,
    sensor.value:parameter:name::varchar as parameter_name,
    sensor.value:parameter:displayName::varchar as parameter_display_name,
    sensor.value:parameter:units::varchar as parameter_unit,
    sensor.value as raw_sensor,
    location.raw_location
from {{ ref('stg_locations') }} as location,
lateral flatten(input => location.sensors) as sensor
