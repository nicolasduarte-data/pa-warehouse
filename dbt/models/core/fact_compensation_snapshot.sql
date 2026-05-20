-- fact_compensation_snapshot — compensation history per employee, one row per
-- comp event (salary change or initial hire salary assignment).
--
-- Grain: one row per comp_id.
-- 5,609 rows for 2,500 employees = ~2.2 comp events per employee over 36 months.
-- The most recent row per employee (MAX(effective_date)) is their current comp.
--
-- "Snapshot" in the name reflects that each row captures the compensation
-- state from effective_date until the next change — a slowly-changing record
-- of what someone was paid at each point in time. Downstream models that
-- need point-in-time salary use window functions to find the active record
-- for a given date: MAX(effective_date) OVER (PARTITION BY employee_id
-- ORDER BY effective_date) WHERE effective_date <= reference_date.
--
-- band_midpoint is joined from dim_job so the pay equity OLS panel (Page 4)
-- can recompute compa_ratio and verify it against the stored value.

{{ config(materialized='table') }}

with comp as (
    select * from {{ ref('stg_compensation') }}
),

employees as (
    select
        employee_id,
        dept_id,
        job_id,
        location_id,
        gender
    from {{ ref('stg_employees_current') }}
),

jobs as (
    -- band_midpoint: needed to recompute compa_ratio = salary / band_midpoint.
    -- Stored compa_ratio in the source is reliable, but the raw inputs being
    -- present lets auditors verify the formula — transparency signal on Page 4.
    select job_id, job_level, band_midpoint, job_family
    from {{ ref('dim_job') }}
)

select
    -- ── Surrogate + natural keys ──────────────────────────────────────────────
    comp.comp_id,
    comp.employee_id,

    -- ── Date FK ───────────────────────────────────────────────────────────────
    comp.effective_date,

    -- ── Compensation attributes ───────────────────────────────────────────────
    comp.salary,
    comp.currency,
    comp.pay_band_id,
    comp.compa_ratio,

    -- ── Org context ───────────────────────────────────────────────────────────
    employees.dept_id,
    employees.job_id,
    employees.location_id,
    employees.gender,

    -- ── Job metadata (for pay equity analysis) ────────────────────────────────
    jobs.job_level,
    jobs.job_family,
    jobs.band_midpoint

from comp
left join employees using (employee_id)
left join jobs on employees.job_id = jobs.job_id
