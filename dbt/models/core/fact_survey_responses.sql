-- fact_survey_responses — one row per eNPS survey response per employee.
--
-- Grain: one row per survey_id.
-- 16,095 rows: quarterly cadence, ~6.4 responses per employee over 36 months.
--
-- eNPS = (% Promoters - % Detractors) × 100.
-- Aggregate eNPS for this dataset is calibrated to ~34.
--
-- The boolean convenience columns (is_promoter, is_detractor, is_passive)
-- from staging let downstream marts compute eNPS with simple SUM() arithmetic
-- instead of nested CASE / COUNTIF expressions:
--
--   eNPS = (SUM(is_promoter) - SUM(is_detractor)) / COUNT(*) * 100
--
-- This pattern is dashboard-friendly: Looker Studio can use calculated fields
-- on SUM(is_promoter) and SUM(is_detractor) directly.

{{ config(materialized='table') }}

with surveys as (
    select * from {{ ref('stg_survey_responses') }}
),

employees as (
    select
        employee_id,
        dept_id,
        location_id,
        gender
    from {{ ref('stg_employees_current') }}
)

select
    -- ── Keys ─────────────────────────────────────────────────────────────────
    surveys.survey_id,
    surveys.employee_id,

    -- ── Date FK ───────────────────────────────────────────────────────────────
    surveys.survey_date,

    -- ── Survey attributes ─────────────────────────────────────────────────────
    surveys.enps_score,
    surveys.response_category,

    -- Boolean flags for SUM()-based eNPS calculation downstream.
    surveys.is_promoter,
    surveys.is_detractor,
    surveys.is_passive,

    -- ── Org context ───────────────────────────────────────────────────────────
    employees.dept_id,
    employees.location_id,
    employees.gender,

    -- ── Survey signal columns (paw-prey-006) ─────────────────────────────────
    -- Pass-through from staging — aggregation to employee grain happens in
    -- v_attrition_features where the snapshot_date leakage gate is applied.
    surveys.engagement_score,
    surveys.manager_relationship_score

from surveys
left join employees using (employee_id)
