{% snapshot dim_employee_snapshot %}

{{- config(
    target_schema='core',
    strategy='check',
    unique_key='employee_id',
    check_cols=['dept_id_safe', 'job_id', 'manager_id_safe', 'location_id_safe'],
    dbt_valid_to_current="cast('9999-12-31' as timestamp)"
) -}}

-- Source: stg_employees_current — one row per employee, current state only.
-- The snapshot engine handles the SCD2 logic (insert / expire rows).
-- We only need to write the SELECT that returns each employee's current attributes.

select
    -- ── Stable identifier (unique_key) ───────────────────────────────────────
    -- employee_id never changes — it's the business key that links all history
    -- rows for the same person across time.
    employee_id,

    -- ── Type 1 attributes (pass-through, no history needed) ──────────────────
    -- These columns don't change over an employee's tenure in this synthetic
    -- dataset. They ride along on every SCD2 row but are NOT in check_cols —
    -- changes here won't trigger a new history row.
    first_name,
    last_name,
    email,
    hire_date,
    gender,        -- Type 1: static, never NULL (Story 2.1.0)

    -- birth_date + age_at_hire (paw-prey-005 Story 5.2.1) — both immutable
    -- by definition. A real HR system can correct a wrong DOB, but in this
    -- synthetic dataset the truth source is the generator's per-employee
    -- assignment, which never changes. NOT in check_cols (immutable cannot
    -- generate a "change" event); they ride along on every history row so
    -- downstream age computations work against any SCD2 version.
    birth_date,
    age_at_hire,

    -- ── Type 2 attributes — the ones that drive new SCD2 rows ────────────────
    -- job_id: changes on promotion or role change. NOT nullable — no COALESCE.
    job_id,

    -- dept_id: changes on department transfer. Nullable in rare pre-onboarding
    -- window. COALESCE maps NULL → '__NO_DEPT__' so the equality check is safe.
    coalesce(dept_id, '__NO_DEPT__')         as dept_id_safe,

    -- manager_id: changes on manager reassignment or org restructure. Nullable
    -- for top-level employees (CEO tier). 88 NULLs in this dataset (confirmed).
    coalesce(manager_id, '__NO_MGR__')       as manager_id_safe,

    -- location_id: changes on office transfer or remote-to-office transition.
    -- Nullable for employees in a remote-pending state at hire.
    coalesce(location_id, '__NO_LOC__')      as location_id_safe

from {{ ref('stg_employees_current') }}

{% endsnapshot %}
