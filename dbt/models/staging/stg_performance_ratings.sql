-- stg_performance_ratings — performance review history per employee.
--
-- One row per review cycle per employee. Two cycles per year (MID + ANNUAL),
-- giving ~3 complete cycles over 36 months — hence 7,454 rows for 2,500 employees.
--
-- Downstream use cases:
--   1. Last rating before a termination event (IsRegrettableFlag logic in marts)
--   2. Performance × attrition scatter on the dashboard (Page 2)
--   3. Progressive OLS control variable (Spec 3) for pay equity analysis (Page 4)

{{ config(materialized='view') }}

select
    -- ── Keys ────────────────────────────────────────────────────────────────
    rating_id,
    employee_id,

    -- ── Review attributes ────────────────────────────────────────────────────
    review_date,

    -- review_cycle ∈ {MID, YEAR_END}. Validated via accepted_values test in
    -- _staging.yml — any unexpected value fails the dbt test suite.
    review_cycle,

    -- rating is an ordinal integer 1–5 (5 = highest performance).
    -- Stored as INT64 in raw; no casting needed. Aliased to performance_rating
    -- so downstream models read clearly without needing the source context.
    rating as performance_rating,

    -- potential_flag ∈ {LOW, MID, HIGH} — future potential assessment.
    -- Used in IsRegrettableFlag CPT: HIGH potential → elevated regrettable risk.
    potential_flag

from {{ source('raw', 'performance_ratings') }}
