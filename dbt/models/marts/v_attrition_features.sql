-- v_attrition_features — employee-grain ML training input for the retention
-- prediction model (downstream consumer).
--
-- ── Grain ────────────────────────────────────────────────────────────────────
-- One row per employee who was ACTIVE at `snapshot_date`. Inactive employees
-- (already exited before snapshot OR not yet hired) are excluded.
--
-- ── Label ────────────────────────────────────────────────────────────────────
-- `voluntary_exit_label` = TRUE if the employee voluntarily exited within
-- 12 months after `snapshot_date`. FALSE otherwise.
--
-- Why 12 months and not 90 days:
-- 12-month forward retention is the industry standard for portfolio-tier
-- retention models. Class balance lands ~14-20% positive (matches the
-- generator's ~14.1% annual attrition rate, modulo year-specific variance),
-- giving the retention model a workable training set without aggressive
-- resampling.
--
-- ── Parameterization ─────────────────────────────────────────────────────────
-- `snapshot_date` is parameterizable via dbt var so the retention model can
-- train on multiple point-in-time snapshots and avoid label leakage:
--   dbt run --select v_attrition_features --vars '{"snapshot_date": "2025-01-01"}'
-- Default: 12 months before current_date — guarantees the label window has
-- fully elapsed (no still-unfolding labels).
--
-- ── Leakage prevention ───────────────────────────────────────────────────────
-- Features are derived from employee state AS OF snapshot_date. The label
-- looks ONLY at exits between snapshot_date and snapshot_date + 12 months.
-- Pre-snapshot exits are not in the active cohort, post-12-month exits are
-- censored to FALSE (we don't know yet — conservative).
--
-- ── Contract enforcement ─────────────────────────────────────────────────────
-- Schema enforced via `_marts.yml` — column type drift breaks the build at
-- `dbt run`, not at training time.

{# Contract enforcement: BigQuery is the primary target — schema contracts
   are enforced there to catch type drift at build time. On Snowflake (validation
   port) we skip contract enforcement because the YAML data_type values
   (int64, float64) are BigQuery-specific and don't map to Snowflake's
   physical column types after casting via dbt.type_int() / dbt.type_float().
   This keeps the same _marts.yml schema working for both targets without
   maintaining two parallel contracts. #}
{{ config(
    materialized = 'view',
    contract     = {'enforced': target.type == 'bigquery'}
) }}

with

-- Parameterizable anchor date. Default: 12 months ago.
--
-- Implementation note (paw-prey-006 fix):
-- dbt.dateadd compiles to datetime_add(cast(current_date() as datetime), ...)
-- which returns DATETIME, not DATE. The original COALESCE pattern cast that
-- DATETIME to STRING ('2025-05-28 00:00:00') and then cast to DATE, but
-- BigQuery's DATE cast requires strict 'YYYY-MM-DD' format and rejects the
-- time component — raising "Invalid date: '2025-05-28 00:00:00'" at query
-- execution time. Fixed with CASE WHEN to avoid the string intermediate:
-- cast(DATETIME as DATE) truncates the time component in both BQ and Snowflake.
snapshot_anchor as (
    select
        case
            when nullif('{{ var("snapshot_date", "") }}', '') is not null
            then cast(nullif('{{ var("snapshot_date", "") }}', '') as date)
            else cast({{ dbt.dateadd('month', -12, 'current_date()') }} as date)
        end as snapshot_date
),

employees as (
    select
        employee_id,
        hire_date,
        exit_date,
        exit_type,
        job_id,
        performance_tier,
        compa_ratio,
        -- birth_date + gender added per paw-prey-005 Story 5.2.2 (rp Epic 1
        -- preconditions). birth_date enables age_at_window_close downstream;
        -- gender is the compound-fairness attribute for rp Epic 5.
        birth_date,
        gender
    from {{ ref('stg_employees_current') }}
),

jobs as (
    select job_id, is_critical_role
    from {{ ref('dim_job') }}
),

succession as (
    -- successor_readiness_count = number of ready successors for this employee's
    -- role. Higher = more replaceable. NULL handled via coalesce(...,0) below.
    select employee_id, successor_readiness_count
    from {{ source('raw', 'succession_plan') }}
),

-- Employees active at snapshot_date — passed the hire gate, hasn't exited yet.
active_at_snapshot as (
    select e.*, s.snapshot_date
    from employees e
    cross join snapshot_anchor s
    where e.hire_date <= s.snapshot_date
      and (e.exit_date is null or e.exit_date > s.snapshot_date)
),

-- Survey signals aggregated to employee-snapshot grain (paw-prey-006).
-- Leakage gate: only include responses with survey_date <= snapshot_date.
-- Intentionally nullable — employees with no surveys before snapshot_date
-- get NULL, which is valid signal for Loop 2 missingness analysis.
-- Coverage expectation: ≥60% of active employees have non-null values
-- (enforced by dbt_utils.expression_is_true test in _marts.yml).
survey_signals as (
    select
        sr.employee_id,
        -- Per-employee eNPS: (promoters - detractors) / total × 100, cast INT64.
        -- CASE WHEN used for cross-dialect boolean-to-int (BQ + Snowflake safe).
        cast(
            round(
                cast(
                    sum(case when sr.is_promoter  then 1 else 0 end)
                    - sum(case when sr.is_detractor then 1 else 0 end)
                as {{ dbt.type_float() }})
                / nullif(count(*), 0) * 100
            ) as {{ dbt.type_int() }}
        ) as enps,
        -- Average engagement rating across all surveys ≤ snapshot_date.
        cast(avg(sr.engagement_score)          as {{ dbt.type_float() }}) as engagement_score,
        -- Average manager relationship rating across all surveys ≤ snapshot_date.
        cast(avg(sr.manager_relationship_score) as {{ dbt.type_float() }}) as manager_relationship_score
    from {{ ref('fact_survey_responses') }} sr
    cross join snapshot_anchor sa
    where cast(sr.survey_date as date) <= cast(sa.snapshot_date as date)
    group by sr.employee_id
)

select
    -- ── Identity / partition key ─────────────────────────────────────────────
    cast(a.employee_id as string) as employee_id,
    cast(a.snapshot_date as date) as snapshot_date,

    -- ── Features ─────────────────────────────────────────────────────────────
    -- date_diff dialect (paw-prey-005 Story 5.6):
    --   BQ: date_diff(end_date, start_date, part) — END first
    --   Snowflake: datediff(part, start_date, end_date) — END last
    -- dbt.datediff signature is (start, end, part) — abstracts both.
    cast({{ dbt.datediff('a.hire_date', 'a.snapshot_date', 'month') }} as {{ dbt.type_int() }}) as tenure_months,
    cast(a.performance_tier as string) as performance_tier,
    cast(a.compa_ratio as {{ dbt.type_float() }}) as compa_ratio,
    cast(j.is_critical_role as {{ dbt.type_boolean() }}) as is_critical_role,
    cast(coalesce(sp.successor_readiness_count, 0) as {{ dbt.type_int() }}) as successor_count,

    -- ── Age + demographic features (paw-prey-005 Story 5.2.2) ─────────────
    -- age_at_window_close = age in completed-ish years at snapshot_date.
    -- We use ROUND(date_diff(DAY) / 365.25) instead of DATE_DIFF(YEAR) because:
    --   1) DATE_DIFF(date_a, date_b, YEAR) in BigQuery returns calendar-year
    --      subtraction (EXTRACT(YEAR FROM a) - EXTRACT(YEAR FROM b)), which
    --      overcounts by 1 for employees whose birthday hasn't yet passed in
    --      the snapshot year. ROUND on the day-precise difference avoids that.
    --   2) The generator built birth_date with the same 365.25 average, so the
    --      mart's arithmetic mirrors the source — no semantic drift between
    --      age_at_hire (integer in the source) and age_at_window_close (here).
    --   3) Snowflake-portability: ROUND + day-difference + 365.25 is the same
    --      pattern in both dialects (Snowflake uses DATEDIFF(DAY, b, a) — same
    --      result, different arg order — handled in Story 5.6's port pass).
    cast(round({{ dbt.datediff('a.birth_date', 'a.snapshot_date', 'day') }} / 365.25) as {{ dbt.type_int() }})
        as age_at_window_close,
    cast(a.gender as string) as gender,

    -- ── Survey features (paw-prey-006) ───────────────────────────────────────
    -- Aggregated over all survey responses ≤ snapshot_date (leakage boundary).
    -- NULL when no survey responses exist before snapshot_date — valid signal.
    ss.enps,
    ss.engagement_score,
    ss.manager_relationship_score,

    -- ── Label ────────────────────────────────────────────────────────────────
    -- TRUE iff the employee voluntarily exited within 12 months AFTER snapshot.
    -- Uses exit_type from stg_employees_current (string: 'term_voluntary' /
    -- 'term_involuntary' / NULL for active). This matches the convention used
    -- in v_attrition_analysis and is_voluntary_term in fact_workforce_events.
    cast(
        case
            when a.exit_date is not null
             and a.exit_date >  a.snapshot_date
             and a.exit_date <= {{ dbt.dateadd('month', 12, 'a.snapshot_date') }}
             and a.exit_type =  'term_voluntary'
            then true
            else false
        end
        as {{ dbt.type_boolean() }}
    ) as voluntary_exit_label

from active_at_snapshot a
left join jobs j on a.job_id = j.job_id
left join succession sp on a.employee_id = sp.employee_id
left join survey_signals ss on a.employee_id = ss.employee_id
