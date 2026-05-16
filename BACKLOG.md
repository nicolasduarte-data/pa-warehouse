# pa-warehouse — Project Backlog (hrds/)

Production-grade people analytics data warehouse with Looker Studio dashboard.
Primary build on **BigQuery + dbt** (native Looker integration, permanent free tier,
consensus modern stack). Secondary validation port to **Snowflake + dbt** for
multi-vendor fluency signal via `dbt run --target snowflake`. Target: ship before
next Wave 1 application batch.

**Definition of Done for the project:**
- BigQuery warehouse deployed with three-layer architecture: `raw` → `core` → `marts`
- **dbt project** with sources, models, snapshots, generic tests — runnable via `dbt build`
- Five fact tables + Type 2 SCD `dim_employee` (via `dbt snapshot`) populated with benchmark-aligned synthetic data
- `IsRegrettableFlag` classification logic implemented in marts layer
- Looker Studio dashboard published (5 pages incl. retention predictions), publicly linkable, **permanent live artifact**
- Snowflake validation port complete — `dbt run --target snowflake` produces matching results, side-by-side screenshots
- rp-prey-001 integrated — reads `marts.v_attrition_features`, writes predictions back to BigQuery, surfaces in dashboard
- Public GitHub repo with dbt project, generator script, both warehouse profiles, deploy automation
- README with architecture diagram, dbt-generated lineage diagram, metric dictionary, multi-vendor narrative
- Repo + dashboard link in `career/portfolio-links.md`
- LinkedIn announcement post live
- CV Technical Skills updated (BigQuery, Snowflake, **dbt**, Looker Studio, dimensional modeling)

**Research foundation:**
- `research/sessions/2026-05-14_people-analytics-dw-standards/` — PA standards, benchmarks, IsRegrettableFlag definition (40 sources, complete)
- `research/sessions/2026-05-15_dbt-bigquery-portfolio-dw/` — implementation stack research, full synthesis (38 sources: 19 T1, 3 T2, 16 T3; `--technical` mode; complete 01_tldr + 02_overview + 03_deep-dive). Supersedes the 2026-05-14 stub.
- `research/sessions/2026-05-15_synthetic-hr-data-generation-methodology/` — generation methodology (20 Tier 1 academic sources, complete synthesis, `--technical` mode, `COVERAGE LIMITED` flag)
- `research/sessions/2026-05-15_pa-dashboard-design-pay-equity/` — dashboard design conventions + pay equity visualization (35 sources, balanced mode, complete synthesis)
- Campaign plan: `research/sessions/pa-warehouse-research-plan.md`

**Supersedes:** `work/queue/ups-prey-001-close-snowflake-looker-stack-gap.md`
**Prior reviews:** `work/reviews/hunt/pa-warehouse-backlog--r01--2026-05-14-1829.md`, `--r02--2026-05-14-1914.md`

---

## Stack Decisions (Resolved)

| Decision                     | Choice                                             | Rationale                                                                                                                                                            |
| ---------------------------- | -------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Primary warehouse            | **BigQuery**                                       | Native Looker Studio connector, permanent free tier (10GB / 1TB queries-mo), dashboard stays live indefinitely                                                       |
| BigQuery mode                | **Billing-enabled (credit card on file)**          | Sandbox mode imposes 60-day table expiry; billing-enabled = $0 expected cost under free-tier quotas + no expiry. Billing alert at $5 threshold.                      |
| Secondary warehouse          | **Snowflake**                                      | 2-day validation port — closes Snowflake ATS keyword filter, multi-vendor signal, Lattice/Rippling/Deel buyer match                                                  |
| BI tool                      | **Looker Studio**                                  | Free, public-link-able, native to BigQuery, ATS keyword                                                                                                              |
| **Transformation framework** | **dbt (dbt-bigquery + dbt-snowflake adapters)**    | Consensus modern data stack. Auto-generates lineage docs, SCD2 via `dbt snapshot`, dependency-ordered builds. Snowflake port (Loop 5) becomes a profile-target swap. |
| ELT loader                   | **`bq load` (BigQuery) + `COPY INTO` (Snowflake)** | Native bulk loaders. dbt handles only T, not EL.                                                                                                                     |
| Build sequencing             | **Iterative loops, not waterfall epics**           | Each loop ships a working public artifact — protects against scope slip mid-build                                                                                    |
| rp-prey-001 integration      | **Required (Loop 6)**                              | Headline narrative is end-to-end pipeline. Schema decisions in Loop 2-3 account for ML feature surfacing via `v_attrition_features`.                                 |
| Looker Studio connection mode | **Live (BigQuery native) — NOT extract**          | Research A: Live is correct for non-operational portfolio dashboards. Extract is for static historical data only. Default 12-hour cache, keep it. **No 100MB constraint applies** — that's an extract-mode limit. |
| dbt SCD2 strategy            | **`check` strategy + `COALESCE` on nullable cols** | Research A: `NULL = NULL` evaluates to `NULL`, which check strategy treats as "changed" — silently creates a new row on EVERY snapshot run for every employee with NULL columns. Mandatory fix: `COALESCE(nullable_col, -1)` in snapshot SELECT. Also adopt `dbt_valid_to_current: "cast('9999-12-31' as date)"` (dbt v1.9+). |
| Snowflake portability budget | **2–4 hours, 3 rewrite points**                    | Research A: QUALIFY is compatible (NOT a break). DATE_TRUNC argument order reversed (use `{{ date_trunc() }}` macro). GENERATE_DATE_ARRAY → dbt-utils `date_spine`. STRUCT/ARRAY not portable but unused in this project. |
| Generator library stack      | **`scipy.stats` + `faker` + custom copula/CPT**    | Research B (20 Tier 1 sources): Faker for nominal strings only; scipy.stats.lognorm for tenure (log-normal preferred over Weibull — humped hazard); Gaussian copula for continuous correlations; CPT (conditional probability table) for IsRegrettableFlag calibration. SDV/HMA rejected (documented referential integrity gaps + near-naive ML utility + no benchmark targeting). |
| Validation framework         | **TSTS + Hellinger + KM + Spearman + FK asserts**  | Research B: TSTR requires real data (unavailable) → use TSTS (hold 20% synthetic out at generation). Hellinger distance < 0.1 per column vs benchmark; Kaplan-Meier median at event ≈ 2.4yr; Spearman correlation matrix preservation; SQL FK assertions. SDMetrics not recommended — its benchmarks are not HR-tested. |
| Pay equity methodology       | **Progressive OLS (3+ model specifications)**      | Research C: Oaxaca-Blinder vs OLS is INCONCLUSIVE; OB only valuable if explainable in one plain-language sentence on the dashboard. Default: log-linear OLS with 3+ progressive specs (unadjusted → role-controlled → role+tenure+performance controlled), p-values shown. Demonstrates competency without over-engineering. |
| Dashboard page order         | **Overview → Attrition → Movement → Compensation** | Research C: page order is a narrative argument, not UX preference. Each page raises a question the next answers (baseline → risk → structural change → fairness). |
| KPI card pattern             | **Current value + prior period + delta indicator** | Research C: every KPI card on every page. Without contextual comparison, a card is a number; with it, the card tells a story. Separates enterprise design from student design before any chart is examined. |
| Pay gap presentation         | **Both unadjusted AND adjusted, with narrative**   | Research C: showing only one gap is analytically incomplete at the senior level. Unadjusted = representation equity; adjusted = equal pay for equal work. Their RELATIONSHIP is the analysis (e.g., 13% unadjusted → 2% adjusted = representation/progression problem, not pay problem). |
| Color palette                | **Custom palette, NOT Looker Studio default**      | Research C: replacing the default rainbow palette is the highest-ROI 30-minute investment for portfolio dashboard credibility. Sequential greens for "good," sequential reds for "concern," neutral grays for context. |

---

## Research Findings Applied (Sessions A + B)

**Session A — dbt-bigquery-portfolio-dw (TL;DR verbatim, 2026-05-15 rerun):** *"The technical implementation of your people analytics DW has well-documented answers for every angle. The single highest-risk item is the NULL comparison failure in dbt's check strategy — it will silently corrupt your SCD2 history if not handled, and it's not documented in official dbt docs. Fix it before your first snapshot run. Apply the COALESCE fix to your snapshot SELECT, enable BigQuery billing before touching snapshots, and complete your YAML files — those three moves cover 95% of the implementation risk and portfolio signal."*

Concrete applications:
- **SCD2 NULL silent corruption** → MANDATORY: `COALESCE(nullable_col, -1)` wrapper for every nullable check column in snapshot SELECT. Without this, every NULL-bearing employee gets a new SCD2 row on every nightly run. Story 2.8.2 specifies the wrap.
- **Sandbox blocks DML — Loop 1 prerequisite** → BigQuery sandbox mode blocks INSERT/UPDATE/DELETE/MERGE. `dbt snapshot` uses MERGE. **Enable billing BEFORE Story 1.5 (first dbt model)**, not just for table-expiry reasons. Story 1.2.1 wording strengthened.
- **`dbt_valid_to_current` config (v1.9+)** → Set `dbt_valid_to_current: "cast('9999-12-31' as date)"` in snapshot config to avoid `IS NULL` filtering in downstream models. Story 2.8.2.
- **`dbt snapshot --target` gotcha** → `dbt snapshot` runs against production schema regardless of `--target` flag. Guard CI runs with explicit conditional or separate project. Loop 4 deploy section.
- **Looker live connection — NOT extract** → BigQuery native + live mode is the right choice. **No 100MB constraint applies** (extract-mode-only limit). 12-hour default cache is correct for portfolio. Drops the Story 3.3 pre-aggregation-for-size requirement.
- **Snowflake portability is 2–4 hours, not 2 days** → Three rewrite points only: DATE_TRUNC argument order (reversed), GENERATE_DATE_ARRAY → date_spine, STRUCT/ARRAY (unused here). QUALIFY is compatible. Loop 5 budget may be reduced.
- **Portfolio senior signal** → YAML completeness + schema tests on every PK/FK + documented NULL mitigation in snapshot config + directory-level materializations in `dbt_project.yml`. Stories 1.3 + 2.8 explicit.

