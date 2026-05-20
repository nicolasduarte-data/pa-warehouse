# pa-warehouse — Roadmap

> Quick reference for what's shipped, what's in progress, and what's planned.
> For the live dashboard see [README.md](./README.md).

---

## Current Status

**Phase 4 — Polish & Publish (in progress)** · Last update: 2026-05-20

The data warehouse and dashboard are **live and reconciling end-to-end.** The remaining Phase 4 work is repository hygiene, documentation polish, and the public announcement. The ML feature view (`marts.v_attrition_features`) is shipped with an enforced dbt contract — the downstream retention prediction project can begin training without further dependencies.

---

## Phased Build Plan

Each phase ends with a shippable public artifact. If a phase slips, the prior phase's artifact stays live.

| Phase | Theme | Deliverable | Status |
|---|---|---|---|
| 1 | Walking Skeleton | GCP + dbt scaffolding + tiny generator (50 employees) + one dashboard chart proving end-to-end | ✅ shipped |
| 2 | Full source data + core layer | 2,500-employee generator + 5-layer validation harness + complete dbt staging/core/marts pipeline + SCD2 `dim_employee` snapshot + 2 dashboard pages with real benchmark-aligned data | ✅ shipped |
| 3 | Differentiating dashboard views | IsRegrettableFlag surfaced, compa-ratio heatmap, progressive OLS pay equity panel, workforce movement page | ⏸ deferred — Wave 2 work, not on critical path |
| 4 | Polish + publish + ML handoff | Custom palette, README polish, dbt-docs site, schema hygiene cleanup, `v_attrition_features` ML feature view, LinkedIn announcement | 🚧 in progress |
| 5 | Snowflake validation port | `dbt build --target snowflake` parity demo; cross-vendor compatibility proof | 📋 planned |
| 6 | Retention prediction integration | Downstream ML model trains on `v_attrition_features`, writes predictions back to BigQuery, surfaces them in a new dashboard page | 📋 planned |

---

## Engineering Decisions Worth Calling Out

These are the choices that shaped the warehouse and that hiring managers tend to ask about:

- **Live BigQuery connection, not extract.** No 100MB cap, no manual refresh, dashboard always reflects current state. Cost-controlled via BigQuery's 1TB/month free-tier query budget plus a `maximum_bytes_billed` guardrail in `profiles.yml`.
- **SCD2 `dim_employee` via `dbt snapshot` with COALESCE NULL-safety.** The classic SCD2 gotcha — `NULL = NULL` evaluates to NULL, silently duplicating rows on every snapshot run for any NULL-bearing employee — is mitigated by wrapping nullable check columns with sentinel values. Validated via a NULL-stability test (re-running snapshot produces zero new rows).
- **Dynamic `dim_date` observation window.** The window auto-detects from `fact_workforce_events.event_date` min/max. The generator is non-deterministic (`window_end = today`), so any hardcoded window drifts. Computing dynamically keeps the dim and the data permanently in sync.
- **dbt model contracts on `v_attrition_features`.** Schema drift breaks the dbt build, not the downstream training notebook. This is the entire reason dbt 1.5+ added contracts — make the warehouse fail loudly so consumers don't fail silently.
- **`dbt-project-evaluator` runs every build.** Code-quality auditor checking naming conventions, test coverage, documentation coverage, and model dependency hygiene. Output routed to its own dataset so it doesn't pollute the source-table namespace.
- **Three-layer synthetic generator.** `scipy.stats.lognorm` for tenure-at-exit (humped HR hazard shape), Gaussian copula for continuous correlations across performance/comp/tenure, CPT for the IsRegrettableFlag calibration. Not a black-box library — every line is auditable.
- **5-layer validation harness.** Scalars (10 benchmark targets) + Hellinger distance (distributional fidelity, threshold 0.12) + Kaplan-Meier (survival-curve median 2.4yr ± 0.4) + Spearman (correlation matrix preservation ± 0.05) + FK integrity (zero orphan records). Runs in `generator/validate.py` before any data is loaded.

---

## Key Bugs Caught + Fixed

Notable issues found during the build that would have silently broken downstream consumers:

1. **N:M fanout in marts views' FULL OUTER JOIN.** When two CTEs share a GROUP BY column list, the JOIN keys must include ALL of those columns — missing keys silently inflate aggregates by the average count of unmatched grouping-dim values per join key. Caught a 2.33× headcount inflation before shipping.
2. **Hardcoded observation windows drift out of sync with non-deterministic generators.** Replaced with a dynamic computation from `fact_workforce_events` min/max event_date so `dim_date` self-adjusts on every build.
3. **Pre-window event leakage in stock+flow joins.** FULL OUTER JOINs between a stock CTE (filtered by month_spine) and a flow CTE (unfiltered) created ghost rows at the time-series edges. Fixed via INNER JOIN of the flow CTE to month_spine before the outer join.

---

## What's Next

**Phase 4 remaining work:**
- Custom Looker Studio palette applied to both dashboard pages — satisfied via per-chart deliberate color choices (see [README.md](./README.md) Architecture section for canonical palette)
- Final commit history polish + LinkedIn announcement

**Phase 6 entry point:**
- `marts.v_attrition_features` is live, contract-enforced, sample queries documented in README. The retention prediction model can start consuming it immediately.

---

## Reproducibility

Full pipeline reproduction steps live in [README.md "How to reproduce"](./README.md#how-to-reproduce). Single-command rebuild is on the Phase 4 backlog.
