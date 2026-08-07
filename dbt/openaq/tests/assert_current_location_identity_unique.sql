select
    location_id
from {{ ref('int_locations_current') }}
group by 1
having count(*) > 1
