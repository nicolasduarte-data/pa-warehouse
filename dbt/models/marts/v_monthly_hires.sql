-- v_monthly_hires — monthly hire count aggregation.
--
-- Original tracer-bullet model. Proves the full pipeline works end-to-end:
-- CSV -> BigQuery raw -> dbt source -> dbt model -> marts dataset -> Looker Studio.
-- The staging + core layers and v_workforce_overview supersede it.

{{ config(materialized='view') }}

select
    {{ dbt.date_trunc('month', 'event_date') }} as hire_month,
    count(*)                        as hire_count
from {{ source('raw', 'workforce_events') }}
where event_type = 'hire'
group by 1
order by 1
