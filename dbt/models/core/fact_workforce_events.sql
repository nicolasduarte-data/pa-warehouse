-- fact_workforce_events — one row per workforce event, enriched with org context.
--
-- Grain: one row per event_id.
-- 2,569 rows: 1,512 hires + 770 voluntary terms + 287 involuntary terms.
-- 341 employees have no events (hired before the 36-month observation window
-- — their hire event falls outside the captured period).
--
-- Org context (dept, job, location) comes from stg_employees_current — the
-- current state. This is appropriate because our synthetic dataset has no
-- mid-employment attribute changes; every employee has exactly one SCD2 row.
-- The SCD2 snapshot exists to demonstrate the capability for datasets that
-- DO have promotions and transfers; this fact table uses it correctly by
-- joining on the current (and only) snapshot row per employee.
--
-- is_regrettable and the boolean convenience columns come from
-- stg_workforce_events — generated at the source, not derived here.

{{ config(materialized='table') }}

with events as (
    select * from {{ ref('stg_workforce_events') }}
),

employees as (
    select
        employee_id,
        dept_id,
        job_id,
        location_id,
        gender,
        performance_tier
    from {{ ref('stg_employees_current') }}
)

select
    -- ── Surrogate + natural keys ──────────────────────────────────────────────
    events.event_id,
    events.employee_id,

    -- ── Date FK (joins to dim_date.date_day) ─────────────────────────────────
    events.event_date,

    -- ── Event attributes ─────────────────────────────────────────────────────
    events.event_type,
    events.is_regrettable,

    -- Boolean convenience columns from staging — avoids CASE logic downstream.
    events.is_voluntary_term,
    events.is_involuntary_term,
    events.is_any_term,
    events.is_hire,

    -- ── Org context at time of event ─────────────────────────────────────────
    -- LEFT JOIN: 341 employees have no events (pre-window hires).
    -- Employees with events always have a matching employee row, so nulls
    -- here would indicate a data quality issue — caught by the relationships
    -- test in _core.yml.
    employees.dept_id,
    employees.job_id,
    employees.location_id,
    employees.gender,
    employees.performance_tier

from events
left join employees using (employee_id)
