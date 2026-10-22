-- v_workforce_overview — Page 1 dashboard feed. Workforce Overview.
--
-- Feeds: KPI strip (headcount, hiring rate, attrition rate, net change)
--        HC trend line, hires-vs-exits waterfall, dept/job_level breakdown.
--
-- Grain: one row per (month_start × dept_id × job_level).
-- Looker Studio aggregates this to produce page-level totals — the grain
-- gives it enough dimensions to slice by dept OR job_level OR both.
--
-- Two parts joined together:
--   1. headcount_snapshot — active employee count at the first of each month.
--      This is a STOCK metric: cross-join months × employees, then filter
--      to employees whose hire_date <= month AND exit_date > month (or NULL).
--      It does NOT come from events — events are flows, not stocks.
--   2. monthly_flows — hire + term event counts per month × dept × job_level.
--      These are FLOW metrics: COUNT events that occurred in each month.
--
-- The stock/flow distinction matters for the KPI formulas:
--   Attrition rate = total_terms / avg_headcount (flow / stock)
--   Hiring rate    = hires / avg_headcount        (flow / stock)

{{ config(materialized='view') }}

with

-- ── Part 1: headcount snapshot ────────────────────────────────────────────────
-- All months in the observation window.
month_spine as (
    select distinct month_start
    from {{ ref('dim_date') }}
    where is_in_observation_window
),

-- Current employee attributes — one row per employee.
employees as (
    select
        employee_id,
        hire_date,
        exit_date,
        dept_id,
        job_id
    from {{ ref('stg_employees_current') }}
),

jobs as (
    select job_id, job_level, job_family
    from {{ ref('dim_job') }}
),

-- Department names for dashboard readability. Joined at the final SELECT so
-- the grain stays at (month × dept_id × job_level × job_family) — dept_name
-- is a Type 1 attribute and adding it to the GROUP BY would be redundant.
departments as (
    select dept_id, dept_name
    from {{ ref('dim_department') }}
),

-- Cross-join months × employees, then filter to active employees.
-- An employee is active at month_start if:
--   hire_date <= month_start   (already hired by this date)
--   AND exit_date > month_start OR exit_date IS NULL  (not yet gone)
-- Aggregated to (month_start × dept_id × job_level).
headcount_snapshot as (
    select
        m.month_start,
        e.dept_id,
        j.job_level,
        j.job_family,
        count(e.employee_id) as headcount
    from month_spine m
    cross join employees e
    left join jobs j on e.job_id = j.job_id
    where e.hire_date <= m.month_start
      and (e.exit_date is null or e.exit_date > m.month_start)
    group by 1, 2, 3, 4
),

-- ── Part 2: monthly event flows ───────────────────────────────────────────────
-- Hire and termination counts per month × dept × job_level.
-- event_date truncated to month_start so it joins to headcount_snapshot.
--
-- WHY THE INNER JOIN TO month_spine?
-- The generator emits exit events for pre-window hires (employees who were
-- hired before the observation window opened, then exited during a tracked
-- year). Those exits have valid event dates but no corresponding headcount
-- snapshot rows — month_spine only includes the 36 in-window months.
-- Without this filter, the final FULL OUTER JOIN includes pre-window months
-- with hc=0 and stray exits, producing the misleading "headcount drops to 0"
-- artifact at the dashboard's leading/trailing edges.
monthly_flows as (
    select
        -- Cast to DATE: dbt.date_trunc compiles to timestamp_trunc on BigQuery.
        -- month_spine.month_start is DATE (from dim_date after its own fix), so
        -- both sides of the join and the returned column must match.
        cast({{ dbt.date_trunc('month', 'fe.event_date') }} as date) as month_start,
        fe.dept_id,
        j.job_level,
        j.job_family,
        {{ count_if('fe.is_hire') }}                as hire_count,
        {{ count_if('fe.is_voluntary_term') }}      as voluntary_term_count,
        {{ count_if('fe.is_involuntary_term') }}    as involuntary_term_count,
        {{ count_if('fe.is_any_term') }}            as total_term_count,
        {{ count_if('fe.is_hire') }} - {{ count_if('fe.is_any_term') }} as net_change
    from {{ ref('fact_workforce_events') }} fe
    left join jobs j on fe.job_id = j.job_id
    inner join month_spine m on cast({{ dbt.date_trunc('month', 'fe.event_date') }} as date) = m.month_start
    group by 1, 2, 3, 4
)

-- ── Final join: stock + flow on the same grain ───────────────────────────────
-- FULL OUTER JOIN because some month × dept × job_level combinations may have
-- headcount but no events that month (stable period), or events but no headcount
-- row (edge case: employee exits on the first of the month).
select
    coalesce(hs.month_start,   mf.month_start)  as month_start,
    coalesce(hs.dept_id,       mf.dept_id)       as dept_id,
    d.dept_name                                   as dept_name,
    coalesce(hs.job_level,     mf.job_level)     as job_level,
    coalesce(hs.job_family,    mf.job_family)    as job_family,

    coalesce(hs.headcount, 0)            as headcount,
    coalesce(mf.hire_count, 0)           as hire_count,
    coalesce(mf.voluntary_term_count, 0) as voluntary_term_count,
    coalesce(mf.involuntary_term_count, 0) as involuntary_term_count,
    coalesce(mf.total_term_count, 0)     as total_term_count,
    coalesce(mf.net_change, 0)           as net_change

-- Join keys must include job_family. Without it, when multiple job_families
-- exist for the same (month, dept, level), the FULL OUTER JOIN cross-joins
-- those rows and inflates headcount/flows by N × M (an N:M fanout bug).
-- COALESCE handles NULL job_family safely (NULL = NULL evaluates to NULL).
from headcount_snapshot hs
full outer join monthly_flows mf
    on  hs.month_start = mf.month_start
    and hs.dept_id     = mf.dept_id
    and hs.job_level   = mf.job_level
    and coalesce(hs.job_family, '__NO_FAMILY__') = coalesce(mf.job_family, '__NO_FAMILY__')
-- LEFT JOIN to enrich with dept_name. Type 1 attribute (no history), safe to
-- join post-aggregation without affecting the grain.
left join departments d
    on coalesce(hs.dept_id, mf.dept_id) = d.dept_id
