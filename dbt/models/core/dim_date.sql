-- dim_date — calendar dimension covering 2022-01-01 through 2027-12-31.
--
-- Why a date dimension?
-- Instead of calling DATE_TRUNC() or EXTRACT() in every dashboard query,
-- you join once to dim_date and get month/quarter/year/weekend flags for free.
-- Every fact table joins its date column to dim_date.date_day.
--
-- Why dbt_utils.date_spine instead of GENERATE_DATE_ARRAY?
-- GENERATE_DATE_ARRAY is BigQuery-only. date_spine is cross-warehouse — it
-- compiles to GENERATE_DATE_ARRAY on BigQuery and GENERATOR() on Snowflake.
-- Since Loop 5 ports this project to Snowflake, using date_spine now means
-- the Snowflake port needs zero changes to this model.
--
-- date_spine generates from start_date (inclusive) to end_date (exclusive),
-- so we pass 2028-01-01 to include all of 2027.

{{ config(materialized='table') }}

with spine as (
    -- date_spine produces one row per day with a column called date_day.
    -- The cast() is needed because date_spine outputs TIMESTAMP on some
    -- adapters — casting to DATE guarantees consistent type downstream.
    {{ dbt_utils.date_spine(
        datepart="day",
        start_date="cast('2022-01-01' as date)",
        end_date="cast('2028-01-01' as date)"
    ) }}
),

dates as (
    select cast(date_day as date) as date_day
    from spine
),

-- ── Dynamic observation window ───────────────────────────────────────────────
-- Auto-detect the window from actual event data instead of hardcoding dates.
-- Why dynamic: the generator uses date.today() as window_end, so the actual
-- data window shifts every day the generator runs. Hardcoded bounds drift
-- out of sync immediately. Pulling min/max from facts means dim_date always
-- matches what's actually in the warehouse.
--
-- window_start: first hire event (earlier exit events exist for pre-window
--               hires but they're outside the "captured" period). Truncated
--               to month so the bound aligns with monthly aggregations.
-- window_end:   last event of any type, truncated to month-end.
--
-- DAG ordering: this CTE references fact_workforce_events, which dbt will
-- build before dim_date. fact_workforce_events does NOT reference dim_date,
-- so no circular dependency.
observation_bounds as (
    select
        -- date_trunc dialect: BQ is date_trunc(date, part); Snowflake is
        -- date_trunc('part', date). dbt.date_trunc handles both.
        {{ dbt.date_trunc('month', "min(case when event_type = 'hire' then event_date end)") }} as window_start,
        -- last_day(date, part) — supported by BOTH adapters' last_day implementations,
        -- but routing through dbt.last_day keeps the dependency explicit.
        {{ dbt.last_day('max(event_date)', 'month') }} as window_end
    from {{ ref('fact_workforce_events') }}
)

select
    -- ── Primary key ──────────────────────────────────────────────────────────
    d.date_day,

    -- ── Year / quarter / month ───────────────────────────────────────────────
    -- extract() pulls a single date part as an integer.
    extract(year    from d.date_day) as year,
    extract(quarter from d.date_day) as quarter_of_year,
    extract(month   from d.date_day) as month_of_year,

    -- date_trunc snaps a date back to the first day of its period.
    -- Fact tables join on month_start to aggregate by month without
    -- needing to call date_trunc in every downstream query.
    -- Cast to DATE: dbt.date_trunc compiles to timestamp_trunc on BigQuery,
    -- which returns TIMESTAMP. Downstream models (v_workforce_overview) compare
    -- month_start against DATE columns — cast enforces the correct type.
    cast({{ dbt.date_trunc('month',   'd.date_day') }} as date) as month_start,
    cast({{ dbt.date_trunc('quarter', 'd.date_day') }} as date) as quarter_start,
    cast({{ dbt.date_trunc('year',    'd.date_day') }} as date) as year_start,

    -- Human-readable labels for dashboard filter dropdowns and chart axes.
    -- Cross-dialect (paw-prey-005 Story 5.6):
    --   BigQuery's format_date('%b %Y', d) uses strftime — Snowflake doesn't
    --   support strftime. Snowflake uses to_char(d, 'Mon YYYY') with Oracle-
    --   style format specifiers. Outputs differ slightly in case ('Jan' vs
    --   'JAN' depending on format) — acceptable: the parity check measures
    --   row counts and aggregates, not string label equality.
    {%- if target.type == 'bigquery' %}
    format_date('%b %Y',  d.date_day)                        as month_label,
    format_date('%Y-Q%Q', d.date_day)                        as quarter_label,
    {%- else %}
    to_char(d.date_day, 'Mon YYYY')                          as month_label,
    to_char(d.date_day, 'YYYY') || '-Q' || extract(quarter from d.date_day) as quarter_label,
    {%- endif %}

    -- ── Day of week ──────────────────────────────────────────────────────────
    -- Cross-dialect: dayofweek numbering differs (BQ 1-7 Sun=1, Snowflake 0-6
    -- Sun=0 by default), so the integer column itself is target-dependent —
    -- consumers must read day_name (the string) for portable logic.
    extract(dayofweek from d.date_day)                       as day_of_week,

    {%- if target.type == 'bigquery' %}
    format_date('%A', d.date_day)                            as day_name,
    -- BQ DAYOFWEEK: 1 = Sunday, 7 = Saturday.
    extract(dayofweek from d.date_day) in (1, 7)             as is_weekend,
    {%- else %}
    -- Snowflake's "Day" format pads to 9 chars with spaces; trim cleans it up.
    -- Returns "Monday", "Tuesday", etc. — same shape as BQ's '%A'.
    trim(to_char(d.date_day, 'Day'))                         as day_name,
    -- Snowflake DAYOFWEEK: 0 = Sunday, 6 = Saturday (default policy).
    extract(dayofweek from d.date_day) in (0, 6)             as is_weekend,
    {%- endif %}

    -- ── Observation window flag ───────────────────────────────────────────────
    -- TRUE for days within the dynamically-detected window. Dashboards filter
    -- on this so charts don't show empty leading/trailing periods.
    -- dbt.date_trunc returns TIMESTAMP on BigQuery (not DATE), so cast both
    -- bounds to DATE before the BETWEEN — BigQuery rejects DATE BETWEEN TIMESTAMP.
    d.date_day between cast(ob.window_start as date) and cast(ob.window_end as date)
        as is_in_observation_window,

    -- Expose the bounds themselves for any downstream model that needs them.
    cast(ob.window_start as date) as observation_window_start,
    cast(ob.window_end   as date) as observation_window_end

from dates d
cross join observation_bounds ob
order by d.date_day
