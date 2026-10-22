-- stg_succession_plan — successor readiness per employee at window-close.
--
-- One row per employee. Point-in-time snapshot, not historical.
-- Used in two downstream contexts:
--   1. IsRegrettableFlag (marts): critical roles with 0 successors = highest risk
--   2. Workforce Overview dashboard (Page 1): succession coverage KPI
--
-- is_critical_role here is the ROLE-level flag from the succession perspective
-- (matches jobs.is_critical_role for the same employee's current job).
-- Having it on this table avoids a redundant dim_job join in marts models
-- that only need the criticality × successor-count combination.

{{ config(materialized='view') }}

select
    -- ── Keys ────────────────────────────────────────────────────────────────
    succession_id,
    employee_id,

    -- ── Succession attributes ────────────────────────────────────────────────
    -- successor_readiness_count: number of ready successors for this employee's
    -- role. 0 = single point of failure — highest IsRegrettableFlag probability
    -- per the CPT (P(reg=1 | critical, successor_count=0) ≈ 0.85).
    successor_readiness_count,

    -- is_critical_role: True if the employee occupies a role flagged as critical.
    -- Denormalized from jobs.is_critical_role at generation time.
    is_critical_role,

    -- ── Derived convenience column ───────────────────────────────────────────
    -- Single-point-of-failure flag: True when critical AND no ready successors.
    -- The combination is what drives the highest regrettable-attrition risk.
    (is_critical_role and successor_readiness_count = 0) as is_succession_risk

from {{ source('raw', 'succession_plan') }}