**Research A caveats:** THIN TOPIC flag on portfolio anti-patterns/hiring signals (practitioner consensus only, no Tier 1-2 coverage). `dbt_valid_to_current` is v1.9+ feature — verify version before adoption. GCP docs imply 60-day expiry removal on billing-enabled but don't explicitly state — billing IS still required regardless because of the DML block.

**Session B — synthetic-hr-data-methodology (TL;DR verbatim):** *"Build a custom three-layer Python generator — not SDV, not Faker. Use log-normal for tenure (μ=ln(2.4)), Gaussian copula + CPT for correlations, and a programmatic ordered event-chain for SCD2. The library choice and correlation methodology are both INCONCLUSIVE in the literature; a hybrid approach is the most defensible. Do not confuse TSTR (requires real data) with TSTS (your only option in a portfolio context)."*

Concrete applications:
- **Three-layer custom Python generator (no SDV)** → SDV/HMASynthesizer rejected: documented referential integrity gaps, near-naive ML utility, no benchmark targeting, only tested on IMDB/AirBnB schemas. Custom simulator: (1) marginal distributions per column via scipy.stats matched to benchmarks; (2) Gaussian copula for inter-column correlations; (3) parent-first hierarchical generation for referential integrity.
- **Log-normal for tenure (NOT Weibull)** → `scipy.stats.lognorm(s=0.9, scale=2.4)` for tenure-at-exit. Weibull is monotone-only; HR attrition is non-monotone (peaks early, declines). Story 2.1.1.
- **Two-population generation: terminated + right-censored** → 36-month observation window means ~64% of employees should be right-censored (still employed at window close). Standard generative models that ignore censoring produce unrealistic all-exits distributions. Story 2.1.1.
- **Gaussian copula for continuous correlations + CPT for IsRegrettableFlag** → Copula preserves arbitrary marginals; CPT (conditional probability table) calibrates discrete conditionals to the 30% regrettable benchmark. Story 2.3.
- **IsRegrettableFlag via logistic probability sampled AFTER predictors** → Generation order matters for leakage prevention: (1) generate predictor features (performance, compa_ratio, role_criticality, successor_count); (2) for voluntary exits, sample IsRegrettableFlag from `logistic(features)` calibrated to E[reg|vol_exit]=0.30; (3) the mart-layer OR-rule (Story 3.2) then derives the same flag descriptively. Both views consistent.
- **TSTS not TSTR** → True TSTR requires real labeled HR data (we have none). Use TSTS: hold out 20% synthetic at generation time, train baseline on 80%, evaluate on 20%. Story 2.5.3.
- **Hellinger + Kaplan-Meier + Spearman + FK validation** → Hellinger distance < 0.1 per column vs benchmark targets; Kaplan-Meier median at event ≈ 2.4yr; Spearman correlation matrix preservation; SQL FK assertions. Replaces SDMetrics. Story 2.5.4.
- **SCD2 ordered event-chain — no library does this** → Generate each employee as ordered sequence: hire → attribute changes → optional termination. Enforce `effective_date = prev_date + rand_days(7, 180)` programmatically. Story 2.4.

**Research B caveats (per session output):** `COVERAGE LIMITED` — 14 of 30 domain diversity floor; library choice and correlation methodology both INCONCLUSIVE in Scale Tip (equal credibility density). The hybrid copula+CPT recommendation is the practical synthesis. Log-normal preference is derived from medical/clinical literature — no HR-specific empirical validation exists. **Pilot test tenure distribution against the 2.4yr benchmark target before full generation.**

---

**Session C — pa-dashboard-design-pay-equity (TL;DR verbatim, 2026-05-15):** *"The difference between a PA portfolio dashboard that impresses a senior hiring manager and one that reads as student work is almost never the chart types — it's the analytical context embedded around every number. Use this research to build the `v_compensation_equity` page with both pay gap metrics and a progressive OLS regression; set the page order as baseline → risk → movement → fairness; and spend 30 minutes replacing Looker Studio's default palette before anything else."*

Concrete applications:
- **Page order is narrative, not UX preference** → Workforce Overview → Attrition Analysis → Workforce Movement → Compensation Equity. Each page raises a question the next answers. Loop 3 Stories 3.4/3.5/3.6 already use this order; reinforced now as deliberate.
- **KPI cards with contextual comparison on every page** → Every KPI = current value + prior-period value + directional indicator (arrow + colored % delta). Story 3.4.0 added. Loop 2 Story 2.10.0 added.
- **Compa-ratio heatmap as the highest-impact chart** → Color-coded (green 95-105%, yellow 85-94%/106-115%, red <85%/>115%), faceted by department × job family × demographic group. Story 3.6.1 rewritten as the lead chart for Page 4.
- **Both pay gap metrics, with narrative framing** → Unadjusted (representation equity) AND adjusted (equal pay for equal work). The relationship between them IS the analysis: 13% unadjusted → 2% adjusted = representation/progression problem, not pay problem. Story 3.6.2 specifies side-by-side presentation with explainer.
- **Progressive OLS regression** → 3+ model specifications: (1) gender alone, (2) + job_level, (3) + job_level + tenure + performance. Log-linear (log(salary) ~ predictors). p-values shown. Oaxaca-Blinder dropped per session's decision rule (only if explainable in one plain-language sentence on the dashboard — we cannot).
- **IsRegrettableFlag — 3-layer introduction on dashboard** → (a) data definition, (b) formula, (c) benchmark context using INTERNAL comparison (regrettable share as % of voluntary over time), NOT the LOW-CONFIDENCE 15% vendor threshold. Story 3.4.4 expanded.
- **Custom color palette before anything else** → Sequential greens for "good" (in-band compa-ratio, low attrition), sequential reds for "concern" (out-of-band compa-ratio, high attrition), neutral grays for context. Replace Looker Studio defaults. New Story 4.1.0.

**Research C caveats:** Enterprise design conventions derive primarily from vendor blogs (Visier, One Model) and practitioner training rather than independent cognitive studies — F-pattern layout assumption and Looker Studio design conventions are practitioner norms, not validated. The 15% regrettable attrition "alarm threshold" is LOW CONFIDENCE (single vendor source, no citation) — use internal benchmarking only.

**Session C evidentiary strength caveat (per r05 hunt review):** Session C's source profile is materially weaker than Sessions A and B. Session A had 19 Tier 1 sources (vendor docs, peer-reviewed); Session B had 20 Tier 1 (academic papers). **Session C has zero Tier 1 sources** — its 35 sources are 0 Tier 1 / ~12 Tier 2 (industry publications) / ~10 Tier 3 (expert blogs) / balanced mode. Apply Session C's design conventions as defaults, NOT as research-validated truths. Departures from these conventions are defensible when backed by clear rationale; do not treat them as rigid constraints. Specifically: the page-order argument, F-pattern layout, "overview-first" hierarchy, and KPI-card-pattern recommendations are practitioner consensus that may not survive cognitive-load research scrutiny.

---

## Loop Structure (Sequencing)

The build is organized into **6 loops**, not sequential epics. Each loop ends with a shippable
public artifact. If a loop slips, the prior loop's artifact remains live and complete.

| Loop | Days | Prey | Deliverable | Public artifact at end |
|---|---|---|---|---|
| 1 — Walking Skeleton | 1-3 | `paw-prey-001` | dbt project init + tiny generator + BigQuery + 1 model + 1 chart in Looker Studio | Repo live, dashboard live (minimal) |
| 2 — Full source data + core | 4-8 (5 days) | `paw-prey-002` | Full generator (~2,500 employees, 5 tables) + raw load + staging + dbt core models + `dim_employee` snapshot with COALESCE + 2 dashboard pages | Substantive dashboard with real data |
| 3 — Marts + differentiating metrics | 9-14 (re-budgeted r05) | `paw-prey-003` | All dbt marts models + IsRegrettableFlag SELECT + 4 differentiating dashboard views + compa-ratio heatmap + progressive OLS panel + 3-layer IsRegrettable intro | The "impressive" version exists |
| 4 — Polish + publish | 15-18 | `paw-prey-004` | Custom palette, filters, README polish, dbt docs site, dbt-project-evaluator report, LinkedIn post, portfolio link, CV update | Shipped + announced |
| 5 — Snowflake validation port | 19 (half-day) | `paw-prey-005` | `dbt build --target snowflake` succeeds, side-by-side screenshots, multi-vendor README section | Multi-vendor showcase |
| 6 — rp-prey-001 integration | 19-20 | `paw-prey-006` | rp-prey-001 reads from BigQuery, predictions written back, dashboard surfaces predictions | End-to-end pipeline narrative |

**Total honest estimate:** 20 calendar days of focused work. Loop 2 = 5 days (r04 re-budget: Gaussian copula + CPT + staging + COALESCE matrix + Hellinger/KM/Spearman). Loop 3 = 6 days (r05 re-budget: Session C added compa-ratio heatmap + progressive OLS panel + KPI strip + 3-layer IsRegrettable intro = ~3.5 days on top of original 9-day plan). Loop 5 = half-day per Research A (Snowflake port 2–4 hours). Run in parallel with other portfolio tracks per Nico's operating mode → realistic delivery 6–7 calendar weeks at parallel-track pace.

**Parallel-track adjustment:** Snowflake free trial setup (Story 5.1.1) runs *alongside* Loop 3
— registration is 5 minutes; Loop 5 port work doesn't depend on dashboard polish. Aligns the
Snowflake 30-day trial timer with port readiness.

---

## Loop 1 — Walking Skeleton (paw-prey-001)

*Tracer bullet. dbt project skeleton + tiny end-to-end. Public artifact by day 3.*

