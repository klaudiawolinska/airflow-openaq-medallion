select *
from {{ ref('int_measurements_rejected') }}
where invalid_reason is null
    or invalid_reason = ''
