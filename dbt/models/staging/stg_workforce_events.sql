-- stg_workforce_events — typed and validated workforce event stream.
--
-- One row per event. Events are the source of truth for employee lifecycle:
-- hire → optional attribute changes → optional termination. The SCD2
-- dim_employee snapshot reads from stg_employees_current (point-in-time),
-- but retention-analysis models trace event timelines from this table.
--
-- is_regrettable is only meaningful on term_voluntary rows. It is False
-- (not NULL) on all other event types — the generator stamps every row.
-- Downstream models that compute regrettable-attrition rates should first
-- filter WHERE event_type = 'term_voluntary'.

{{ config(materialized='view') }}

select
    -- ── Keys ────────────────────────────────────────────────────────────────
    event_id,
    employee_id,

    -- ── Event attributes ────────────────────────────────────────────────────
    event_date,
    event_type,

    -- is_regrettable: CPT-sampled at generation (E[reg | vol_exit] = 0.30).
    -- The flag is the canonical truth label — the marts layer SELECTs it
    -- rather than re-deriving it from an OR-rule (Story 3.2 in BACKLOG).
    is_regrettable,

    -- ── Derived convenience columns ──────────────────────────────────────────
    -- These are the two event categories used across most attrition analyses.
    -- Materializing them here avoids repeating the CASE logic in every downstream
    -- model.
    (event_type = 'term_voluntary')   as is_voluntary_term,
    (event_type = 'term_involuntary') as is_involuntary_term,
    (event_type in ('term_voluntary', 'term_involuntary')) as is_any_term,
    (event_type = 'hire')             as is_hire

from {{ source('raw', 'workforce_events') }}
