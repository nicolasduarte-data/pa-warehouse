-- v_attrition_analysis — Page 2 dashboard feed. Attrition Analysis (preliminary).
--
-- Feeds: KPI strip (voluntary/involuntary attrition rate, regrettable share,
--        avg tenure at exit), decomposition stack, performance × attrition scatter.
--
-- Two grains served from one view by including both monthly aggregates AND
-- the individual-level columns needed for the scatter plot. Looker Studio
-- can aggregate the individual rows to produce the monthly time series,
-- and use them directly for the scatter.
--
-- Grain: one row per termination event — enriched with:
--   - tenure_at_exit (how long the employee was at the company)
--   - last_performance_rating before termination (window function)
--   - dept, job_level, manager context
--
-- Why tenure_at_exit from employees not events?
-- The generator stores hire_date on employees.csv and exit_date alongside it.
-- Computing DATE_DIFF from these is cleaner than reconstructing from event dates.

{{ config(materialized='view') }}

with

-- Only termination events — this view is attrition-focused.
terminations as (
    select
        event_id,
        employee_id,
        event_date          as exit_date,
        event_type          as exit_type,
        is_regrettable,
        is_voluntary_term,
        is_involuntary_term,
        dept_id,
        job_id
    from {{ ref('fact_workforce_events') }}
    where is_any_term = true
),

-- Employee attributes for tenure and demographics.
employees as (
    select
        employee_id,
        hire_date,
        manager_id,
        gender,
        performance_tier     as current_performance_tier
    from {{ ref('stg_employees_current') }}
),

-- Job metadata for attrition segmentation.
jobs as (
    select job_id, job_level, job_family, is_critical_role, skill_scarcity_tier
    from {{ ref('dim_job') }}
),

-- Last performance rating BEFORE the exit date per employee.
-- Join to terminations FIRST so the rank only considers pre-exit ratings.
-- Without this, rank() = 1 might be a post-exit rating — the subsequent
-- review_date < exit_date join filter would then return NULL for that employee
-- even though earlier pre-exit ratings exist.
-- QUALIFY (BigQuery + Snowflake compatible) filters to the top-ranked row inline.
last_ratings as (
    select
        pr.employee_id,
        pr.performance_rating  as last_performance_rating,
        pr.potential_flag      as last_potential_flag,
        pr.review_date         as last_review_date
    from {{ ref('fact_performance_ratings') }} pr
    inner join terminations t
        on  pr.employee_id   = t.employee_id
        and pr.review_date   < t.exit_date   -- only ratings that pre-date the exit
    qualify row_number() over (
        partition by pr.employee_id
        order by pr.review_date desc         -- most recent pre-exit rating = 1
    ) = 1
)

select
    -- ── Event identity ────────────────────────────────────────────────────────
    t.event_id,
    t.employee_id,

    -- ── Exit attributes ───────────────────────────────────────────────────────
    t.exit_date,
    {{ dbt.date_trunc('month', 't.exit_date') }} as exit_month,   -- for monthly decomposition
    t.exit_type,
    t.is_regrettable,
    t.is_voluntary_term,
    t.is_involuntary_term,

    -- ── Tenure at exit ────────────────────────────────────────────────────────
    -- dbt.datediff(start, end, part) — cross-dialect (BQ + Snowflake).
    -- Dividing months by 12.0 gives fractional years — better for scatter axis.
    {{ dbt.datediff('e.hire_date', 't.exit_date', 'month') }}              as tenure_months,
    round({{ dbt.datediff('e.hire_date', 't.exit_date', 'month') }} / 12.0, 2) as tenure_years,

    -- ── Last performance rating before exit ───────────────────────────────────
    -- NULL if the employee had no performance review before exiting.
    -- The scatter plot on Page 2 plots this against attrition — expect high
    -- performers to cluster in the "regrettable" bucket.
    lr.last_performance_rating,
    lr.last_potential_flag,

    -- ── Org context ───────────────────────────────────────────────────────────
    t.dept_id,
    e.gender,
    e.manager_id,
    j.job_level,
    j.job_family,
    j.is_critical_role,
    j.skill_scarcity_tier

from terminations t
left join employees e
    on t.employee_id = e.employee_id
left join jobs j
    on t.job_id = j.job_id
-- last_ratings already filtered to pre-exit + most recent; join on employee_id only.
left join last_ratings lr
    on t.employee_id = lr.employee_id
