-- stg_employees_current — current state of every employee.
--
-- One row per employee. This is a point-in-time snapshot at window-close
-- (2026-03-31), not a historical record. The name "current" distinguishes
-- it from the SCD2 dim_employee snapshot which tracks full attribute history.
--
-- Downstream models that need an employee's current org position (e.g.,
-- dim_employee snapshot, fact_compensation_snapshot) reference this model
-- via ref('stg_employees_current') -- never source() directly.
-- That indirection means we can change the raw schema in one place (here)
-- without touching every downstream model.

{{ config(materialized='view') }}

select
    -- ── Identity ────────────────────────────────────────────────────────────
    employee_id,
    first_name,
    last_name,
    email,

    -- ── Demographics ────────────────────────────────────────────────────────
    -- gender is a Type 1 attribute — does not change over employee tenure in
    -- this synthetic dataset. It is NOT a check_col in the SCD2 snapshot.
    gender,

    -- birth_date + age_at_hire (paw-prey-005 Story 5.2.1) — both immutable per
    -- employee. They flow through to dim_employee_snapshot as Type 1 attrs (NOT
    -- in check_cols — they cannot change, so the SCD2 engine should never see
    -- a "change" event on them). Downstream marts (v_attrition_features) use
    -- birth_date to compute age_at_window_close at any snapshot_date.
    birth_date,
    age_at_hire,

    -- ── Org position ────────────────────────────────────────────────────────
    -- These four FK columns drive the SCD2 snapshot (dim_employee). Changes
    -- in any of them should generate a new SCD2 history row.
    dept_id,
    job_id,
    location_id,

    -- manager_id is nullable: top-level employees (CEO tier) have no manager.
    -- The SCD2 snapshot wraps this with COALESCE('__NO_MGR__') to prevent
    -- the NULL = NULL silent-row-duplication bug.
    manager_id,

    -- ── Dates ───────────────────────────────────────────────────────────────
    hire_date,

    -- exit_date and exit_type are NULL for active employees. Downstream models
    -- that compute attrition use IS NULL / IS NOT NULL rather than a status flag.
    exit_date,
    exit_type,

    -- ── Performance + compensation snapshot ─────────────────────────────────
    -- perf_tier (1–5 integer) is the performance tier at window-close.
    -- Renamed to performance_tier so downstream SQL reads naturally.
    perf_tier   as performance_tier,

    -- compa_ratio = current salary / band midpoint. Centered at 1.00.
    compa_ratio

from {{ source('raw', 'employees') }}