**Loop 1 Definition of Done:**
- GitHub repo exists with placeholder README labeled "v0.1 — Walking Skeleton complete"
- GCP project created with billing enabled, $5 alert configured
- dbt project initialized — `dbt_project.yml`, `profiles.yml`, `sources.yml` skeleton
- BigQuery project + 3 datasets (`raw`, `core`, `marts`)
- Generator produces 50 employees + minimal `workforce_events`
- `bq load` loads CSVs into `raw.employees` + `raw.workforce_events`
- One dbt model in `marts/` produces a small aggregation
- `dbt build` runs clean
- One Looker Studio chart renders the aggregation
- Dashboard is publicly accessible via shareable link

### STORY 1.1 — Project + repo skeleton
- [ ] 1.1.1 — Init `projects/hrds/pa-warehouse/` with `src/`, `generator/`, `dbt/`, `looker/`, `data/`, `docs/`
- [ ] 1.1.2 — `requirements.txt` with pinned versions (dbt 1.9+ required for `dbt_valid_to_current` config used in Story 2.8):
  ```
  pandas>=2.0,<3.0
  numpy>=1.24,<2.0
  scipy>=1.11,<2.0              # lognorm, Hellinger via scipy.spatial.distance
  faker>=22.0,<25.0             # string attrs only — names, emails
  scikit-learn>=1.4,<2.0        # TSTS baseline + Spearman (scipy.stats also fine)
  statsmodels>=0.14,<1.0        # Progressive OLS for pay equity (Story 3.6.3) — native p-values, log-linear
  pandas-gbq>=0.22              # Python ↔ BigQuery for OLS write-back (Story 4.4.1)
  google-cloud-bigquery>=3.20
  dbt-core>=1.9,<2.0
  dbt-bigquery>=1.9,<2.0
  dbt-snowflake>=1.9,<2.0
  ```
  **Removed (per Research B):** `lifelines` (we use scipy.stats.lognorm directly), `sdmetrics` (TSTS + Hellinger + KM + Spearman replace SDMetrics).
- [ ] 1.1.3 — `.gitignore` excludes binaries + credentials (`profiles.yml`, `*.json` service account keys)
- [ ] 1.1.4 — Create public GitHub repo, push skeleton
- [ ] 1.1.5 — README.md v0.1 with SYNTHETIC notice + "Walking Skeleton complete" label

