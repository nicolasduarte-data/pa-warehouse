-- stg_compensation — compensation history per employee.
--
-- Multiple rows per employee — one per compensation event (initial hire salary
-- plus any subsequent changes). 5,609 rows for 2,500 employees means ~2.2
-- comp events per employee over the 36-month observation window.
--
-- The most recent record per employee (MAX(effective_date)) represents their
-- current compensation. Core models that need point-in-time comp (e.g.,
-- fact_compensation_snapshot) join on effective_date ranges using window
-- functions — do that in the core layer, not here.

{{ config(materialized='view') }}

select
    -- ── Keys ────────────────────────────────────────────────────────────────
    comp_id,
    employee_id,

    -- ── Compensation attributes ──────────────────────────────────────────────
    effective_date,

    -- salary in USD. FLOAT64 in raw to handle any fractional values, though
    -- the generator currently produces whole-dollar amounts.
    salary,
    currency,
    pay_band_id,

    -- compa_ratio = salary / band_midpoint at this effective date.
    -- 1.00 = exactly at midpoint; >1.00 = above; <1.00 = below.
    -- The generator centers this at 1.00 with std dev ~0.08.
    compa_ratio

from {{ source('raw', 'compensation') }}
