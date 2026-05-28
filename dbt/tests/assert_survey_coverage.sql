-- assert_survey_coverage — fails if <60% of employees have a non-null
-- engagement_score in v_attrition_features.
--
-- Win condition for paw-prey-006: the generator produces quarterly surveys
-- at a rate that should cover ~80-85% of active employees. 60% is the
-- realistic floor for a "low-response shop" — documented as an EDA finding
-- for Loop 2 missingness handling.
--
-- Returns 0 rows on pass (coverage ≥ 60%). Returns 1 row on fail (< 60%),
-- which causes dbt test to report a failure.
select
    sum(case when engagement_score is not null then 1 else 0 end) as non_null_count,
    count(*)                                                       as total,
    sum(case when engagement_score is not null then 1 else 0 end)
        * 100.0 / nullif(count(*), 0)                             as coverage_pct
from {{ ref('v_attrition_features') }}
having
    sum(case when engagement_score is not null then 1 else 0 end)
        * 100.0 / nullif(count(*), 0) < 60
