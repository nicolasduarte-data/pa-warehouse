-- dim_job — one row per job code. Type 1 (no history tracked).
--
-- Carries the metadata that drives several dashboard analyses:
--   - is_critical_role → IsRegrettableFlag logic
--   - skill_scarcity_tier → attrition risk segmentation (Page 2)
--   - band_midpoint → denominator for compa_ratio
--   - job_level → control variable for a gender pay gap regression
--
-- No phantom row needed: job_id is NOT NULL on every employee (see the
-- snapshot's COALESCE rules). Every employee always has a job.

{{ config(materialized='table') }}

select
    job_id,
    job_title,
    job_level,
    job_family,
    is_critical_role,
    skill_scarcity_tier,
    band_midpoint

from {{ source('raw', 'jobs') }}