### STORY 1.2 — GCP + BigQuery infrastructure
- [ ] 1.2.1 — Create GCP project `pa-warehouse-prod`, **enable billing IMMEDIATELY** (per Research A: sandbox mode blocks DML — INSERT/UPDATE/DELETE/MERGE — and `dbt snapshot` requires MERGE; this is not just a 60-day-expiry concern, it's a hard blocker for any snapshot run). Billing-enabled stays $0 under free-tier quotas.
- [ ] 1.2.2 — Set billing alert at $5 threshold (early warning, not a hard cap)
- [ ] 1.2.3 — Service account for loader + dbt with **both** `BigQuery Data Editor` + `BigQuery Job User` (per Research A: granting only one breaks either table creation or query execution — both are minimum required)
- [ ] 1.2.4 — Download service account JSON; reference path via env var (NOT committed)
- [ ] 1.2.5 — Enable BigQuery API; create datasets `raw`, `core`, `marts` — note GCP `location:` (e.g., `us-central1`) for use in profiles.yml (per Research A: dataset location must match profile location exactly)

### STORY 1.3 — dbt project initialization
- [ ] 1.3.1 — `dbt init` inside `dbt/` directory
- [ ] 1.3.2 — Configure `profiles.yml` with `dev` (BigQuery) and `prod-snowflake` (placeholder) targets — service account JSON path via env var only (NEVER commit `profiles.yml`)
- [ ] 1.3.3 — Configure `dbt_project.yml` with model paths: `models/staging/`, `models/core/`, `models/marts/`
- [ ] 1.3.4 — Configure `maximum_bytes_billed` in `profiles.yml` as integer byte count (per Research A: queries exceeding limit error out before running — this is the dbt-side cost guardrail). Suggested: 1 GB (1073741824) — way above expected usage, prevents runaway queries.
- [ ] 1.3.5 — Create `packages.yml` with `dbt-labs/dbt_utils` dependency; run `dbt deps` (Research A: canonical utility lib, signals stack fluency)
- [ ] 1.3.6 — Test: `dbt debug` succeeds; `dbt run` (empty) succeeds; `dbt docs generate && dbt docs serve` renders

### STORY 1.4 — Tiny generator (SCD2-AWARE from day 1)
**Single generator script, scalable via CLI flags.** Loop 1 and Loop 2 share `generator/generate.py` — Loop 1 invokes with smaller flags. Loop 2 scales up the same code path. No duplicate generator scripts.

- [ ] 1.4.0 — `generator/generate.py` accepts CLI flags: `--n_employees`, `--n_months`, `--seed`, `--output_dir`. Defaults match Loop 2 (`--n_employees 2500 --n_months 36`). Loop 1 runs `python generator/generate.py --n_employees 50 --n_months 6 --seed 42`.
- [ ] 1.4.1 — 50 employees, each with sorted timeline of events `[hire, term?]`
- [ ] 1.4.2 — Per-employee event timeline emits monotonically increasing dates
- [ ] 1.4.3 — Validation: no two events per employee on same date, no events before hire
- [ ] 1.4.4 — Output: `data/raw/employees.csv`, `data/raw/workforce_events.csv`

### STORY 1.5 — Raw load + first dbt model
- [ ] 1.5.1 — DDL for `raw.employees` + `raw.workforce_events` (typed)
- [ ] 1.5.2 — Python loader script `generator/load_raw.py` using `bq load`
- [ ] 1.5.3 — Declare raw tables as `sources` in `dbt/models/sources.yml`
- [ ] 1.5.4 — First dbt model `models/marts/v_monthly_hires.sql` — uses `{{ source('raw', 'workforce_events') }}`
- [ ] 1.5.5 — `dbt build` runs clean; view exists in `marts.v_monthly_hires`

### STORY 1.6 — First dashboard
- [ ] 1.6.1 — Connect Looker Studio to `marts.v_monthly_hires`
- [ ] 1.6.2 — One line chart: hires over time
- [ ] 1.6.3 — Page title, SYNTHETIC banner, project description in dashboard header
- [ ] 1.6.4 — Set sharing to public (read-only)
- [ ] 1.6.5 — Add dashboard link to README

**Loop 1 Checkpoint:** Public repo + dbt project + public dashboard live. Walking skeleton complete.

---

## Loop 2 — Full Source Data + Core Layer (paw-prey-002)

*Substantive dashboard with real benchmark-aligned data. SCD2 via dbt snapshot.*

**Loop 2 Definition of Done:**
- Generator produces full 5-table synthetic dataset matching benchmark targets
- Validation harness passes — all benchmarks within ±0.5pp tolerance
- Raw layer loaded with all 5 source tables
- Core layer modeled via dbt — 4 Type 1 dims + Type 2 SCD `dim_employee` (snapshot) + 4 fact tables
- All dbt tests pass (`not_null`, `unique`, `relationships`)
- 2 dashboard pages live with real data

### STORY 2.1 — Full generator
**Library stack (per Research B, 20 Tier 1 sources):** Three-layer custom Python simulator. `faker` for nominal strings (names, emails) only; `scipy.stats.lognorm` for tenure-at-exit; `scipy.stats.norm` + Gaussian copula for continuous correlations; CPT for IsRegrettableFlag calibration. **Parent-first generation order** for referential integrity (org_hierarchy → departments → jobs → employees → events).

- [ ] 2.1.0 — **Gender column added to `employees.csv`** (per r05 hunt review — required by Story 3.6 pay equity analysis):
  - Column `gender` ∈ {"F", "M", "NB"} with NB ≈ 1% reflecting real distribution
  - **Conditional on job_level** (this is the mechanism that produces the 13% unadjusted gap; do NOT sample independently):
    - `P(gender = F | job_level = "IC1")` ≈ 0.48 (entry-level near parity)
    - `P(gender = F | job_level = "IC2")` ≈ 0.45
    - `P(gender = F | job_level = "M1")` ≈ 0.40 (first management gap)
    - `P(gender = F | job_level = "M2")` ≈ 0.33
    - `P(gender = F | job_level = "Director")` ≈ 0.28
    - `P(gender = F | job_level = "VP+")` ≈ 0.22
  - NB and M fill the remainder proportionally per level
  - Generation order: assign job_level first, then sample gender conditional on level
- [ ] 2.1.1 — Expand to ~2,500 employees over 36 months. **Causal generation flow (per r04 hunt review — corrected from terminated-first framing):**
  1. Assign each employee a `hire_date`, sampled uniformly from `[window_end - 60_months, window_end]` (allows pre-window hires to enter as ongoing tenure)
  2. Draw a `tenure_months` from `scipy.stats.lognorm(s=0.9, scale=2.4*12)` adjusted by covariate hazards (Story 2.3 — high perf → 0.5× tenure shrinkage; pay compression → 1.4× hazard)
  3. Compute `theoretical_exit_date = hire_date + tenure_months`
  4. **Classify:**
     - If `theoretical_exit_date < window_end`: **terminated** (observed exit at `theoretical_exit_date`)
     - If `theoretical_exit_date ≥ window_end`: **right-censored** (still active; tenure = `window_end - hire_date`)

  Censored fraction is the **outcome** of this process (~60-70% expected for 36-month window + 2.4yr median tenure), not a target.

  **Pilot test (per r04 hunt review — replaces tautological median check):** Generate 500 samples first, verify:
  - **Censoring rate** in [55%, 75%] (validates window length matches lognorm scale)
  - **Hazard shape non-monotone**: KM-estimated hazard peaks around tenure 12–24mo then declines (Research B's "humped hazard" signature)
  - **Covariate effect**: KM curves stratified by `performance_tier` show high-performer curve dominating low-performer curve (hazard ratio recovered ≈ 0.5)
  - Median of TERMINATED employees only (KM at-event median) recovers ≈ 2.4yr ± 0.2 (this is the real benchmark match — censored employees don't contribute a median)
- [ ] 2.1.2 — Generate `compensation.csv` (salary, currency, pay band, effective dates).
  **Pay-correlation mechanism (per r05 hunt review — required to produce Spec 1 → Spec 3 shrinkage in Story 3.6.3 OLS panel):**

  ```
  For each employee, sample compa_ratio:
      compa_ratio ~ scipy.stats.norm(mean=mu_ratio, std=0.08), clipped to [0.7, 1.4]
      where mu_ratio =
          1.00
        + 0.020 × (tenure_years - 2)         # +2% per year above 2yr median
        + 0.030 × (performance_tier - 3)     # +3% per point above 3
        + 0.000 × gender                     # CRITICAL: gender has NO direct effect

  Then: salary = band_midpoint(job_level) × compa_ratio
  ```

  **Why this generates the 13% → 2% narrative naturally:**
  - Gender has NO direct effect on `compa_ratio` → within-(job_level, tenure, perf) salary equal across gender → controlled gap ≈ 0-2%
  - Gender × job_level distribution is skewed (Story 2.1.0) → senior bands pay more → women underrepresented at senior bands → raw gap ≈ 13%
  - The shrinkage from Spec 1 to Spec 3 emerges from the joint distribution, not from explicit injection
  - Story 3.6.3's OLS panel can show this as a learned phenomenon, not a designed result

  Pilot test (recommended before full run): generate 500 employees, compute unadjusted vs adjusted gap, verify they land in roughly [11%, 15%] and [0%, 3%] respectively. Adjust the job_level × gender table in Story 2.1.0 if drift exceeds.
- [ ] 2.1.3 — Generate `performance_ratings.csv` (annual + mid-year cycles) — joint distribution with tenure + retention via Gaussian copula (Story 2.3)
- [ ] 2.1.4 — Generate `survey_responses.csv` (quarterly eNPS + engagement items) — eNPS aggregate centers on 34, individual response distribution skewed
- [ ] 2.1.5 — Generate `succession_plan.csv` (employee_id → successor_readiness_count) — critical-role employees over-represented in zero-successor bucket (feeds IsRegrettableFlag CPT)
- [ ] 2.1.6 — Generate `org_hierarchy.csv` reference (departments, jobs, locations, criticality flags, skill scarcity tiers) — generated **first** (parent in hierarchical generation)

### STORY 2.2 — Benchmark realism
**Targets** (from `research/sessions/2026-05-14_people-analytics-dw-standards/01_tldr.md`):
- [ ] 2.2.1 — Total attrition 14.5% annualized (voluntary 11%, involuntary 3.5%)
- [ ] 2.2.2 — Regrettable share 30% of voluntary (2.2% headcount-based)
- [ ] 2.2.3 — High-performer voluntary attrition 5%
- [ ] 2.2.4 — Median tenure at exit 2.4 years
- [ ] 2.2.5 — Promotion rate 8%
- [ ] 2.2.6 — Internal fill rate 35%
- [ ] 2.2.7 — Compa-ratio centered at 1.00, std dev 0.10
- [ ] 2.2.8 — eNPS 34 ± noise
- [ ] 2.2.9 — Manager span of control mean 6.5
- [ ] 2.2.10 — Controlled gender pay gap 2% (unadjusted ~13%)

### STORY 2.3 — Correlated signals (regrettable-attrition foundation)
**Methodology (per Research B):** Gaussian copula for continuous joint distributions (compa-ratio × performance × tenure_outcome) + CPT for IsRegrettableFlag discrete conditional. **Causal generation order** prevents target leakage — predictors generated first, then attrition/regrettable sampled from their joint distribution.

**Generation sequence:**
1. Sample predictor features per employee: performance ∈ {1..5}, potential ∈ {LOW, MID, HIGH}, role_criticality (from job), successor_count
2. Compute hazard adjustment from features (high performers → 0.5× baseline; critical role + zero successors → 1.4×)
3. Sample tenure outcome (terminated vs censored) using adjusted log-normal hazard
4. For voluntary terminations: sample IsRegrettableFlag from logistic CPT calibrated to E[reg | vol_exit] = 0.30

- [ ] 2.3.1 — High performers attrit at half the rate of low performers (hazard ratio ≈ 0.5)
- [ ] 2.3.2 — Critical-role exits cluster in specific job families
- [ ] 2.3.3 — Pay compression near band ceiling correlates with elevated exit risk (compa-ratio > 1.15 → hazard ratio ≈ 1.4)
- [ ] 2.3.4 — Early-tenure attrition elevated, dips, climbs at 2y mark (matches log-normal non-monotone hazard)
- [ ] 2.3.5 — Manager-level attrition variance (some managers lose 2-3× more than mean)
- [ ] 2.3.6 — IsRegrettableFlag CPT: P(reg=1 | perf=high, potential=high, role=critical, successor_count=0) ≈ 0.85; P(reg=1 | perf=low, role=non-critical) ≈ 0.05. Calibrate iteratively against the 30% aggregate target.

### STORY 2.4 — SCD2-compatible event sequences
- [ ] 2.4.1 — For each employee, emit chronologically ordered, gap-free event timeline
- [ ] 2.4.2 — Each event explicitly carries before/after state for changed attributes
- [ ] 2.4.3 — Validation: deterministic SCD2 reconstruction yields no gaps, no overlaps, single is_current row

### STORY 2.5 — Validation harness
**Validation stack (per Research B — replaces SDMetrics):** Five-layer validation that doesn't require real comparable data.

- [ ] 2.5.1 — `generator/validate.py` computes each benchmark from generated CSVs (attrition rate, regrettable share, tenure median, compa-ratio mean/std, eNPS, span, controlled gender gap)
- [ ] 2.5.2 — **Hellinger distance** per column: synthetic distribution vs benchmark target distribution; assert < 0.1 for each tracked benchmark column. Exit non-zero if any fail.
- [ ] 2.5.3 — **Kaplan-Meier estimator**: compute median time-to-event from terminated+censored populations; assert 2.2yr ≤ median ≤ 2.6yr. Plot survival curve to `docs/survival-curve.png` (portfolio artifact).
- [ ] 2.5.4 — **Spearman correlation matrix preservation**: target correlations (performance↔attrition, tenure↔compa-ratio, etc.) preserved within ±0.05 of design intent.
- [ ] 2.5.5 — **SQL FK assertions**: every employee_id in fact tables resolves to dim_employee; every dept_id resolves to dim_department. Zero orphan rows.
- [ ] 2.5.6 — Output: console table — metric / target / actual / status; plus `docs/survival-curve.png`.

**TSTS readiness check (deferred to Loop 6 entry — see Loop 6 prerequisites):** Hold 20% synthetic out at generation time; train baseline logistic on 80%; verify AUC > 0.65 on held-out 20%. This is a Loop 6 prerequisite (the baseline model belongs with the retention pipeline), not Loop 2 validation. Generator must support a `--holdout-fraction 0.20` flag.

### STORY 2.6 — Raw load (all 5 tables)
- [ ] 2.6.1 — DDL + sources.yml entries for all 5 raw tables
- [ ] 2.6.2 — Loader script handles all 5 in one run
- [ ] 2.6.3 — Raw-layer dbt tests (`not_null`, `unique` on natural keys)

### STORY 2.6.5 — Staging layer (`models/staging/`)
**Convention (per dbt Labs best practices):** `models/staging/stg_*.sql` is the canonical entry point for downstream models. Staging renames + casts + cleans raw columns into analyst-friendly column names. **Core models never reference `{{ source(...) }}` directly — they reference `{{ ref('stg_*') }}`.**

- [ ] 2.6.5.1 — `models/staging/stg_employees_current.sql` — selects the latest state per employee from `raw.employees` (or reconstructs from `raw.workforce_events` if events are the truth source); explicit type casts; column renames if needed. **Pass-through columns:** employee_id, first_name, last_name, email, hire_date, **gender** (Type 1, never null per Story 2.1.0), dept_id, job_id, manager_id, location_id, pay_band_id
- [ ] 2.6.5.2 — `models/staging/stg_workforce_events.sql` — type-cast event dates, validate event_type ∈ {hire, promote, dept_change, mgr_change, comp_change, term_voluntary, term_involuntary}
- [ ] 2.6.5.3 — `models/staging/stg_compensation.sql`
- [ ] 2.6.5.4 — `models/staging/stg_performance_ratings.sql`
- [ ] 2.6.5.5 — `models/staging/stg_survey_responses.sql`
- [ ] 2.6.5.6 — `models/staging/stg_succession_plan.sql`
- [ ] 2.6.5.7 — `models/staging/_staging.yml` — `not_null` + `unique` tests on PKs; `accepted_values` tests on enums
- [ ] 2.6.5.8 — Materialize all staging models as `view` (default) — fast, no storage cost

### STORY 2.7 — Core dimensions (dbt models, Type 1)
**Demographic dimensions convention (per r05 hunt review):** Gender is a Type 1 attribute on dim_employee (static — does not change over employee tenure in this synthetic dataset; real-world is more nuanced but out of scope). It surfaces on the SCD2-tracked dim_employee snapshot but is NOT a check_col (no need to track historical changes). Ethnicity, age_band, and location_type are noted in "What I'd add with more time" (Story 4.5.2).

- [ ] 2.7.1 — `core/dim_date.sql` — date spine 2022-2027 with month/quarter/year flags
- [ ] 2.7.2 — `core/dim_department.sql`
- [ ] 2.7.3 — `core/dim_job.sql` (incl. is_critical_role, skill_scarcity_tier, band_midpoint per level)
- [ ] 2.7.4 — `core/dim_location.sql`
- [ ] 2.7.5 — Add `relationships` tests for FK integrity
- [ ] 2.7.6 — `dim_employee` Type 1 attributes pass-through: `gender` (from `stg_employees_current` → through snapshot → exposed on dim) — NOT a check_col, never changes

### STORY 2.8 — Type 2 SCD `dim_employee` (dbt snapshot)
**Strategy = `check` with mandatory COALESCE wrapping (per Research A — single highest-risk item in the entire build):**

Source rows are derived from event timelines, not from a system-updated_at column — so `check` is the right strategy. BUT: dbt's check strategy compares columns using SQL equality, and `NULL = NULL` evaluates to `NULL`, which the comparison logic treats as **"changed."** Without mitigation, every employee with any NULL in a check column gets a new SCD2 row on every nightly run — silent history corruption. **Not documented in official dbt docs.**

**Complete nullable-column COALESCE matrix:**

| Source column | Type   | Nullable in source? | Sentinel value      | SAFE alias       |
|---------------|--------|---------------------|---------------------|------------------|
| `employee_id` | STRING | NO (PK)             | (none)              | `employee_id`    |
| `dept_id`     | STRING | YES (rare — pre-onboarding) | `'__NO_DEPT__'` | `dept_id_safe`   |
| `job_id`      | STRING | NO                  | (none)              | `job_id`         |
| `manager_id`  | STRING | YES (CEO, vacancies)| `'__NO_MGR__'`      | `manager_id_safe`|
| `location_id` | STRING | YES (remote-pending)| `'__NO_LOC__'`      | `location_id_safe`|
| `pay_band_id` | STRING | YES (new hire, TBD) | `'__NO_BAND__'`     | `pay_band_id_safe`|

All sentinel values are STRING (matching column type — `-1` integer sentinels are a type-mismatch bug). All non-nullable columns pass through unwrapped.

**Phantom dim rows:** For each sentinel value used in a check column, create a corresponding phantom row in the relevant dimension (`dim_department`, `dim_employee` for managers, `dim_location`, `dim_pay_band`) with `id = '__NO_*__'` and `description = 'Sentinel: source value was NULL'`. This keeps `relationships` tests green and is transparent in the dashboard ("unassigned" buckets are visible, not silently dropped).

- [ ] 2.8.1 — Define snapshot `snapshots/dim_employee_snapshot.sql`:
  ```sql
  {{ config(
      target_schema='core',
      strategy='check',
      unique_key='employee_id',
      check_cols=['dept_id_safe', 'job_id', 'manager_id_safe', 'location_id_safe', 'pay_band_id_safe'],
      dbt_valid_to_current="cast('9999-12-31' as date)"
  ) }}

  SELECT
      employee_id,
      job_id,
      gender,                                            -- Type 1, never null (Story 2.1.0); NOT in check_cols
      COALESCE(dept_id,     '__NO_DEPT__') AS dept_id_safe,
      COALESCE(manager_id,  '__NO_MGR__')  AS manager_id_safe,
      COALESCE(location_id, '__NO_LOC__')  AS location_id_safe,
      COALESCE(pay_band_id, '__NO_BAND__') AS pay_band_id_safe
  FROM {{ ref('stg_employees_current') }}
  ```
- [ ] 2.8.2 — Create phantom dim rows: each sentinel value (`__NO_DEPT__`, `__NO_MGR__`, `__NO_LOC__`, `__NO_BAND__`) inserted as a record in its respective dimension with `description = 'Sentinel — source NULL'`. Define in seeds or in the dim model's SQL.
- [ ] 2.8.3 — `dbt snapshot` runs successfully across multiple loaded states (each generates new history rows only on real changes)
- [ ] 2.8.4 — Validation: every workforce_events change reflected; single `dbt_valid_to = '9999-12-31'` per active employee (uses `dbt_valid_to_current` config — no `IS NULL` filtering downstream)
- [ ] 2.8.5 — **NULL-stability test:** snapshot the same source data twice in a row with no real changes. Assert: zero new SCD2 rows added. If new rows appear, COALESCE wrapping is broken.
- [ ] 2.8.6 — NULL-transition test: an employee with `manager_id = NULL` → `manager_id = 'EMP_00042'` produces exactly ONE new SCD2 row (not infinite false-positives).
- [ ] 2.8.7 — Downstream model contract: any model joining on `*_safe` columns either joins to the phantom dim rows OR filters `WHERE col != '__NO_*__'` and documents the exclusion. Add to `models/marts/_marts.yml` as a column description.

### STORY 2.9 — Core facts (dbt models)
- [ ] 2.9.1 — `core/fact_workforce_events.sql` (event-grain)
- [ ] 2.9.2 — `core/fact_compensation_snapshot.sql`
- [ ] 2.9.3 — `core/fact_performance_ratings.sql`
- [ ] 2.9.4 — `core/fact_survey_responses.sql`
- [ ] 2.9.5 — Relationships tests for all FKs

### STORY 2.10 — Dashboard pages 1 + 2 (per Session C — narrative starts here)
**Narrative anchor:** Page 1 = baseline ("what's the workforce?"). Page 2 = risk ("what's leaving?"). Subsequent loops add Page 3 (structural change) and Page 4 (fairness).

- [ ] 2.10.0 — **KPI scorecard pattern** (per Session C, with r05 wording correction): Looker Studio has a native "Scorecard with comparison" chart — set Metric = current period, Comparison date range = prior period, display shows value + % delta + ↑/↓ arrow. **NOT a Looker Studio template object** — cross-page reuse requires copy-paste with identical config. Document the exact config in `looker/scorecard-config.md` (metric, comparison range, conditional colors green/red/gray) so pages 2-4 replicate cleanly. Consistency enforced by config doc + visual review, not by templating.
- [ ] 2.10.1 — Page 1 — Workforce Overview (KPI strip: HC, hiring rate, voluntary attrition rate, span-of-control; trend charts: HC trend, growth rate, dept/location breakdown, hires-vs-exits waterfall)
- [ ] 2.10.2 — Page 2 — Attrition Analysis preliminary (KPI strip + decomposition stack + perf-attrition scatter). Loop 3 Story 3.4 adds the IsRegrettableFlag 3-layer introduction + manager ranking.

**Loop 2 Checkpoint:** Dashboard reflects real benchmark data, two pages live. Core layer + SCD2 complete via dbt.

---

## Loop 3 — Marts + Differentiating Metrics (paw-prey-003)

*The signal-generating layer. IsRegrettableFlag, the dashboard views recruiters recognize.*

**Loop 3 Definition of Done:**
- `fact_headcount_snapshot` (periodic snapshot) materialized as dbt model
- `IsRegrettableFlag` computed on all voluntary terminations
- 4 marts dbt models (one per dashboard page) + 1 ML feature model (`v_attrition_features`)
- All dbt marts tests pass
- Pages 2 + 3 + 4 with differentiating viz live
- BigQuery Time Travel demo documented in README

### STORY 3.1 — `marts/fact_headcount_snapshot.sql` (periodic snapshot)
- [ ] 3.1.1 — dbt model: for each month-end, snapshot active employees joining SCD2 dim
- [ ] 3.1.2 — Denormalize dim attrs (dept, job_level, location, manager) onto fact
- [ ] 3.1.3 — Materialize as `table` (not `view`) for query performance
- [ ] 3.1.4 — Cluster on (snapshot_date, dept_id, job_level)

### STORY 3.2 — IsRegrettableFlag classification (`marts/fact_workforce_events_enriched.sql`)
**Canonical source = generation (CPT-stamped in raw data; per r04 hunt review):**

IsRegrettableFlag is sampled at generation time (Story 2.3.6) via logistic CPT calibrated to E[reg | vol_exit] = 0.30, and stored as a column on the voluntary-termination event. The mart layer **reads this column** rather than re-deriving it. This avoids a per-employee inconsistency that would emerge if generation calibrated to aggregate rate while the mart used a deterministic OR-rule.

**Why this design:**
- Loop 6 (rp-prey-001) trains on the canonical generated label — no ambiguity about training truth
- Dashboard rate and underlying data structure tell the same story
- Aggregate rate (~30%) is guaranteed by calibration, not coincidence

**Mart-layer pattern: SELECT-the-flag with documentation block**

The mart materializes the flag joined to its descriptive features, with a comment block showing the OR-rule a PA analyst would have used to derive the same flag from observable attributes (without access to the CPT-sampled truth). This demonstrates the SQL pattern recruiters expect AND honors the generated label.

```sql
-- /*
--   IsRegrettableFlag descriptive interpretation (for analyst reference):
--   The CPT-generated flag will fire approximately when:
--     voluntary_term = TRUE
--     AND (
--       last_perf_rating >= 4
--       OR last_potential_rating = 'HIGH'
--       OR job.is_critical_role = TRUE
--       OR successor_readiness_count = 0
--       OR job.skill_scarcity_tier IN ('SCARCE', 'CRITICAL')
--     )
--   Aggregate rate: ~30% of voluntary terminations (Mercer 2024 benchmark)
-- */

SELECT
    e.event_id,
    e.employee_id,
    e.event_date,
    e.exit_type,
    e.is_regrettable,                          -- CPT-sampled at generation time
    perf.last_rating  AS last_perf_rating,
    perf.last_potential AS last_potential_rating,
    j.is_critical_role,
    j.skill_scarcity_tier,
    sp.successor_readiness_count
FROM {{ ref('stg_workforce_events') }} e
LEFT JOIN ({{ ... last-perf-rating window query ... }}) perf USING (employee_id)
LEFT JOIN {{ ref('dim_job') }} j USING (job_id)
LEFT JOIN {{ ref('stg_succession_plan') }} sp USING (employee_id)
WHERE e.exit_type IS NOT NULL
```

- [ ] 3.2.1 — Build join: termination events → last perf rating BEFORE term date (window function on `stg_performance_ratings`)
- [ ] 3.2.2 — Join `dim_job` for criticality + scarcity (descriptive context only)
- [ ] 3.2.3 — Join `stg_succession_plan` for successor_readiness_count
- [ ] 3.2.4 — SELECT the CPT-generated `is_regrettable` column from `stg_workforce_events` (no OR-logic derivation)
- [ ] 3.2.5 — Validation test: aggregate rate from mart matches the CPT calibration target within ±2pp (tight tolerance because we're not deriving — we're SELECTing the truth label)
- [ ] 3.2.6 — Documentation block in SQL header (per template above) shows the analyst-derived OR-rule the flag would correspond to — pure documentation, not executed

### STORY 3.3 — Marts views (one per dashboard page + ML feature view)
**Connection mode = LIVE (per Research A):** Live BigQuery native connection — NO 100MB constraint applies. Pre-aggregation is for **query latency** (< 3s target), not size compliance. Views can return arbitrary row counts; the BQ free-tier 1TB/month query budget is the relevant limit, not extract size.

**View → page → chart mapping** (explicit):
- [ ] 3.3.1 — `marts/v_workforce_overview.sql` → Page 1 — pre-aggregated to (month × dept × job_level) for query latency
- [ ] 3.3.2 — `marts/v_attrition_analysis.sql` → Page 2 → decomposition + scatter + manager-rank — grain (month × dept × manager_id × exit_type)
- [ ] 3.3.3 — `marts/v_workforce_movement.sql` → Page 3 → mobility + promotion + span — grain (month × dept × event_type)
- [ ] 3.3.4 — `marts/v_compensation_equity.sql` → Page 4 → compa-ratio + pay gap + band penetration — grain (month × dept × job_level × gender)
- [ ] 3.3.5 — `marts/v_attrition_features.sql` → feeds Loop 6 (rp-prey-001 model input) — employee-grain. **Enforced model contract** (dbt 1.5+):
  ```yaml
  - name: v_attrition_features
    config:
      contract:
        enforced: true
    columns:
      - name: employee_id
        data_type: STRING
        constraints: [{ type: not_null }]
      - name: snapshot_date
        data_type: DATE
        constraints: [{ type: not_null }]
      - name: tenure_months
        data_type: INT64
      - name: performance_tier
        data_type: STRING
      - name: compa_ratio
        data_type: FLOAT64
      - name: is_critical_role
        data_type: BOOL
      - name: successor_count
        data_type: INT64
      - name: voluntary_exit_label
        data_type: BOOL
  ```
  Schema drift breaks the build at `dbt run`, not at Loop 6 training time.
- [ ] 3.3.6 — Latency sanity check: each dashboard-facing view returns first 1000 rows in < 3s on Looker Studio first load. If any view exceeds, consider partitioning (PARTITION BY snapshot_month) or materializing as `table`.

### STORY 3.4 — Page 2 differentiating views (per Session C — risk page)
**Page anchor (Session C narrative):** This page answers *"who's leaving and how much should we worry?"* — sets up the workforce-movement and pay-equity pages by quantifying risk.

**Page header KPI strip (per Session C — contextual comparison required):**
- Voluntary attrition rate (current period + prior period delta)
- Involuntary attrition rate (current + prior + delta)
- Regrettable share of voluntary (current + prior + delta)
- Avg tenure at exit (current + prior + delta)

- [ ] 3.4.0 — KPI strip implemented across all 4 KPIs (current + prior + delta + colored directional indicator). Pattern reused across all dashboard pages — define once as a Looker Studio template card.
- [ ] 3.4.1 — Attrition decomposition stack (voluntary + involuntary + regrettable + early-tenure) — monthly trend, last 36 months
- [ ] 3.4.2 — Performance-attrition scatter (rating bucket × attrition rate) — annotated quadrants
- [ ] 3.4.3 — Top 5 departments by attrition rate, ranked, with voluntary/involuntary split
- [ ] 3.4.4 — **Regrettable attrition introduction (3-layer per Session C):**
  - **Layer 1 — Definition panel** (markdown text card at top of section): *"**IsRegrettableFlag** identifies voluntary terminations where (a) last performance rating ≥ 4, OR (b) potential = HIGH, OR (c) role is flagged critical, OR (d) zero successors are ready, OR (e) skill scarcity is high. The flag exists to separate 'good attrition' from 'attrition that hurts.'"*
  - **Layer 2 — Formula panel**: the SQL OR-rule excerpted verbatim from `marts/fact_workforce_events_enriched.sql` (Story 3.2) as a code block. Demonstrates traceability.
  - **Layer 3 — Internal benchmark context**: trendline showing regrettable share as % of voluntary over time (this dataset's history only). NO mention of external "15% alarm threshold" — per Session C, that source is LOW CONFIDENCE.
    - **Bold YoY callout pinned above the trend chart** (per r05 hunt review — restores 30-second comprehension that was lost when the 15% threshold was dropped): single sentence with directional arrow, e.g., *"↑ Regrettable share trending UP — currently 32%, +4pp YoY"* — colored red if trending up, green if trending down, gray if flat (±1pp).
    - Trend chart sits below the callout for reviewers who want to see the shape, not just the headline.
- [ ] 3.4.5 — Regrettable attrition ranked by manager (top 10 managers by # regrettable exits in trailing 12 months, with their span-of-control + tenure for context)

### STORY 3.5 — Page 3 — Workforce Movement
- [ ] 3.5.1 — Internal mobility rate KPI + 12mo trend
- [ ] 3.5.2 — Promotion rate by job level + department
- [ ] 3.5.3 — Span of control heatmap

### STORY 3.6 — Page 4 — Compensation Equity (per Session C findings — fairness page)
**Page anchor (Session C narrative arc):** This is the "fairness" page. The prior three pages established baseline (Overview), risk (Attrition), and structural change (Movement). This page answers: *"is the system equitable?"* Both pay gap metrics are mandatory — showing only one is analytically incomplete at the senior level.

**Cognitive-load layout decision (per r05 hunt review):** The page has two audiences — a 30-second hiring manager scanner AND a senior PA practitioner who'll dwell. Layout splits the load:

- **Top half of Page 4 (visible without scrolling)** — the 30-second story: KPI strip + side-by-side both-gap presentation (Story 3.6.2) + compa-ratio heatmap (Story 3.6.1) + YoY-callout-style headline interpretation. Plain language; no regression coefficients.
- **Bottom half of Page 4 (scroll/expand)** — the methodology depth: progressive OLS panel (Story 3.6.3) + compa-ratio distributions (Story 3.6.4) + band penetration (Story 3.6.5) + outlier table (Story 3.6.6) + methodology text card (Story 3.6.7). For reviewers who dig.

This honors Session C's "decision-driving over visual impression" principle while respecting the 30-second scan. Visier's research: usage first, visual appeal third — the methodology depth serves users who'll act on it, the top-half serves users who'll judge competence in seconds.

**Page header KPI strip (per Session C — contextual comparison required):**
- Unadjusted gender pay gap (% with prior period delta)
- Adjusted gender pay gap (% with prior period delta)
- Median compa-ratio overall (with prior period delta)
- % employees in red compa-ratio zones (with prior period delta)

- [ ] 3.6.1 — **Compa-ratio HEATMAP (Session C's highest-impact single chart)**: color-coded matrix with rows = department, columns = job_level, cells colored by mean compa-ratio (green 95-105%, yellow 85-94% or 106-115%, red <85% or >115%). Hover reveals cell employee count + median compa-ratio. **This is the chart that signals genuine comp analytics competency** — make it the dominant visual on the page.

  **Implementation note (per r05 hunt review — Looker Studio pivot heatmap has no native breakdown dimension):** For the demographic facet, implement as **two side-by-side pivot tables** on the same page — one filtered to gender = F, one to gender = M (NB shown as a separate small inset given low N). Looker Studio's "Pivot table with heatmap" chart type supports rows × columns × single-metric cells with conditional formatting; duplication across genders is intentional for visual comparison. Document the pattern in `looker/heatmap-config.md` so future loops can replicate.
- [ ] 3.6.2 — **Side-by-side pay gap presentation (per Session C — both metrics + narrative)**:
  - Left card: **Unadjusted** gender pay gap (raw median % difference). Subtitle: "Representation equity — reflects who's in senior roles."
  - Right card: **Adjusted** gender pay gap (from OLS specification 3 — controlling for job_level, tenure, performance). Subtitle: "Equal pay for equal work — reflects within-level fairness."
  - Below both: a text block (markdown panel) explaining their relationship for THIS specific dataset: "An unadjusted gap of X% combined with an adjusted gap of Y% indicates a [representation / pay / both] driver — interventions differ accordingly." Auto-populate Y vs X from data.
- [ ] 3.6.3 — **Progressive OLS regression panel (3 specifications) — Python + statsmodels (committed per r05 hunt review)**:
  - **Specifications:**
    - Spec 1: `log(salary) ~ gender`
    - Spec 2: `log(salary) ~ gender + job_level`
    - Spec 3: `log(salary) ~ gender + job_level + tenure_months + last_perf_rating`
  - **Method commit: Python + `statsmodels.api.OLS` (NOT BQML).** Rationale: native p-values from `results.pvalues` (BQML requires manual t-stat→scipy extraction); `np.log(salary)` for log-linear is one line; the three specs are 30 lines total. Trade-off: introduces a Python step in the deploy sequence (handled in Story 4.4.1).
  - **Implementation:**
    1. `scripts/compute_pay_equity_ols.py` — reads `marts.v_compensation_equity` (or `marts.v_attrition_features` — whichever surfaces the needed columns) via `pandas-gbq.read_gbq()`
    2. Fits all 3 OLS specs with `statsmodels.api.OLS(np.log(salary), sm.add_constant(X)).fit()`
    3. Extracts: coefficient on `gender_F` (vs reference category `M`), std error, p-value, R², N, AIC
    4. Writes a flat dataframe to BigQuery via `pandas-gbq.to_gbq()` → table `marts.fact_pay_equity_models` (columns: spec_id, label, coef, stderr, pvalue, r_squared, n, aic, computed_at)
  - **Dashboard panel reads `marts.fact_pay_equity_models`** — Looker Studio renders the 3-spec results as a single table with columns: Spec, Predictors, Coef on gender_F, p-value, R². Conditional formatting: green if p < 0.05, gray if p ≥ 0.05.
  - **Rationale text block** (markdown panel above the table): "Spec 1 shows the unadjusted gap; Spec 2 isolates within-level inequity; Spec 3 controls for tenure and performance signals. The shrinkage from Spec 1 to Spec 3 quantifies how much of the raw gap is explained by structural variables. For this dataset, the gap shrinks from ~13% (Spec 1) to ~2% (Spec 3), indicating a representation/progression driver rather than a within-level pay driver."
- [ ] 3.6.4 — Compa-ratio distribution by job_level (faceted histogram, in-band vs out-of-band colored)
- [ ] 3.6.5 — Band penetration: employees by quartile within band (Q1 stacked column per level)
- [ ] 3.6.6 — Outlier flag table — employees with compa-ratio <0.85 or >1.15, joined to manager + dept + tenure for context
- [ ] 3.6.7 — Methodology text card (pinned to bottom of Page 4 — Looker Studio has no native cross-page footer; this is a single-page text component): explains the OLS specifications + cites SYNTHETIC DATA disclaimer + notes that Oaxaca-Blinder decomposition was considered and intentionally deferred (one-line explanation: "OLS is practitioner-standard and explainable without specialized econometrics training")

### STORY 3.7 — BigQuery Time Travel demo
- [ ] 3.7.1 — Write query using `FOR SYSTEM_TIME AS OF` showing headcount snapshot 30 days ago vs. today
- [ ] 3.7.2 — Add to README with point-in-time HR reporting use case explanation

**Loop 3 Checkpoint:** All 4 dashboard pages live with differentiating views. IsRegrettableFlag working. The "impressive" version exists.

---

## Loop 4 — Polish + Publish (paw-prey-004)

*Cross-page interactivity, documentation, public announcement.*

**Loop 4 Definition of Done:**
- Interactive filters work consistently across all 4 pages
- README complete with architecture diagram, dbt-docs lineage embed, metric dictionary, narrative
- `dbt build` reproduces full warehouse end-to-end from clone
- SYNTHETIC labeling visible on every dashboard page header + README opening
- Repo public, polished commit history, LinkedIn post live, portfolio + CV updated

### STORY 4.0 — Custom color palette (per Session C — highest-ROI 30-min investment)
**Replace Looker Studio default rainbow before polish work.** Session C: "spend 30 minutes replacing Looker Studio's default palette before anything else." A custom palette is the single fastest move that distinguishes enterprise-grade from student dashboards.

- [ ] 4.0.1 — Define palette in `looker/palette.md` and on each Looker page:
  - **Sequential greens** (3 shades) for "good" / in-band / low concern — `#d1e7dd → #75b798 → #198754`
  - **Sequential reds** (3 shades) for "concern" / out-of-band / high attrition — `#f8d7da → #ea868f → #dc3545`
  - **Neutral grays** (2 shades) for context / inactive — `#dee2e6 → #6c757d`
  - **Accent blue** for hyperlinks / interactive elements — `#0d6efd`
  - Avoid: Looker Studio's default categorical rainbow (signals "default settings, no thought")
- [ ] 4.0.2 — Apply palette consistently across all 4 pages (Looker Studio theme: top menu → Theme and layout → custom theme)
- [ ] 4.0.3 — Verify color-blind safety using Coblis (or Sim Daltonism) — palette must be distinguishable in all three modes: **deuteranopia** (red-green, most common), **protanopia** (red-green, less common), **tritanopia** (blue-yellow, rare but WCAG-relevant). Capture before/after screenshots of the compa-ratio heatmap under each mode, save to `docs/colorblind-tests/` as portfolio artifacts. Stretch goal: also test monochromacy (full grayscale) — if the dashboard still reads, accessibility is excellent.

### STORY 4.1 — Interactive filters
- [ ] 4.1.1 — Report-level filter controls: date range, department, location, job level
- [ ] 4.1.2 — Verify filter persistence across page navigation
- [ ] 4.1.3 — Mobile/responsive sanity check

### STORY 4.2 — Synthetic-data labeling enforcement
- [ ] 4.2.1 — Every Looker page header has "SYNTHETIC DATA — Illustrative Only" watermark
- [ ] 4.2.2 — README opens with full SYNTHETIC notice + disclaimer paragraph (no real company, no real employees)
- [ ] 4.2.3 — Each generator output CSV prefixed `_SYNTHETIC_`
- [ ] 4.2.4 — Dashboard landing page (page 1 header) has visible disclaimer banner

### STORY 4.3 — Architecture + schema documentation
- [ ] 4.3.1 — Architecture diagram (Mermaid in README): CSVs → bq load → BigQuery (raw → dbt staging → core → marts) → Looker Studio
- [ ] 4.3.2 — Schema diagram (dbt-docs auto-generates) — embed link in README
- [ ] 4.3.3 — Metric dictionary: every differentiating metric, formula, source model, business meaning
- [ ] 4.3.4 — **GitHub Pages site** published from `docs/` branch — hosts: dbt-docs (via `dbt docs generate && cp -r target/* docs/dbt/`), `docs/survival-curve.png`, `docs/project-evaluator-report.html`. README links all three.
- [ ] 4.3.5 — **`dbt-project-evaluator` run** (per r04 hunt review): Add `dbt-labs/dbt_project_evaluator` to `packages.yml`; run `dbt build --select package:dbt_project_evaluator`; capture results to `docs/project-evaluator-report.html`; resolve every Critical or Warning finding before publication.

### STORY 4.4 — Reproducible deploy
- [ ] 4.4.1 — `Makefile` or `deploy.sh` with explicit step sequencing (per r05 hunt review — OLS slot added):
  ```
  make all:
    1. python generator/generate.py             # generates CSVs into data/raw/
    2. python generator/validate.py             # benchmark + Hellinger + KM + FK checks
    3. python generator/load_raw.py             # bq load CSVs into raw.*
    4. dbt deps && dbt build                    # staging + core + marts + snapshot + tests
    5. python scripts/compute_pay_equity_ols.py  # OLS fit + write to marts.fact_pay_equity_models
    # Step 5 runs after dbt build so marts.v_compensation_equity exists for OLS input.
    # marts.fact_pay_equity_models is a Python-written table that the dashboard reads directly
    # (not a dbt model); documented in README as "non-dbt-managed marts artifact."
  ```
- [ ] 4.4.2 — README "How to reproduce" section with the full step sequence above + 1-line description of each step
- [ ] 4.4.3 — `make validate` runs `generator/validate.py` + `dbt test` (subset of `dbt build`)
- [ ] 4.4.4 — **`dbt snapshot --target` gotcha guard** (per Research A): `dbt snapshot` ignores `--target` and writes to its configured `target_schema`. Mitigation: write a custom macro and run it before snapshot operations.

  Create `dbt/macros/check_environment.sql`:
  ```jinja
  {% macro check_environment(expected) %}
      {% if target.name != expected %}
          {{ exceptions.raise_compiler_error(
              "Target mismatch: expected '" ~ expected ~
              "', got '" ~ target.name ~
              "'. Snapshots use target_schema regardless of --target; abort to prevent corrupting production history."
          ) }}
      {% else %}
          {{ log("Environment check passed: target = " ~ target.name, info=True) }}
      {% endif %}
  {% endmacro %}
  ```

  Use in `Makefile`:
  ```makefile
  snapshot-dev:
  	dbt run-operation check_environment --args '{expected: dev}' && dbt snapshot --target dev
  ```

  Document the gotcha + macro purpose in README under "Reproducing the warehouse — gotchas."

### STORY 4.5 — Interview narrative
- [ ] 4.5.1 — README opens with 3-sentence project pitch
- [ ] 4.5.2 — "What I'd add with more time" section (self-aware critique)
- [ ] 4.5.3 — Practice verbal version

### STORY 4.6 — Publication
- [ ] 4.6.1 — Push polished commit history (squash WIP commits, conventional commit format)
- [ ] 4.6.2 — Pin Looker Studio dashboard link in repo header
- [ ] 4.6.3 — Add to `career/portfolio-links.md`
- [ ] 4.6.4 — LinkedIn post (3 sentences + dashboard screenshot + repo link)
- [ ] 4.6.5 — LinkedIn skills: BigQuery, Snowflake, dbt, Looker Studio, Dimensional Modeling
- [ ] 4.6.6 — CV Technical Skills + project bullet

**Loop 4 Checkpoint:** Shipped. Public. Discoverable.

---

## Loop 5 — Snowflake Validation Port (paw-prey-005)

*The multi-vendor showcase. dbt's profile abstraction makes this dramatically easier than manual translation.*

**Loop 5 Definition of Done:**
- Snowflake free trial active
- `dbt run --target snowflake` succeeds — same models, same logic
- Same key queries produce parity results across BigQuery and Snowflake
- Side-by-side screenshots in README
- Multi-vendor narrative section
- Snowflake added to LinkedIn skills (now backed by working code)

### STORY 5.1 — Snowflake account + warehouse
- [ ] 5.1.1 — Activate Snowflake free trial (parallel-friendly with Loop 3)
- [ ] 5.1.2 — Create database HR_ANALYTICS with schemas RAW, CORE, MARTS
- [ ] 5.1.3 — X-Small warehouse with 60s auto-suspend
- [ ] 5.1.4 — Roles (PA_LOADER, PA_TRANSFORMER, PA_REPORTER) — RBAC awareness signal

### STORY 5.2 — dbt-snowflake profile + dialect adjustments
**Expected portability (per Research A, 2026-05-15 rerun):** Budget **2–4 hours** assuming no nested types in models. Only three concrete rewrite points exist in this schema.

**Confirmed dialect breaks (per Research A):**
- `DATE_TRUNC` — argument order is **reversed** between BigQuery and Snowflake. Fix: use `{{ dbt.date_trunc('month', 'my_date_col') }}` cross-database macro instead of native calls.
- `GENERATE_DATE_ARRAY` — BigQuery-only. Rewrite to dbt-utils `date_spine` (cross-warehouse compatible).
- `STRUCT` / `ARRAY` literal syntax — BQ-native, not portable. **Not used in this project's models** (verify during port).

**Confirmed compatible (do NOT need adapter.dispatch):**
- `QUALIFY` — supported in both BigQuery and Snowflake with consistent semantics.
- Standard SQL window functions, CTEs, basic aggregates.

**For Story 3.7 (Time Travel demo) — decision: BQ-only, documented:** BigQuery `FOR SYSTEM_TIME AS OF` and Snowflake `AT(TIMESTAMP =>)` are semantically equivalent but syntactically different. Time Travel is a **BQ-specific capability demo** — not ported to Snowflake. Snowflake equivalent SQL documented in `docs/multi-vendor-notes.md` for completeness. This keeps Loop 5 at half-day; demo lives in the BQ-native experience.

- [ ] 5.2.1 — Add Snowflake target to `profiles.yml`
- [ ] 5.2.2 — Audit `dim_date.sql` and any models using DATE_TRUNC / GENERATE_DATE_ARRAY; replace with cross-db equivalents (`{{ dbt.date_trunc() }}`, `{{ dbt_utils.date_spine() }}`)
- [ ] 5.2.3 — Document every dialect adjustment in `docs/multi-vendor-notes.md` with before/after SQL — recruiter-readable proof of cross-warehouse fluency
- [ ] 5.2.4 — Run `dbt build --target snowflake` end-to-end after macro changes; iterate until clean

### STORY 5.3 — Data load (COPY INTO)
- [ ] 5.3.1 — Create internal stage `@HR_ANALYTICS.RAW.STG_SOURCE`
- [ ] 5.3.2 — `PUT` to upload CSVs from local
- [ ] 5.3.3 — `COPY INTO` scripts; row counts match BigQuery

### STORY 5.4 — Build + parity validation
- [ ] 5.4.1 — `dbt run --target snowflake` builds all models
- [ ] 5.4.2 — Run 5 representative queries on both warehouses; compare results within rounding tolerance
- [ ] 5.4.3 — Capture screenshots of both Snowsight + BigQuery console with matching results
- [ ] 5.4.4 — Document any deltas + reasons

### STORY 5.5 — Multi-vendor README section
- [ ] 5.5.1 — Add "Multi-Warehouse Implementation" section
- [ ] 5.5.2 — Side-by-side screenshot grid (4 query results × 2 warehouses)
- [ ] 5.5.3 — Frame as "demonstrated cloud-warehouse fluency across both major vendors via dbt's portability"
- [ ] 5.5.4 — Note Snowflake side is trial-expiring; BigQuery is canonical live artifact

**Loop 5 Checkpoint:** Multi-vendor showcase complete. dbt portability demonstrated.

---

## Loop 6 — rp-prey-001 Integration (REQUIRED)

*Connects this warehouse to the retention prediction model. Headline narrative: end-to-end pipeline, not two disconnected projects.*

**Loop 6 Definition of Done:**
- **TSTS pre-flight passes** (per r04 hunt review): baseline logistic regression on 80% synthetic, evaluate on 20% holdout, **AUC > 0.65** confirms ML utility before training rp-prey-001
- rp-prey-001 reads training data from `marts.v_attrition_features` (live BigQuery, not CSV)
- Trained model writes predictions to `marts.fact_retention_predictions`
- Looker Studio dashboard gains Page 5: "Predicted Attrition Risk"
- Both READMEs cross-link with pipeline architecture diagram
- LinkedIn announcement updated for the combined narrative

### STORY 6.0 — TSTS pre-flight (must pass before 6.1)
- [ ] 6.0.1 — Regenerate dataset with `python generator/generate.py --holdout-fraction 0.20 --seed 42` — holdout split deterministic
- [ ] 6.0.2 — Train baseline logistic regression on 80% on (tenure, performance_tier, compa_ratio, is_critical_role, successor_count) predicting `voluntary_exit_label`
- [ ] 6.0.3 — Evaluate AUC on 20% holdout — assert AUC > 0.65 (signal exists, not noise)
- [ ] 6.0.4 — If AUC < 0.65: regenerate with stronger covariate effects (Story 2.3 hazard ratios), repeat. Document the iteration count in `docs/tsts-readiness-report.md`.

### STORY 6.1 — Refactor rp-prey-001 to consume from BigQuery
- [ ] 6.1.1 — Add `google-cloud-bigquery` to rp project deps
- [ ] 6.1.2 — Refactor data loading: SELECT from `marts.v_attrition_features` (contract-enforced schema from Story 3.3.5)
- [ ] 6.1.3 — Write predictions back: INSERT to `marts.fact_retention_predictions` (employee_id, prediction_date, risk_score, risk_tier, model_version)
- [ ] 6.1.4 — Add Page 5 to Looker dashboard — risk-tier heatmap by dept × tenure band
- [ ] 6.1.5 — Update both READMEs to cross-link with combined architecture diagram

**Loop 6 Checkpoint:** End-to-end pipeline: raw data → BigQuery → dbt → Python model → predictions in BigQuery → Looker visualization. Single coherent portfolio story.

---

## Sequencing & Dependencies

```
Loop 1 (Walking Skeleton) ──► Loop 2 (Full data + core + dbt snapshot)
       │                              │
       │                              ▼
       │                       Loop 3 (Marts + IsRegrettable + feature view)
       │                              │
       └──► Snowflake free trial      │
            activated during Loop 3   │
                                      ▼
                              Loop 4 (Polish + publish)
                                      │
                                      ▼
                              Loop 5 (Snowflake port — dbt profile swap)
                                      │
                                      ▼
                              Loop 6 (rp-prey-001 integration — REQUIRED)
```

**Critical path:** Loops 1 → 2 → 3 → 4 → 6. Loop 5 parallel-friendly with Loop 4.

---

## Risk Register

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| dbt-bigquery learning curve | Medium | Low | Research A covers setup; first Loop 1 stories build muscle memory; total overhead capped at 1 day |
| Snowflake trial re-trial denied at Loop 5 | Medium | Low | Pay $5 for credits if needed; BigQuery is canonical artifact |
| BigQuery cost overrun from buggy query | Low | Low | `maximum_bytes_billed` in dbt profile (per Research A: queries exceeding limit error out before running) + $5 billing alert. Hand-issued console queries from outside dbt are also bounded by free-tier quotas at our data scale. |
| Synthetic correlation tuning slips Loop 2 | Medium | Low | ±1pp benchmark tolerance acceptable; log-normal + Gaussian copula + CPT methodology from Research B (20 Tier 1 sources) prevents wheel-reinvention; pilot test on 500 samples before full run (Story 2.1.1) |
| Log-normal tenure derived from medical literature, not HR-validated | Medium | Low | Per Research B: log-normal preference is from clinical survival analysis; no HR-specific empirical validation exists. Mitigation: pilot validation against 2.4yr benchmark before full generation (Story 2.1.1); fallback to Weibull if Hellinger > 0.1 |
| Looker Studio data-source proliferation | Low | Low | Mitigated by explicit view→page→chart mapping (Story 3.3); 4 dashboard pages = 4 data sources |
| **SCD2 silent corruption via NULL = NULL** | **High** if unmitigated | **High** | **Mandatory** COALESCE wrapping in Story 2.8.2; NULL-stability test (2.8.5) catches regressions. Without this, every snapshot run silently duplicates history rows for NULL-bearing employees. Per Research A: highest-risk item in the entire build. |
| Sandbox blocks dbt snapshot MERGE | Low | High | Story 1.2.1 enables billing immediately, before any snapshot work. Documented as Loop 1 prerequisite. |
| **SDV/HMA referential integrity gaps** | N/A (out of stack) | N/A | Per Research B: SDV/HMASynthesizer rejected — documented FK integrity failures + near-naive ML utility + IMDB/AirBnB-only benchmarking. Replaced with custom three-layer simulator (scipy.stats + Gaussian copula + CPT) |
| Loop 4 polish overruns | Medium | Low | Slack in 4-day Loop 4; defer non-essential to post-launch |
| Parallel-track context-switching cost | Medium | Low | Each loop has explicit checkpoint state; ~2h re-orientation cost per re-entry, acceptable |
| **Research C not complete when Loop 3 starts** | RESOLVED | — | Research C complete 2026-05-15 (35 sources, balanced mode, full synthesis). Findings applied to BACKLOG. |
| Using LOW-CONFIDENCE "15% regrettable alarm threshold" on dashboard | Low | Medium | Per Session C: source is single-vendor, no citation. Story 3.4.4 explicitly uses INTERNAL trend comparison (regrettable share over time) instead of external threshold. |

---

## Publication Pre-Flight Checklist (before public push)

- [ ] All path references use lowercase `research/` (case-sensitive filesystems will fail otherwise)
- [ ] `git ls-files | grep -i research` returns only lowercase paths
- [ ] No service account JSON committed (verify `.gitignore` blocks `*.json` at repo root)
- [ ] `profiles.yml` not committed (verify `.gitignore` blocks it)
- [ ] Dashboard link in README is public read-only Looker Studio share URL
- [ ] SYNTHETIC banner visible on dashboard load + README opening paragraph
- [ ] `dbt-project-evaluator` report shows zero Critical findings
- [ ] All model contracts (`v_attrition_features`) pass enforcement

---

## Out of Scope (Explicitly Cut)

- **CI/CD pipeline** — no GitHub Actions for dbt runs; manual `dbt build` is sufficient for portfolio
- **Streaming / Snowpipe / Tasks** — overkill for this dataset volume
- **Multi-region / replication** — not needed
- **External stage (S3 / GCS bucket)** — internal stage on Snowflake, local load to BigQuery
- **Pay equity ML model** — deferred; descriptive view only
- **Oaxaca-Blinder decomposition** — explicitly deferred per Session C's decision rule ("include OB only if explainable in one plain-language sentence on the dashboard"). Progressive OLS (Story 3.6.3) is practitioner-standard and demonstrates competency without requiring specialized econometrics framing. Mention in "What I'd add with more time" (Story 4.5.2).
- **Custom React/D3 frontend** — Looker Studio is the BI layer
- **Dashboard auth / row-level security** — public read-only acceptable for portfolio
- **dbt Cloud** — using dbt-core CLI locally; no Cloud subscription
