# pa-warehouse — Status and Engineering Notes

> What's shipped, what isn't, and the decisions behind the build.
> For the live dashboard and reproduction steps see [README.md](./README.md).

Last updated: 2026-10-22

---

## Status

| Component | State |
|---|---|
| Synthetic generator + 5-layer validation harness | Shipped 2026-05-20 |
| BigQuery warehouse: staging, core with SCD2 snapshot, marts | Shipped 2026-05-20 |
| 2-page Looker Studio dashboard on a live connection | Shipped 2026-05-20 |
| `marts.v_attrition_features` ML feature view, contract-enforced | Shipped 2026-05-20; survey columns added 2026-05-28 |
| Snowflake port + 26-column parity check | Parity passed 2026-05-22; code and evidence published 2026-10-21 |
| Dashboard pages for a compa-ratio heatmap, a pay-equity regression and workforce movement | Not built |
| Retention-model predictions written back to BigQuery and shown on the dashboard | Not built |
| Single-command rebuild | Not built; the pipeline runs step by step ([How to reproduce](./README.md#how-to-reproduce)) |

---

## Engineering Decisions

- **Live BigQuery connection, not extract.** No 100MB cap, no manual refresh, dashboard always reflects current state. Cost-controlled via BigQuery's 1TB/month free-tier query budget plus a `maximum_bytes_billed` guardrail in `profiles.yml`.
- **SCD2 `dim_employee` via `dbt snapshot` with COALESCE NULL-safety.** The classic SCD2 gotcha — `NULL = NULL` evaluates to NULL, silently duplicating rows on every snapshot run for any NULL-bearing employee — is mitigated by wrapping nullable check columns with sentinel values. Validated via a NULL-stability test (re-running snapshot produces zero new rows).
- **Dynamic `dim_date` observation window.** The window auto-detects from `fact_workforce_events.event_date` min/max. The generator is non-deterministic (`window_end = today`), so any hardcoded window drifts. Computing dynamically keeps the dim and the data permanently in sync.
- **dbt model contracts on `v_attrition_features`.** Schema drift breaks the dbt build, not the downstream training notebook. This is the entire reason dbt 1.5+ added contracts — make the warehouse fail loudly so consumers don't fail silently.
- **`dbt-project-evaluator` runs every build.** Code-quality auditor checking naming conventions, test coverage, documentation coverage, and model dependency hygiene. Output routed to its own dataset so it doesn't pollute the source-table namespace.
- **Three-layer synthetic generator.** `scipy.stats.lognorm` for tenure-at-exit (humped HR hazard shape), Gaussian copula for continuous correlations across performance/comp/tenure, CPT for the IsRegrettableFlag calibration. No synthetic-data library, so every distribution choice is in the code.
- **5-layer validation harness.** Scalars (10 benchmark targets) + Hellinger distance (distributional fidelity, threshold 0.12) + Kaplan-Meier (survival-curve median 2.4yr ± 0.4) + Spearman (correlation matrix preservation ± 0.05) + FK integrity (zero orphan records). Runs in `generator/validate.py` before any data is loaded.

---

## Bugs Caught Before Shipping

Issues found during the build that would have silently broken downstream consumers:

1. **N:M fanout in marts views' FULL OUTER JOIN.** When two CTEs share a GROUP BY column list, the JOIN keys must include ALL of those columns — missing keys silently inflate aggregates by the average count of unmatched grouping-dim values per join key. Caught a 2.33× headcount inflation before shipping.
2. **Hardcoded observation windows drift out of sync with non-deterministic generators.** Replaced with a dynamic computation from `fact_workforce_events` min/max event_date so `dim_date` self-adjusts on every build.
3. **Pre-window event leakage in stock+flow joins.** FULL OUTER JOINs between a stock CTE (filtered by month_spine) and a flow CTE (unfiltered) created ghost rows at the time-series edges. Fixed via INNER JOIN of the flow CTE to month_spine before the outer join.
