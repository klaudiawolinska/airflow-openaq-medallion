with latest_snapshot as (
    select max(snapshot_at) as snapshot_at
    from {{ ref('stg_locations') }}
)

select
    location.load_id,
    location.snapshot_at,
    location.location_id,
    location.location_name,
    location.locality,
    location.country_id,
    location.country_code,
    location.country_name,
    location.provider_id,
    location.provider_name,
    location.owner_id,
    location.owner_name,
    round(location.latitude, 6) as latitude,
    round(location.longitude, 6) as longitude,
    location.timezone,
    location.is_mobile,
    location.is_monitor,
    location.instruments,
    location.licenses,
    location.loaded_at
from {{ ref('stg_locations') }} as location
where location.snapshot_at = (
    select snapshot_at
    from latest_snapshot
)
