-- stg_survey_responses — quarterly eNPS survey responses per employee.
--
-- One row per survey response. Quarterly cadence produces ~6.4 responses per
-- employee over 36 months — 16,095 total rows for 2,500 employees.
--
-- response_category is derived from enps_score at generation time:
--   PROMOTER  → score 9–10
--   PASSIVE   → score 7–8
--   DETRACTOR → score 0–6
--
-- The eNPS formula: eNPS = (%Promoters - %Detractors) × 100.
-- Aggregate eNPS for this dataset is calibrated to ~34 (Story 2.2.8).
-- The dashboard Page 2 attrition analysis correlates eNPS trend with turnover.

{{ config(materialized='view') }}

select
    -- ── Keys ────────────────────────────────────────────────────────────────
    survey_id,
    employee_id,

    -- ── Survey attributes ────────────────────────────────────────────────────
    survey_date,

    -- enps_score: raw NPS integer 0–10.
    enps_score,

    -- response_category: pre-computed label — avoids repeating the score-to-
    -- category thresholds in every downstream query. The accepted_values test
    -- in _staging.yml catches any unexpected values from future generator runs.
    response_category,

    -- ── Derived convenience columns ──────────────────────────────────────────
    -- Boolean flags per category — same pattern as stg_workforce_events convenience
    -- columns. Downstream aggregations can SUM() these instead of writing CASE.
    (response_category = 'PROMOTER')  as is_promoter,
    (response_category = 'DETRACTOR') as is_detractor,
    (response_category = 'PASSIVE')   as is_passive,

    -- ── Survey signal columns (paw-prey-006) ─────────────────────────────────
    -- engagement_score: 1.0–5.0 Likert scale. Generated with perf_tier
    -- correlation (see generator/generate.py). Adds ML signal beyond eNPS.
    engagement_score,

    -- manager_relationship_score: 1.0–5.0 Likert scale. Weakly correlated
    -- with perf_tier (manager quality is more org-random). Noisier signal.
    manager_relationship_score

from {{ source('raw', 'survey_responses') }}
