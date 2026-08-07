select *
from {{ ref('int_locations_current') }}
where snapshot_at < (
    select max(snapshot_at)
    from {{ ref('stg_locations') }}
)
