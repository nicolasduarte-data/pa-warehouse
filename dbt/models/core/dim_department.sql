-- dim_department — one row per department. Type 1 (no history tracked).
--
-- Type 1 means: if a department name changes, we overwrite the old value.
-- We don't keep the historical name. For this synthetic dataset that's fine —
-- departments are stable reference data, not changing entities.
--
-- Includes a phantom row for '__NO_DEPT__'. This sentinel value is used by
-- the SCD2 dim_employee snapshot (Story 2.8) via COALESCE(dept_id, '__NO_DEPT__').
-- Without a matching row here, the relationships test in _core.yml would fail
-- for any employee who briefly had no department assigned (e.g., pre-onboarding).

{{ config(materialized='table') }}

with source as (
    select * from {{ ref('stg_employees_current') }}
),

departments as (
    select * from {{ source('raw', 'departments') }}
),

-- Phantom row: represents "no department assigned". The SCD2 snapshot uses
-- COALESCE(dept_id, '__NO_DEPT__') so NULL dept_ids map here instead of
-- orphaning in the relationships test.
sentinel as (
    select
        '__NO_DEPT__'              as dept_id,
        'Sentinel — source NULL'   as dept_name
)

select dept_id, dept_name from departments
union all
select dept_id, dept_name from sentinel
