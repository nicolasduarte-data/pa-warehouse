-- scripts/parity_check.sql — multi-vendor parity validation for pa-warehouse.
--
-- PURPOSE:
-- Run this query against BOTH BigQuery and Snowflake. The result row should
-- be identical (row count exact, summary statistics within 0.1% relative
-- tolerance). Any column-level deltas surface here, at the data layer, before
-- they corrupt downstream ML training or dashboard renders.
--
-- WHY THIS QUERY IS THE RIGHT PARITY TEST:
-- Comparing schemas (information_schema) catches structural drift but not
-- DATA drift. Comparing every row by employee_id catches data drift but
-- masks numerical precision differences. This query lives in the middle —
-- it asserts that the AGGREGATE statistics the ML model will compute on
-- v_attrition_features are equivalent across vendors. If row_count, label
-- proportion, and feature distributions match, the trained model would be
-- materially identical.
--
-- CROSS-DIALECT SQL:
-- Only standard SQL functions used — runs unchanged on both BigQuery and
-- Snowflake. SUM(CASE WHEN ... THEN 1 ELSE 0 END) is the portable boolean-
-- counting idiom; SUM(boolean) is not portable. STDDEV is supported on both.
--
-- HOW TO RUN:
--   BigQuery:  paste into BigQuery console; or `bq query --use_legacy_sql=false <sql>`
--   Snowflake: paste into a Snowsight worksheet
--
-- HOW TO COMPARE:
-- The two result rows should match column-by-column. Acceptable deltas:
--   - row_count, employee_count, label_positive_count: EXACT match required
--   - All AVG / STDDEV / MIN / MAX numeric stats: within 0.1% relative
--     tolerance (abs(bq - sf) / abs(bq) < 0.001)
--   - Date columns: exact match
--
-- If anything fails, common causes are SCD2 snapshot timing, COPY INTO
-- row-skip on bad data, or floating-point precision (rare with NUMERIC columns).

SELECT
    -- ── Identity ──────────────────────────────────────────────────────────
    'v_attrition_features' AS table_name,
    COUNT(*)               AS row_count,
    COUNT(DISTINCT employee_id) AS employee_count,

    -- ── Snapshot window (should match on both targets) ───────────────────
    MIN(snapshot_date) AS min_snapshot_date,
    MAX(snapshot_date) AS max_snapshot_date,

    -- ── Label balance ────────────────────────────────────────────────────
    -- voluntary_exit_label is BOOL. SUM(boolean) is not portable; use CASE.
    SUM(CASE WHEN voluntary_exit_label THEN 1 ELSE 0 END) AS label_positive_count,
    AVG(CASE WHEN voluntary_exit_label THEN 1.0 ELSE 0.0 END) AS label_positive_rate,

    -- ── Continuous feature distributions ─────────────────────────────────
    MIN(tenure_months)    AS min_tenure_months,
    MAX(tenure_months)    AS max_tenure_months,
    AVG(tenure_months)    AS avg_tenure_months,
    STDDEV(tenure_months) AS std_tenure_months,

    MIN(compa_ratio)      AS min_compa_ratio,
    MAX(compa_ratio)      AS max_compa_ratio,
    AVG(compa_ratio)      AS avg_compa_ratio,
    STDDEV(compa_ratio)   AS std_compa_ratio,

    -- ── Age column ───────────────────────────────────────────────────────
    MIN(age_at_window_close)    AS min_age,
    MAX(age_at_window_close)    AS max_age,
    AVG(age_at_window_close)    AS avg_age,
    STDDEV(age_at_window_close) AS std_age,

    -- ── Categorical distributions ────────────────────────────────────────
    SUM(CASE WHEN gender = 'M'  THEN 1 ELSE 0 END) AS count_gender_m,
    SUM(CASE WHEN gender = 'F'  THEN 1 ELSE 0 END) AS count_gender_f,
    SUM(CASE WHEN gender = 'NB' THEN 1 ELSE 0 END) AS count_gender_nb,

    SUM(CASE WHEN is_critical_role THEN 1 ELSE 0 END) AS count_critical_role,

    -- successor_count is INT64 — full distribution stats
    MIN(successor_count)    AS min_successor_count,
    MAX(successor_count)    AS max_successor_count,
    AVG(successor_count)    AS avg_successor_count

FROM marts.v_attrition_features;
