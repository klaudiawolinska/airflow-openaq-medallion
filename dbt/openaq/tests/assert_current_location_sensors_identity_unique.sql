select
    location_id,
    sensor_id
from {{ ref('int_location_sensors_current') }}
group by 1, 2
having count(*) > 1
