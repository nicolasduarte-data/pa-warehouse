-- fact_performance_ratings — one row per performance review per employee.
--
-- Grain: one row per rating_id.
-- 7,454 rows: MID-year (4,344) + YEAR_END (3,110) cycles over 36 months.
-- ~3 complete review cycles per employee.
--
-- Downstream use cases:
--   1. Last rating before termination — IsRegrettableFlag mart (Loop 3 Story 3.2)
--      uses a window function: MAX(review_date) < term_date per employee.
--   2. Performance × attrition scatter — Page 2 dashboard.
--   3. OLS Spec 3 control variable — pay equity analysis Page 4.
--
-- potential_flag is carried through because the regrettable-attrition CPT
-- weights HIGH potential heavily (P(reg | potential=HIGH) >> baseline).

{{ config(materialized='table') }}

with ratings as (
    select * from {{ ref('stg_performance_ratings') }}
),

employees as (
    select
        employee_id,
        dept_id,
        job_id,
        gender
    from {{ ref('stg_employees_current') }}
)

select
    -- ── Keys ─────────────────────────────────────────────────────────────────
    ratings.rating_id,
    ratings.employee_id,

    -- ── Date FK ───────────────────────────────────────────────────────────────
    ratings.review_date,

    -- ── Review attributes ─────────────────────────────────────────────────────
    ratings.review_cycle,
    ratings.performance_rating,
    ratings.potential_flag,

    -- ── Org context ───────────────────────────────────────────────────────────
    employees.dept_id,
    employees.job_id,
    employees.gender

from ratings
left join employees using (employee_id)
