-- dim_location — one row per office location. Type 1 (no history tracked).
--
-- 5 locations: New York, Chicago, Austin, Denver, San Francisco.
-- location_type ∈ {OFFICE, REMOTE}. region groups locations for dashboard
-- geographic breakdowns (Page 1 — Workforce Overview).
--
-- Phantom row for '__NO_LOC__': mirrors the COALESCE(location_id, '__NO_LOC__')
-- in the SCD2 snapshot for employees in a remote-pending state at hire.

{{ config(materialized='table') }}

with locations as (
    select * from {{ source('raw', 'locations') }}
),

sentinel as (
    select
        '__NO_LOC__'             as location_id,
        'Sentinel — source NULL' as location_name,
        'UNKNOWN'                as location_type,
        'UNKNOWN'                as region
)

select location_id, location_name, location_type, region from locations
union all
select location_id, location_name, location_type, region from sentinel
