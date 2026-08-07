select
    sensor_id,
    parameter_id,
    measurement_period_from_utc
from {{ ref('int_measurements_conformed') }}
group by 1, 2, 3
having count(*) > 1
