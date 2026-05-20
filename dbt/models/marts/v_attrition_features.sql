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

{{ config(
    materialized = 'view',
    contract     = {'enforced': true}
) }}

with

-- Parameterizable anchor date. Default: 12 months ago.
snapshot_anchor as (
    select cast(
        coalesce(
            nullif('{{ var("snapshot_date", "") }}', ''),
            cast(date_sub(current_date(), interval 12 month) as string)
        ) as date
    ) as snapshot_date
),

employees as (
    select
        employee_id,
        hire_date,
        exit_date,
        exit_type,
        job_id,
        performance_tier,
        compa_ratio
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
)

select
    -- ── Identity / partition key ─────────────────────────────────────────────
    cast(a.employee_id as string) as employee_id,
    cast(a.snapshot_date as date) as snapshot_date,

    -- ── Features ─────────────────────────────────────────────────────────────
    cast(date_diff(a.snapshot_date, a.hire_date, month) as int64) as tenure_months,
    cast(a.performance_tier as string) as performance_tier,
    cast(a.compa_ratio as float64) as compa_ratio,
    cast(j.is_critical_role as bool) as is_critical_role,
    cast(coalesce(sp.successor_readiness_count, 0) as int64) as successor_count,

    -- ── Label ────────────────────────────────────────────────────────────────
    -- TRUE iff the employee voluntarily exited within 12 months AFTER snapshot.
    -- Uses exit_type from stg_employees_current (string: 'term_voluntary' /
    -- 'term_involuntary' / NULL for active). This matches the convention used
    -- in v_attrition_analysis and is_voluntary_term in fact_workforce_events.
    cast(
        case
            when a.exit_date is not null
             and a.exit_date >  a.snapshot_date
             and a.exit_date <= date_add(a.snapshot_date, interval 12 month)
             and a.exit_type =  'term_voluntary'
            then true
            else false
        end
        as bool
    ) as voluntary_exit_label

from active_at_snapshot a
left join jobs j on a.job_id = j.job_id
left join succession sp on a.employee_id = sp.employee_id
