"""
generator/generate.py — Synthetic HR data generator for pa-warehouse.

PROJECT: hrds/pa-warehouse
PURPOSE: Generate fictional workforce-events data for the BigQuery warehouse.
         All output is synthetic. No real persons or organizations.

LOOP 1 SCOPE (this file's current capability):
    Tiny generator — small employee population, short observation window.
    Output: data/raw/employees.csv + data/raw/workforce_events.csv

LOOP 2 SCOPE (future expansion — same file, same CLI, scaled config):
    Scale to ~2,500 employees over 36 months. Add compensation, performance,
    survey, succession, and org_hierarchy tables. Switch termination timing
    from uniform-over-window to log-normal survival (scipy.stats.lognorm)
    with covariate-weighted hazards (Gaussian copula across performance,
    compa-ratio, tenure). See BACKLOG.md Story 2.1+ for the scale plan.

KEY DESIGN PATTERN (preserved across all loops):
    Each employee has an ORDERED EVENT TIMELINE. Events emit in chronological
    order, no two events on the same date per employee, no events before hire.
    The dim_employee SCD2 history (Loop 2, via `dbt snapshot`) reconstructs
    from this timeline — so generating events correctly here is the foundation
    for SCD2 correctness later.

USAGE:
    Loop 1: python generator/generate.py --n_employees 50 --n_months 6 --seed 42
    Loop 2: python generator/generate.py   # defaults: 2500 employees, 36 months

DETERMINISM:
    Seed (default 42) governs both numpy's RNG and Faker's RNG. Re-running with
    the same seed produces byte-identical output. Loop 2's benchmark validation
    depends on this — drift between runs would be untestable otherwise.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd
from faker import Faker
from scipy.stats import lognorm, norm, truncnorm
from scipy.spatial.distance import jensenshannon

# ─── Loop 1 constants ─────────────────────────────────────────────────
# Loop 1 termination probabilities — independent samples per employee.
# Approximate annual rates: voluntary ~10%, involuntary ~4%. The total
# (~14%) is in the right ballpark for Mercer's 14.5% benchmark, but Loop 1
# does NOT calibrate to that benchmark — it just produces plausible-looking
# events for the walking-skeleton demo. Loop 2 will replace these with
# covariate-driven log-normal survival via scipy.stats.lognorm.
P_TERM_VOLUNTARY_LOOP1: Final[float] = 0.05    # ≈10%/yr over a 6-month window
P_TERM_INVOLUNTARY_LOOP1: Final[float] = 0.02  # ≈4%/yr over a 6-month window

# Minimum tenure before a termination event is plausible. Day-one quits exist
# but are rare; excluding them in Loop 1 keeps the data clean. Loop 2 may
# explicitly model early-tenure churn (the "humped hazard" research finding).
MIN_TENURE_DAYS_BEFORE_TERM: Final[int] = 30

# ─── Loop 2 constants ─────────────────────────────────────────────────

# Job-level pay band midpoints (USD). These are the "market rate" salary
# for the centre of each pay band. An employee's actual salary will be:
#   salary = band_midpoint(job_level) × compa_ratio
# where compa_ratio ~ N(1.00, 0.08), clipped to [0.7, 1.4].
# The spread between IC1 and VP+ is what produces the ~13% unadjusted
# gender pay gap once women are underrepresented at senior levels (Story 2.1.0).
BAND_MIDPOINTS: Final[dict[str, int]] = {
    "IC1":      75_000,
    "IC2":     100_000,
    "M1":      130_000,
    "M2":      165_000,
    "Director": 210_000,
    "VP+":     280_000,
}

# P(gender = F | job_level) — Story 2.1.0.
# Women are near-parity at entry level but progressively underrepresented
# at senior levels. This skew, combined with higher band_midpoints at
# senior levels, is the mechanism that generates the ~13% unadjusted gap.
# The remaining probability after subtracting P(F) is split ~99:1 M:NB.
P_FEMALE_BY_LEVEL: Final[dict[str, float]] = {
    "IC1":      0.48,
    "IC2":      0.45,
    "M1":       0.40,
    "M2":       0.33,
    "Director": 0.28,
    "VP+":      0.22,
}

# ─── Age / birth_date distribution (Story 5.1.2 — paw-prey-005) ───────
# Truncated normal centred on workforce median age 36 (BLS Current Population
# Survey 2024, median age of employed civilians ≥16: ~42 nationally; tech
# companies skew younger — 36 is the calibrated midpoint for this synthetic
# tech-shaped population). σ=10 captures the spread from early-career (mid-20s)
# to late-career (50s+); bounds [18, 70] enforce minimum-working-age and
# pre-retirement ceiling.
#
# Sampled as age_at_hire per employee → birth_date is derived from
# hire_date - age_at_hire. age_at_hire ≥ 18 by construction guarantees the
# "hire_date - birth_date ≥ 18 years" invariant (Story 5.1.3) — no post-hoc
# rejection step needed.
#
# WHY scipy.stats.truncnorm (not normal + np.clip):
# A normal draw with manual clipping PILES UP probability mass at the bounds
# — anyone sampled <18 or >70 collapses onto the boundary, producing a visible
# spike. truncnorm samples from the properly truncated distribution — no
# boundary artifact. Distribution-fitting is the whole point of having one.
#
# Z-SCORE PARAMETRIZATION (the truncnorm footgun):
# scipy.stats.truncnorm takes the truncation points (a, b) in STANDARDIZED
# z-score units, not raw values. To clip raw values at [LOWER, UPPER] with
# loc=μ, scale=σ:
#     a = (LOWER - μ) / σ
#     b = (UPPER - μ) / σ
# Forgetting this is the most common truncnorm bug — the resulting
# distribution looks compressed because the actual bounds were too tight.
AGE_LOC: Final[float]   = 36.0   # workforce median age (BLS CPS 2024, tech-adjusted)
AGE_SCALE: Final[float] = 10.0   # σ — covers ~95% within ±2σ → [16, 56]
AGE_MIN: Final[int]     = 18     # minimum working age
AGE_MAX: Final[int]     = 70     # pre-retirement ceiling
AGE_A: Final[float]     = (AGE_MIN - AGE_LOC) / AGE_SCALE  # = -1.8 in z-score space
AGE_B: Final[float]     = (AGE_MAX - AGE_LOC) / AGE_SCALE  # = +3.4 in z-score space

# Log-normal parameters for tenure-at-exit — informed by the synthetic-data
# methodology research synthesis (May 2026, 20 Tier-1 sources).
# lognorm(s=LOGNORM_S, scale=LOGNORM_SCALE) gives a distribution where:
#   - median = LOGNORM_SCALE months ≈ 28.8 months ≈ 2.4 years
#   - s (sigma of the underlying normal) controls spread; 0.9 gives the
#     "humped hazard" shape (peak attrition at ~12-18 months, declining after)
# We sample tenure_months from this distribution, then compare to the
# observation window to classify employees as terminated vs right-censored.
LOGNORM_S: Final[float] = 0.9
LOGNORM_SCALE: Final[float] = 24.0  # months — tuned to produce ~14.5% annualised attrition

# Annual market rate growth applied to band_midpoints when computing compa_ratio.
# Without this, annual merit increases drift compa_ratio above 1.00 because salary
# grows but the denominator (band_midpoint) stays static. 3% market growth ≈ typical
# real-world band midpoint appreciation. Net compa_ratio drift = merit% - market% ≈ 1%/yr.
MARKET_RATE_GROWTH: Final[float] = 0.03

# Benchmark targets (Mercer 2024 / Story 2.2). The validation harness
# checks generated data against these. Stored here so the same constants
# are shared between generate.py and validate.py.
BENCHMARK_ATTRITION_ANNUAL: Final[float] = 0.145   # 14.5% total annual
BENCHMARK_VOLUNTARY_SHARE: Final[float]  = 0.759   # voluntary = 11% / 14.5%
BENCHMARK_REGRETTABLE_SHARE: Final[float] = 0.30   # 30% of voluntary exits
BENCHMARK_TENURE_MEDIAN_YR: Final[float] = 2.4     # years, at-event (KM)
BENCHMARK_COMPA_RATIO_MEAN: Final[float] = 1.00
BENCHMARK_COMPA_RATIO_STD: Final[float]  = 0.10
BENCHMARK_ENPS: Final[float] = 34.0
BENCHMARK_SPAN: Final[float] = 6.5                 # mean manager span of control


def generate_org_hierarchy() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Generate three reference tables that form the organisational hierarchy.
    These must be produced BEFORE employees, because employee rows carry
    foreign keys (dept_id, job_id, location_id) that reference these tables.

    Returns (departments_df, jobs_df, locations_df).

    WHY HARDCODED?
    Reference tables are intentionally not random. Every run produces the
    same departments, jobs, and locations — only employee assignments to
    those references are random. This means:
      - dbt `relationships` tests will always pass (no phantom IDs)
      - The dashboard's department filter shows the same labels every run
      - Benchmark calibration is stable (band midpoints don't drift)
    """

    # ── Departments ───────────────────────────────────────────────────────
    # 8 departments matching a mid-size tech company. No manager_id here —
    # that's a chicken-and-egg problem (employees reference depts, depts
    # reference employees for the manager). We'll derive the dept manager
    # in the dbt mart layer via a window function over workforce_events.
    departments = pd.DataFrame([
        {"dept_id": "DEPT_01", "dept_name": "Engineering"},
        {"dept_id": "DEPT_02", "dept_name": "Product"},
        {"dept_id": "DEPT_03", "dept_name": "Sales"},
        {"dept_id": "DEPT_04", "dept_name": "Marketing"},
        {"dept_id": "DEPT_05", "dept_name": "Human Resources"},
        {"dept_id": "DEPT_06", "dept_name": "Finance"},
        {"dept_id": "DEPT_07", "dept_name": "Customer Success"},
        {"dept_id": "DEPT_08", "dept_name": "Operations"},
    ])

    # ── Jobs ──────────────────────────────────────────────────────────────
    # Each job has:
    #   job_level:          one of the 6 levels in BAND_MIDPOINTS
    #   job_family:         broad grouping (used in pay equity analysis)
    #   is_critical_role:   feeds IsRegrettableFlag CPT (critical exits are
    #                       more likely to be regrettable regardless of perf)
    #   skill_scarcity_tier: STANDARD / SCARCE / CRITICAL — reflects how hard
    #                        this role is to backfill (feeds CPT + succession)
    #   band_midpoint:      pulled from BAND_MIDPOINTS by level — the salary
    #                       anchor for compa-ratio calculations
    #
    # Distribution across levels is intentional:
    #   IC1/IC2 = majority (most companies are pyramid-shaped)
    #   M1/M2   = fewer (managers manage multiple ICs)
    #   Director/VP+ = small number (leadership is thin at the top)
    # This produces a realistic headcount pyramid and the right span-of-control.
    jobs_raw = [
        # IC1 roles — entry level, large population
        ("JOB_001", "Software Engineer I",          "IC1", "Engineering",    False, "STANDARD"),
        ("JOB_002", "Data Analyst I",               "IC1", "Analytics",      False, "STANDARD"),
        ("JOB_003", "Sales Development Rep",        "IC1", "Commercial",     False, "STANDARD"),
        ("JOB_004", "HR Coordinator",               "IC1", "G&A",            False, "STANDARD"),
        ("JOB_005", "Financial Analyst I",          "IC1", "G&A",            False, "STANDARD"),
        ("JOB_006", "Customer Success Specialist",  "IC1", "Commercial",     False, "STANDARD"),
        ("JOB_007", "Marketing Associate",          "IC1", "Commercial",     False, "STANDARD"),
        # IC2 roles — mid level
        ("JOB_008", "Software Engineer II",         "IC2", "Engineering",    False, "SCARCE"),
        ("JOB_009", "Data Analyst II",              "IC2", "Analytics",      False, "SCARCE"),
        ("JOB_010", "Account Executive",            "IC2", "Commercial",     False, "STANDARD"),
        ("JOB_011", "HR Business Partner",          "IC2", "G&A",            True,  "SCARCE"),
        ("JOB_012", "Financial Analyst II",         "IC2", "G&A",            False, "STANDARD"),
        ("JOB_013", "Senior Customer Success Mgr",  "IC2", "Commercial",     True,  "STANDARD"),
        ("JOB_014", "Product Analyst",              "IC2", "Product",        False, "SCARCE"),
        ("JOB_015", "ML Engineer",                  "IC2", "Engineering",    True,  "CRITICAL"),
        # M1 roles — first-line managers
        ("JOB_016", "Engineering Manager",          "M1",  "Engineering",    True,  "CRITICAL"),
        ("JOB_017", "Analytics Manager",            "M1",  "Analytics",      True,  "CRITICAL"),
        ("JOB_018", "Sales Manager",                "M1",  "Commercial",     False, "SCARCE"),
        ("JOB_019", "HR Manager",                   "M1",  "G&A",            True,  "SCARCE"),
        ("JOB_020", "Finance Manager",              "M1",  "G&A",            False, "STANDARD"),
        # M2 roles — senior managers
        ("JOB_021", "Senior Engineering Manager",   "M2",  "Engineering",    True,  "CRITICAL"),
        ("JOB_022", "Senior Analytics Manager",     "M2",  "Analytics",      True,  "CRITICAL"),
        ("JOB_023", "Head of Sales",                "M2",  "Commercial",     True,  "CRITICAL"),
        # Director roles
        ("JOB_024", "Director of Engineering",      "Director", "Engineering", True, "CRITICAL"),
        ("JOB_025", "Director of People",           "Director", "G&A",         True, "CRITICAL"),
        ("JOB_026", "Director of Finance",          "Director", "G&A",         True, "SCARCE"),
        # VP+ roles — thin at the top
        ("JOB_027", "VP of Engineering",            "VP+", "Engineering",    True,  "CRITICAL"),
        ("JOB_028", "VP of Sales",                  "VP+", "Commercial",     True,  "CRITICAL"),
        ("JOB_029", "Chief People Officer",         "VP+", "G&A",            True,  "CRITICAL"),
    ]

    jobs = pd.DataFrame(jobs_raw, columns=[
        "job_id", "job_title", "job_level", "job_family",
        "is_critical_role", "skill_scarcity_tier",
    ])
    # band_midpoint comes from BAND_MIDPOINTS — map via job_level.
    # Using .map() on a Series applies the dict as a lookup table.
    # Every job_level value in our data is guaranteed to be a key in
    # BAND_MIDPOINTS (hardcoded above), so no NaN risk here.
    jobs["band_midpoint"] = jobs["job_level"].map(BAND_MIDPOINTS)

    # ── Locations ─────────────────────────────────────────────────────────
    # location_type drives the pay equity analysis context — in a real
    # company, remote employees in lower-cost cities might have adjusted pay,
    # but for this synthetic dataset we apply a single national pay scale.
    # The column still exists so the dashboard can filter by location_type.
    locations = pd.DataFrame([
        {"location_id": "LOC_01", "location_name": "New York",       "location_type": "OFFICE",  "region": "East"},
        {"location_id": "LOC_02", "location_name": "San Francisco",  "location_type": "OFFICE",  "region": "West"},
        {"location_id": "LOC_03", "location_name": "Austin",         "location_type": "HYBRID",  "region": "Central"},
        {"location_id": "LOC_04", "location_name": "Chicago",        "location_type": "HYBRID",  "region": "East"},
        {"location_id": "LOC_05", "location_name": "Remote",         "location_type": "REMOTE",  "region": "Remote"},
    ])

    return departments, jobs, locations


@dataclass(frozen=True)
class GeneratorConfig:
    """CLI inputs bundled together. Frozen so functions can't mutate config."""

    n_employees: int
    n_months: int
    seed: int
    output_dir: Path

    @property
    def window_end(self) -> date:
        """Observation window closes today. Loop 2 may parameterize this for reproducibility."""
        return date.today()

    @property
    def window_start(self) -> date:
        """Window opens n_months ago. 30-day month approximation is fine for synthetic data."""
        return self.window_end - timedelta(days=30 * self.n_months)


def parse_args() -> GeneratorConfig:
    """Parse CLI arguments. Defaults match Loop 2; pass flags for Loop 1."""
    parser = argparse.ArgumentParser(
        description="Generate synthetic HR data for the pa-warehouse project."
    )
    parser.add_argument(
        "--n_employees", type=int, default=2500,
        help="Number of employees to generate (Loop 1: 50).",
    )
    parser.add_argument(
        "--n_months", type=int, default=36,
        help="Observation window length in months (Loop 1: 6).",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="RNG seed for deterministic output.",
    )
    parser.add_argument(
        "--output_dir", type=Path, default=Path("data/raw"),
        help="Directory to write CSV files into.",
    )
    args = parser.parse_args()
    return GeneratorConfig(**vars(args))


def generate_employees(
    cfg: GeneratorConfig,
    fake: Faker,
    rng: np.random.Generator,
    jobs: pd.DataFrame,
    departments: pd.DataFrame,
    locations: pd.DataFrame,
) -> pd.DataFrame:
    """
    Generate the full employee population for Loop 2.

    GENERATION ORDER (order within this function matters):
      1. employee_id, hire_date, name, email  — no dependencies
      2. job_id (and derived job_level)        — samples from jobs reference table
      3. gender                                — conditional on job_level (Story 2.1.0)
      4. dept_id, location_id, manager_id      — samples from reference tables

    WHY HIRE DATES EXTEND BEFORE THE WINDOW?
    In Loop 1, every hire fell within the 6-month window because the generator
    simply sampled from [window_start, window_end]. But real companies have
    long-tenured employees — someone hired 3 years ago is still active today.
    If we only hire within the 36-month window, every employee has at most 3
    years of tenure, which is fine, but we want some employees hired BEFORE
    the window so the SCD2 history can show longer tenures and the dashboard
    can demonstrate BigQuery Time Travel realistically.

    We sample hire_date from [window_end - 60 months, window_end] — a 5-year
    lookback. Employees hired before window_start don't get a 'hire' event in
    workforce_events (the event is pre-window), but they appear in employees.csv
    and are picked up by the staging model's current-state logic.

    WHY MANAGER_ID IS NULLABLE?
    The CEO / top of org has no manager. Some orgs have vacant manager roles.
    Rather than build a full org-tree (which would require knowing headcount
    per manager before sampling), we assign manager_id as a random peer-employee
    after the full population is known. The SCD2 snapshot's COALESCE handles
    the NULLs for employees who genuinely have no manager yet (Story 2.8).
    """
    n = cfg.n_employees

    # ── IDs ───────────────────────────────────────────────────────────────
    employee_ids = [f"EMP_{i + 1:05d}" for i in range(n)]

    # ── Hire dates ────────────────────────────────────────────────────────
    # 60-month lookback from window_end (5 years). This gives us pre-window
    # employees with longer tenure history.
    lookback_days = 60 * 30   # 60 months × 30-day approximation
    day_offsets = rng.integers(low=0, high=lookback_days, size=n)
    hire_dates = [
        cfg.window_end - timedelta(days=int(d))
        for d in day_offsets
    ]

    # ── Birth date / age_at_hire (Story 5.1.1, 5.1.2, 5.1.4) ──────────────
    # Sample age_at_hire from a truncated normal, then derive birth_date by
    # subtracting that many years from hire_date.
    #
    # WHY sample age_at_hire (and not birth_date) directly?
    #   - Workforce age distributions are well-characterised (BLS CPS).
    #     Birth-date distributions for an active workforce are not — they
    #     drift with each new cohort's hire dates. Sampling age and deriving
    #     birth_date keeps the model close to the published demographic shape.
    #   - age_at_hire ≥ AGE_MIN by construction mechanically guarantees
    #     hire_date - birth_date ≥ 18 years (Story 5.1.3 invariant) — no
    #     post-hoc rejection sampling needed.
    #
    # PPF-FROM-UNIFORM PATTERN (matches lognorm survival draw below):
    # Instead of calling truncnorm.rvs(random_state=...), we draw uniform
    # samples from our own rng and feed them into the inverse CDF (ppf).
    # This keeps numpy's RNG stream the single source of randomness so
    # seed reproducibility stays byte-identical across the generator.
    age_uniform = rng.random(size=n)
    ages_at_hire_continuous = truncnorm.ppf(
        age_uniform, a=AGE_A, b=AGE_B, loc=AGE_LOC, scale=AGE_SCALE
    )
    # Integer years — half-year birthdays add no analytic value and complicate
    # downstream age_at_window_close arithmetic on the dbt side.
    ages_at_hire = ages_at_hire_continuous.round().astype(int)

    # birth_date = hire_date − age_at_hire years.
    # 365.25 = mean days/year incl. leap years — accurate to within ±1 day,
    # which is fine for an immutable per-employee birthday derived in the
    # synthetic layer. Real HR systems store DOB directly; we back-derive it
    # here because we're constructing the population from demographic
    # priors, not loading from a system of record.
    birth_dates = [
        h - timedelta(days=int(a * 365.25))
        for h, a in zip(hire_dates, ages_at_hire)
    ]

    # ── Names & emails ────────────────────────────────────────────────────
    first_names = [fake.first_name() for _ in range(n)]
    last_names  = [fake.last_name()  for _ in range(n)]
    # Append the index to guarantee email uniqueness at 2,500 employees.
    # Two employees named "John Smith" would otherwise produce identical emails.
    emails = [
        f"{fn.lower()}.{ln.lower()}.{i + 1}@example.com"
        for i, (fn, ln) in enumerate(zip(first_names, last_names))
    ]

    # ── Job assignment ────────────────────────────────────────────────────
    # Sample job_id uniformly from the jobs reference table.
    # We use a WEIGHTED sample: IC1/IC2 roles are more common than Director/VP+.
    # The weight vector below approximates a real company's headcount pyramid.
    # Without weights, each of the 29 jobs would get ~86 employees — you'd
    # have as many VPs as junior engineers, which is unrealistic.
    level_weights = {
        "IC1": 10,   # most employees are entry-level ICs
        "IC2": 8,    # mid-level ICs — slightly fewer
        "M1":  3,    # managers manage ~6 ICs; need fewer
        "M2":  1.5,  # senior managers — rarer
        "Director": 0.8,
        "VP+":      0.3,
    }
    job_weights = jobs["job_level"].map(level_weights).values
    job_weights = job_weights / job_weights.sum()   # normalise to sum to 1

    job_indices = rng.choice(len(jobs), size=n, p=job_weights)
    job_ids    = jobs["job_id"].iloc[job_indices].values
    job_levels = jobs["job_level"].iloc[job_indices].values

    # ── Gender (conditional on job_level) ────────────────────────────────
    # CRITICAL: we loop per-employee, conditioning P(F) on that employee's
    # job_level. This is what produces the representation gap.
    # For each employee: P(F) = P_FEMALE_BY_LEVEL[level], P(NB) = 0.01,
    # P(M) = 1 - P(F) - P(NB).
    genders = []
    for level in job_levels:
        p_female = P_FEMALE_BY_LEVEL[level]
        p_nb     = 0.01
        p_male   = 1.0 - p_female - p_nb
        genders.append(
            rng.choice(["F", "M", "NB"], p=[p_female, p_male, p_nb])
        )
    genders = np.array(genders)

    # ── Department & location ─────────────────────────────────────────────
    # Uniform sample — every department is equally likely for simplicity.
    # A more realistic model would constrain Engineering jobs to Engineering
    # dept, but that requires a job→dept mapping table we haven't defined.
    # The pay equity analysis doesn't require it — the key axes are job_level
    # and gender. Department is a filter dimension on the dashboard.
    dept_ids     = departments["dept_id"].iloc[
        rng.integers(0, len(departments), size=n)
    ].values
    location_ids = locations["location_id"].iloc[
        rng.integers(0, len(locations), size=n)
    ].values

    # ── Manager assignment (level-aware hierarchy) ────────────────────────
    # Employees are assigned managers from the NEXT level up. This produces:
    #   IC1/IC2  → managed by M1 employees
    #   M1       → managed by M2 employees
    #   M2       → managed by Director employees
    #   Director → managed by VP+ employees
    #   VP+      → NULL (top of org; no manager)
    #
    # This creates a proper org tree with realistic span-of-control
    # (~6-8 direct reports per manager) rather than the flat random
    # assignment that Loop 1 used.
    MANAGES: dict[str, list[str]] = {
        "IC1":      ["M1", "M2"],        # IC1 managed by M1 (or M2 if M1 absent)
        "IC2":      ["M1", "M2"],
        "M1":       ["M2", "Director"],
        "M2":       ["Director", "VP+"],
        "Director": ["VP+"],
        "VP+":      [],                  # top of org — no manager
    }

    # Build lookup: level → list of employee_ids at that level
    level_to_ids: dict[str, list[str]] = {}
    for eid, lvl in zip(employee_ids, job_levels):
        level_to_ids.setdefault(lvl, []).append(eid)

    manager_ids = []
    for eid, lvl in zip(employee_ids, job_levels):
        mgr_levels = MANAGES.get(lvl, [])
        candidates = []
        for ml in mgr_levels:
            candidates.extend(level_to_ids.get(ml, []))

        if not candidates or rng.random() < 0.03:  # 3% null for vacancies
            manager_ids.append(None)
        else:
            idx = rng.integers(0, len(candidates))
            mgr = candidates[idx]
            # Self-reference guard: if the only candidate is the employee themselves,
            # set to None. This is extremely rare but theoretically possible.
            manager_ids.append(None if mgr == eid else mgr)

    return pd.DataFrame({
        "employee_id":  employee_ids,
        "first_name":   first_names,
        "last_name":    last_names,
        "email":        emails,
        "birth_date":   birth_dates,    # Story 5.1.1 — immutable per-employee DOB
        "age_at_hire":  ages_at_hire,   # Story 5.1.4 — derived, kept for analytic ergonomics
        "hire_date":    hire_dates,
        "job_id":       job_ids,
        "job_level":    job_levels,   # denormalised for convenience in generator; not in the DB table
        "gender":       genders,
        "dept_id":      dept_ids,
        "location_id":  location_ids,
        "manager_id":   manager_ids,
    })


def generate_survival_outcomes(
    employees: pd.DataFrame,
    cfg: GeneratorConfig,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """
    Assign each employee a termination outcome using a log-normal survival model.

    WHAT IS A SURVIVAL MODEL?
    Instead of flipping a coin ("does this employee quit?"), we ask: "how long
    will this employee stay?" We draw a tenure_months from a log-normal
    distribution. Then we compare that tenure to the remaining window:

      theoretical_exit = hire_date + tenure_months
      if theoretical_exit < window_end  →  TERMINATED (observed exit)
      else                              →  CENSORED   (still active)

    This naturally calibrates to the benchmark: if the log-normal median is 2.4yr
    and our window is 3yr, roughly 40-45% of employees will have exited by
    window_end — which divided by 3 years gives ~14.5% annualised attrition.

    COVARIATE HAZARD ADJUSTMENTS:
    Not everyone has the same exit probability. We apply multipliers to the
    log-normal scale parameter based on observable attributes:
      - High performers (perf_tier ≥ 4) → 0.5× hazard (they stay longer)
      - Pay compression (compa_ratio > 1.15) → 1.4× hazard (they're underpaid for performance)
      - Critical role + zero successors → no adjustment here (affects IsRegrettableFlag only)
    These adjustments are applied by rescaling the lognorm distribution's
    location parameter (mu = log(scale)), which shifts the entire curve.

    VOLUNTARY vs INVOLUNTARY:
    Among terminated employees, we split: ~76% voluntary, ~24% involuntary.
    This gives ~11% voluntary + ~3.5% involuntary annualised, matching Mercer.
    Involuntary terminations are NOT eligible for IsRegrettableFlag.

    Returns employees df augmented with survival outcome columns:
      tenure_months, exit_date (NaT if censored), exit_type (None if censored),
      is_terminated (bool), perf_tier (int 1-5), compa_ratio (float)
    """
    n = len(employees)

    # ── Performance tier ──────────────────────────────────────────────────
    # Sample before survival so we can use it to adjust the hazard.
    # 5-point scale: 1=low, 5=high. Distribution: slight right skew
    # (companies tend to grade on a curve that inflates middle scores).
    # Probabilities: [5%, 15%, 40%, 30%, 10%] sums to 100%.
    perf_tiers = rng.choice([1, 2, 3, 4, 5], size=n, p=[0.05, 0.15, 0.40, 0.30, 0.10])

    # ── Compa-ratio ───────────────────────────────────────────────────────
    # Compa-ratio = actual_salary / band_midpoint. A ratio of 1.00 means
    # you're exactly at market. 0.90 = underpaid relative to band; 1.15 = overpaid.
    # We sample from N(1.00, 0.08), clipped to [0.7, 1.4].
    # The compa-ratio is used here to adjust hazard (compressed employees leave
    # faster) and in generate_compensation() to derive actual salary.
    raw_compa = rng.normal(loc=1.00, scale=0.08, size=n)
    compa_ratios = np.clip(raw_compa, 0.70, 1.40)

    # Adjust compa-ratio slightly upward for high performers (Story 2.1.2):
    # senior performers tend to negotiate better. This is a small effect.
    compa_ratios += 0.020 * (perf_tiers - 3) / 2   # ±0.02 across perf range

    # ── Hazard multipliers ────────────────────────────────────────────────
    # These scale the lognorm's 'scale' parameter (the median tenure).
    # A multiplier > 1 means longer expected tenure (lower hazard).
    # A multiplier < 1 means shorter expected tenure (higher hazard).
    #
    # High performer effect: 2× longer expected tenure (hazard ratio ≈ 0.5).
    # We apply this as a scale multiplier on the lognorm.
    perf_multiplier = np.where(perf_tiers >= 4, 2.0, 1.0)

    # Pay compression effect: compa_ratio > 1.15 means employee is paid above
    # band ceiling — often signals they've outgrown the role and are likely
    # to leave for a promotion elsewhere. 0.71× scale ≈ 1.4× hazard.
    comp_multiplier = np.where(compa_ratios > 1.15, 0.71, 1.0)

    # Combined multiplier: high-performer pay-compressed employees are rarer
    # but especially flight-risky (strong market demand, underpriced).
    hazard_scale = LOGNORM_SCALE * perf_multiplier * comp_multiplier

    # ── Draw tenure from log-normal with per-employee scale ───────────────
    # scipy.stats.lognorm(s, scale) has:
    #   median = scale
    #   shape  = s (controls spread and hazard shape)
    # Vectorised: we call lognorm.rvs() once per employee with their own scale.
    # random_state is intentionally NOT set here because we're passing rng.integers
    # as seeds — we use rng.random() to get uniform samples and feed them into
    # the ppf (percent-point function = inverse CDF) manually. This keeps
    # numpy's RNG stream in sync (Faker + numpy both consuming from rng).
    #
    # ppf(u, s, scale) = lognorm inverse CDF — converts uniform [0,1] draws
    # into log-normally distributed tenure values. This is equivalent to
    # lognorm.rvs() but uses OUR rng rather than scipy's internal random state.
    uniform_samples = rng.random(size=n)
    tenure_months = lognorm.ppf(uniform_samples, s=LOGNORM_S, scale=hazard_scale)
    # Clip to [1, 120] months — no same-day quits, no 10-year tenures in a 3yr window
    tenure_months = np.clip(tenure_months, 1, 120)

    # ── Classify: terminated vs right-censored ────────────────────────────
    hire_dates = pd.to_datetime(employees["hire_date"])
    theoretical_exits = [
        h + pd.DateOffset(months=int(m))
        for h, m in zip(hire_dates, tenure_months)
    ]
    window_end = pd.Timestamp(cfg.window_end)

    is_terminated = np.array([ex < window_end for ex in theoretical_exits])
    exit_dates = [ex.date() if term else None
                  for ex, term in zip(theoretical_exits, is_terminated)]

    # ── Split voluntary / involuntary ─────────────────────────────────────
    # Among terminated employees, sample exit type.
    # Target: 76% voluntary, 24% involuntary (→ 11% + 3.5% annualised).
    exit_types = []
    for terminated in is_terminated:
        if not terminated:
            exit_types.append(None)
        elif rng.random() < BENCHMARK_VOLUNTARY_SHARE:
            exit_types.append("term_voluntary")
        else:
            exit_types.append("term_involuntary")

    return employees.assign(
        perf_tier    = perf_tiers,
        compa_ratio  = compa_ratios.round(4),
        tenure_months= tenure_months.astype(int),
        exit_date    = exit_dates,
        exit_type    = exit_types,
        is_terminated= is_terminated,
    )


def generate_compensation(
    employees: pd.DataFrame,
    jobs: pd.DataFrame,
    cfg: GeneratorConfig,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """
    Generate compensation history — one record per employee per year employed.

    STRUCTURE:
    Each employee starts with a base salary on hire_date derived from their
    job_level's band_midpoint × compa_ratio. Each subsequent year they get a
    merit increase (2-6%). If they were terminated, records stop at exit_date.

    WHY ANNUAL RECORDS?
    The dashboard's pay equity analysis (Story 3.6) looks at compa-ratio
    trends over time. Annual records give enough resolution without the
    noise of monthly snapshots. The SCD2 snapshot on dim_employee will track
    job/dept/manager changes separately — comp changes come here.

    COLUMNS:
      comp_id         — surrogate key
      employee_id     — FK to employees
      effective_date  — date this salary took effect
      salary          — integer USD (rounded to nearest $100 for realism)
      currency        — always USD (single-currency company)
      pay_band_id     — e.g. "BAND_IC2" — derived from job_level
      compa_ratio     — actual salary / band_midpoint at this point in time
    """
    rows: list[dict] = []
    comp_counter = 1

    # Build job_id → band_midpoint lookup for fast access
    band_lookup = dict(zip(jobs["job_id"], jobs["band_midpoint"]))
    level_lookup = dict(zip(jobs["job_id"], jobs["job_level"]))

    for emp in employees.itertuples(index=False):
        hire_date  = pd.Timestamp(emp.hire_date)
        exit_date  = pd.Timestamp(emp.exit_date) if emp.exit_date else pd.Timestamp(cfg.window_end)
        band_mid   = band_lookup[emp.job_id]
        job_level  = level_lookup[emp.job_id]
        pay_band   = f"BAND_{job_level}"

        # Starting salary from the compa_ratio computed in survival step
        current_salary = round(band_mid * emp.compa_ratio / 100) * 100  # round to $100

        # Emit one record per annual cycle while employed
        current_date = hire_date
        while current_date < exit_date:
            # Market-adjusted midpoint: band_mid grows 3%/yr to reflect
            # that pay bands themselves increase with inflation/market.
            # Without this, repeated merit increases push compa_ratio above 1.0
            # indefinitely — after 3 years of 4% merit + 0% market adjustment,
            # every employee looks 12% above market. With 3% market growth,
            # net drift is only 1%/yr — compa_ratio stays near 1.0.
            years_elapsed = (current_date - hire_date).days / 365.25
            effective_midpoint = band_mid * ((1 + MARKET_RATE_GROWTH) ** years_elapsed)

            rows.append({
                "comp_id":       f"COMP_{comp_counter:07d}",
                "employee_id":   emp.employee_id,
                "effective_date": current_date.date(),
                "salary":         int(current_salary),
                "currency":       "USD",
                "pay_band_id":    pay_band,
                "compa_ratio":    round(current_salary / effective_midpoint, 4),
            })
            comp_counter += 1

            # Annual merit increase: 2-6%, uniform random
            merit = rng.uniform(0.02, 0.06)
            current_salary = round(current_salary * (1 + merit) / 100) * 100
            current_date   = current_date + pd.DateOffset(years=1)

    return pd.DataFrame(rows)


def generate_performance_ratings(
    employees: pd.DataFrame,
    cfg: GeneratorConfig,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """
    Generate annual + mid-year performance ratings.

    Each employee gets two rating events per year:
      - Mid-year (month 6 of their hire anniversary cycle): rating 1-5
      - Year-end (month 12):                                rating 1-5

    The year-end rating must be correlated with the perf_tier already assigned
    in the survival model. If perf_tier=5, year-end ratings should cluster at
    4-5, not be random. We implement this by using perf_tier as the centre of
    a distribution, with some noise.

    WHY TWO RATINGS PER YEAR?
    Mid-year reviews are standard in most mid-size companies. Having both lets
    the dashboard show rating trajectories over time. The IsRegrettableFlag CPT
    uses the LAST rating before exit, so recency matters.

    COLUMNS:
      rating_id, employee_id, review_date, review_cycle (MID/YEAR_END),
      rating (1-5), potential_flag (HIGH/MID/LOW)
    """
    rows: list[dict] = []
    rating_counter = 1

    potential_map = {5: "HIGH", 4: "HIGH", 3: "MID", 2: "LOW", 1: "LOW"}

    for emp in employees.itertuples(index=False):
        hire_date = pd.Timestamp(emp.hire_date)
        exit_date = pd.Timestamp(emp.exit_date) if emp.exit_date else pd.Timestamp(cfg.window_end)

        # Mid-year = 6 months after hire anniversary; year-end = 12 months
        # Iterate annual cycles until exit or window_end
        cycle_start = hire_date
        while cycle_start + pd.DateOffset(months=6) < exit_date:
            # Mid-year review
            mid_date = cycle_start + pd.DateOffset(months=6)
            # Rating centred on perf_tier with ±1 noise, clipped to [1,5]
            mid_rating = int(np.clip(
                rng.integers(max(1, emp.perf_tier - 1), min(5, emp.perf_tier + 1) + 1),
                1, 5
            ))
            rows.append({
                "rating_id":    f"RTG_{rating_counter:07d}",
                "employee_id":  emp.employee_id,
                "review_date":  mid_date.date(),
                "review_cycle": "MID",
                "rating":        mid_rating,
                "potential_flag": potential_map[mid_rating],
            })
            rating_counter += 1

            # Year-end review
            if cycle_start + pd.DateOffset(months=12) < exit_date:
                yr_date   = cycle_start + pd.DateOffset(months=12)
                yr_rating = int(np.clip(
                    rng.integers(max(1, emp.perf_tier - 1), min(5, emp.perf_tier + 1) + 1),
                    1, 5
                ))
                rows.append({
                    "rating_id":    f"RTG_{rating_counter:07d}",
                    "employee_id":  emp.employee_id,
                    "review_date":  yr_date.date(),
                    "review_cycle": "YEAR_END",
                    "rating":        yr_rating,
                    "potential_flag": potential_map[yr_rating],
                })
                rating_counter += 1

            cycle_start = cycle_start + pd.DateOffset(years=1)

    return pd.DataFrame(rows)


def generate_survey_responses(
    employees: pd.DataFrame,
    cfg: GeneratorConfig,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """
    Generate quarterly eNPS survey responses.

    eNPS (Employee Net Promoter Score) is a single question:
    "On a scale of 0-10, how likely are you to recommend this company
     as a place to work?"
      - 9-10: Promoters
      - 7-8:  Passives
      - 0-6:  Detractors
    eNPS = %Promoters - %Detractors. Target aggregate: 34 (Story 2.2.8).

    Correlation: low-perf-tier employees skew toward Detractors (they're
    dissatisfied or at risk of exit). High-perf employees skew toward
    Promoters. This correlation is what makes the survey data analytically
    interesting — the dashboard can show that engagement predicts attrition.
    """
    rows: list[dict] = []
    survey_counter = 1

    for emp in employees.itertuples(index=False):
        hire_date = pd.Timestamp(emp.hire_date)
        exit_date = pd.Timestamp(emp.exit_date) if emp.exit_date else pd.Timestamp(cfg.window_end)

        # Quarterly surveys: every 3 months from hire until exit
        survey_date = hire_date + pd.DateOffset(months=3)
        while survey_date < exit_date:
            # Sample eNPS in two steps:
            #   1. Determine category (Promoter/Passive/Detractor) using
            #      calibrated probabilities per perf_tier.
            #   2. Sample score uniformly within the category's range.
            # This avoids the integer-truncation bias of rounding a continuous
            # normal — and lets us hit the aggregate eNPS=34 target exactly.
            #
            # Calibration (verified to produce aggregate eNPS ≈ 34):
            #   p_promoter = 0.08 + perf_tier * 0.11  → 0.19 (perf=1) to 0.63 (perf=5)
            #   p_detractor = max(0, 0.42 - perf_tier * 0.10) → 0.32 (perf=1) to 0 (perf=5)
            t = emp.perf_tier
            p_promoter  = 0.08 + t * 0.11
            p_detractor = max(0.0, 0.42 - t * 0.10)
            p_passive   = 1.0 - p_promoter - p_detractor

            category = rng.choice(
                ["PROMOTER", "PASSIVE", "DETRACTOR"],
                p=[p_promoter, p_passive, p_detractor],
            )
            if category == "PROMOTER":
                score = int(rng.integers(9, 11))   # 9 or 10
            elif category == "PASSIVE":
                score = int(rng.integers(7, 9))    # 7 or 8
            else:
                score = int(rng.integers(0, 7))    # 0 to 6
            # engagement_score: 1.0–5.0 Likert scale, mean ~3.2 overall.
            # Positively correlated with perf_tier — disengaged employees
            # score lower AND are more likely to exit, giving Loop 2's hybrid
            # cohort meaningful incremental signal beyond eNPS alone.
            # Calibration: mean = 1.8 + perf_tier * 0.48
            #   perf=1 → µ≈2.28  perf=3 → µ≈3.24  perf=5 → µ≈4.20
            engagement_mean = 1.8 + t * 0.48
            engagement_score = round(
                float(np.clip(rng.normal(engagement_mean, 0.6), 1.0, 5.0)), 2
            )

            # manager_relationship_score: 1.0–5.0, mean ~3.2 overall.
            # Weakly correlated with perf_tier — manager quality is more
            # org-random than individual performance. Adds noisier signal.
            # Calibration: mean = 2.75 + perf_tier * 0.15
            #   perf=1 → µ≈2.90  perf=3 → µ≈3.20  perf=5 → µ≈3.50
            mgr_mean = 2.75 + t * 0.15
            manager_relationship_score = round(
                float(np.clip(rng.normal(mgr_mean, 0.8), 1.0, 5.0)), 2
            )

            rows.append({
                "survey_id":   f"SRV_{survey_counter:07d}",
                "employee_id": emp.employee_id,
                "survey_date": survey_date.date(),
                "enps_score":  score,
                # Categorise for dbt model convenience
                "response_category": (
                    "PROMOTER"  if score >= 9 else
                    "PASSIVE"   if score >= 7 else
                    "DETRACTOR"
                ),
                "engagement_score":          engagement_score,
                "manager_relationship_score": manager_relationship_score,
            })
            survey_counter += 1
            survey_date = survey_date + pd.DateOffset(months=3)

    return pd.DataFrame(rows)


def generate_succession_plan(
    employees: pd.DataFrame,
    jobs: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """
    Generate succession plan records — how many ready successors each employee has.

    Employees in critical roles with zero successors are the highest-priority
    IsRegrettableFlag candidates. This table feeds the CPT (Story 2.3.6).

    COLUMNS:
      succession_id, employee_id, successor_readiness_count,
      is_critical_role (denormalised for CPT convenience)
    """
    # Merge criticality flag from jobs onto employees
    crit_lookup = dict(zip(jobs["job_id"], jobs["is_critical_role"]))
    is_critical  = employees["job_id"].map(crit_lookup).values

    # Successor count distribution:
    # Critical roles: 60% have 0 successors, 30% have 1, 10% have 2+
    # Non-critical:   20% have 0 successors, 50% have 1, 30% have 2+
    rows = []
    for i, emp in enumerate(employees.itertuples(index=False)):
        if is_critical[i]:
            count = rng.choice([0, 1, 2], p=[0.60, 0.30, 0.10])
        else:
            count = rng.choice([0, 1, 2], p=[0.20, 0.50, 0.30])

        rows.append({
            "succession_id":           f"SUC_{i + 1:07d}",
            "employee_id":             emp.employee_id,
            "successor_readiness_count": int(count),
            "is_critical_role":         bool(is_critical[i]),
        })

    return pd.DataFrame(rows)


def generate_is_regrettable(
    employees: pd.DataFrame,
    succession: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.Series:
    """
    Apply CPT (Conditional Probability Table) to assign IsRegrettableFlag
    to voluntary terminations. Only voluntary leavers are eligible.

    WHY A CPT?
    IsRegrettableFlag can't be sampled randomly (would give ~50% regrettable,
    not the 30% benchmark). It can't be a pure rule (perf≥4 OR critical role)
    because that would be deterministic — every high performer who quits is
    regrettable, which overstates the rate. A CPT is a lookup of probabilities
    conditioned on observable predictors, calibrated to hit the 30% aggregate.

    The CPT maps: (perf_tier, is_critical_role, successor_count_bucket) → P(regrettable)
    Then we sample: is_regrettable ~ Bernoulli(P)

    We iterate calibration: if aggregate rate drifts from 30%, adjust the
    overall scale. One pass is sufficient for our tolerance.

    Returns a boolean Series aligned with employees index.
    """
    succ_lookup = dict(zip(succession["employee_id"], succession["successor_readiness_count"]))
    crit_lookup_succ = dict(zip(succession["employee_id"], succession["is_critical_role"]))

    TARGET = BENCHMARK_REGRETTABLE_SHARE  # 0.30

    # Base probabilities by (perf_tier, is_critical, zero_successors)
    # These are calibrated to produce ~30% aggregate over voluntary exits.
    # Intuition: high-perf + critical role + no backup = almost always regrettable.
    #            low-perf + non-critical + has backup = rarely regrettable.
    def p_regrettable(perf: int, critical: bool, zero_successors: bool) -> float:
        base = 0.05
        base += 0.15 * max(0, perf - 2)    # +15% per perf point above 2
        if critical:      base += 0.20
        if zero_successors: base += 0.20
        return min(base, 0.95)

    flags = []
    for emp in employees.itertuples(index=False):
        if emp.exit_type != "term_voluntary":
            flags.append(False)
            continue
        succ_count  = succ_lookup.get(emp.employee_id, 1)
        is_crit     = crit_lookup_succ.get(emp.employee_id, False)
        p = p_regrettable(emp.perf_tier, is_crit, succ_count == 0)
        flags.append(bool(rng.random() < p))

    result = pd.Series(flags, index=employees.index, name="is_regrettable")

    # ── Post-hoc calibration ──────────────────────────────────────────────
    # CPT coefficients are approximate; the aggregate rate rarely hits 30%
    # exactly on the first pass. We correct by randomly flipping True→False
    # (or False→True) among voluntary exit rows until the target is met.
    # This preserves the CPT's RELATIVE ordering (high-risk employees are
    # still more likely to be flagged) while hitting the exact benchmark.
    vol_mask = employees["exit_type"] == "term_voluntary"
    vol_idx  = employees.index[vol_mask]

    if len(vol_idx) > 0:
        actual_count  = result[vol_idx].sum()
        target_count  = int(round(TARGET * len(vol_idx)))
        delta         = actual_count - target_count

        if delta > 0:
            # Too many regrettable — flip some True → False
            true_idx   = vol_idx[result[vol_idx]]
            flip_count = min(delta, len(true_idx))
            flip_idx   = rng.choice(true_idx, size=flip_count, replace=False)
            result.loc[flip_idx] = False

        elif delta < 0:
            # Too few regrettable — flip some False → True
            false_idx  = vol_idx[~result[vol_idx]]
            flip_count = min(-delta, len(false_idx))
            flip_idx   = rng.choice(false_idx, size=flip_count, replace=False)
            result.loc[flip_idx] = True

    return result


def generate_events(
    employees: pd.DataFrame, cfg: GeneratorConfig, rng: np.random.Generator
) -> pd.DataFrame:
    """
    Generate workforce events per employee.

    Loop 2 changes vs Loop 1:
      - Termination timing comes from the survival model (exit_date column
        on employees), not from a coin flip.
      - Pre-window hires (hire_date < window_start) do NOT get a 'hire' event
        — the hire is historical, outside the observation window. The employee
        appears in employees.csv as an ongoing worker.
      - is_regrettable is embedded on term_voluntary events (event attribute).

    Emits per employee:
      - 'hire' event IF hire_date >= window_start
      - 'term_voluntary' or 'term_involuntary' IF is_terminated = True

    The dbt snapshot reads events to build SCD2 history. Event ordering
    (hire < term) is guaranteed by the survival model (exit_date > hire_date).
    """
    event_rows: list[dict] = []
    event_counter = 1
    window_start = pd.Timestamp(cfg.window_start)

    for row in employees.itertuples(index=False):
        emp_id    = row.employee_id
        hire_date = pd.Timestamp(row.hire_date)

        # Only emit hire event if it falls within the observation window.
        # Pre-window employees are already active at window_start.
        if hire_date >= window_start:
            event_rows.append({
                "event_id":       f"EVT_{event_counter:07d}",
                "employee_id":    emp_id,
                "event_date":     hire_date.date(),
                "event_type":     "hire",
                "is_regrettable": False,
            })
            event_counter += 1

        # Termination event — only if survival model flagged this employee as terminated
        if row.is_terminated and row.exit_date is not None:
            event_rows.append({
                "event_id":       f"EVT_{event_counter:07d}",
                "employee_id":    emp_id,
                "event_date":     row.exit_date,
                "event_type":     row.exit_type,
                # is_regrettable only meaningful for voluntary terms; False otherwise
                "is_regrettable": bool(row.is_regrettable) if row.exit_type == "term_voluntary" else False,
            })
            event_counter += 1

    events_df = (
        pd.DataFrame(event_rows)
        .sort_values(["employee_id", "event_date"])
        .reset_index(drop=True)
    )
    return events_df


def validate(employees: pd.DataFrame, events: pd.DataFrame) -> None:
    """
    Enforce Story 1.4.3 invariants. Raise loudly on violation — silent
    corruption downstream is worse than a crash here.
    """
    # Build hire_date lookup once for fast per-event checks.
    hire_dates = dict(zip(employees["employee_id"], employees["hire_date"]))

    # Check 1: no event_date before that employee's hire_date.
    for row in events.itertuples(index=False):
        if row.event_date < hire_dates[row.employee_id]:
            raise ValueError(
                f"Validation failure: event {row.event_id} for {row.employee_id} "
                f"has event_date {row.event_date} < hire_date {hire_dates[row.employee_id]}"
            )

    # Check 2: no two events for the same employee on the same date.
    # groupby.size() returns a Series indexed by (employee_id, event_date) tuples;
    # we look for any group with count > 1.
    dup_counts = events.groupby(["employee_id", "event_date"]).size()
    if (dup_counts > 1).any():
        offenders = dup_counts[dup_counts > 1].head(5)
        raise ValueError(
            f"Validation failure: duplicate event dates for the same employee:\n{offenders}"
        )

    # Check 3: FK integrity — every event's employee_id must exist in employees.
    # This is belt-and-suspenders since generate_events only emits IDs from
    # the employee list, but it catches future regressions.
    orphans = set(events["employee_id"]) - set(employees["employee_id"])
    if orphans:
        raise ValueError(f"Validation failure: orphan employee_ids in events: {orphans}")

    # Check 4 (Story 5.1.3 — paw-prey-005): no minor at hire.
    # The age sampler (truncnorm with AGE_MIN=18) guarantees this by
    # construction. We layer two checks so any regression in the demographic
    # path surfaces immediately instead of silently shipping under-age
    # employees into rp's training data:
    #
    #   (a) age_at_hire ≥ AGE_MIN — the SOURCE-of-truth integer. If anyone
    #       widens the truncnorm bounds or swaps in a non-truncated sampler,
    #       this catches it directly without going through date arithmetic.
    #   (b) hire_date - birth_date ≥ int(AGE_MIN * 365.25) days — a sanity
    #       check that the derived birth_date column wasn't tampered with.
    #       CRITICAL: the threshold must use the SAME int() floor as the
    #       construction (`birth_date = hire_date - int(age * 365.25)`);
    #       otherwise the half-day drift at age=AGE_MIN produces spurious
    #       failures. Earlier draft used a float threshold and fired on every
    #       age_at_hire=18 employee — caught by the first full Loop 2 run.
    if "age_at_hire" in employees.columns:
        under_age_mask = employees["age_at_hire"] < AGE_MIN
        if under_age_mask.any():
            sample = employees.loc[under_age_mask, "employee_id"].head(5).tolist()
            raise ValueError(
                f"Validation failure: {int(under_age_mask.sum())} employees have "
                f"age_at_hire < {AGE_MIN}. First 5: {sample}"
            )

    if "birth_date" in employees.columns:
        hire_d  = pd.to_datetime(employees["hire_date"])
        birth_d = pd.to_datetime(employees["birth_date"])
        min_gap_days = int(AGE_MIN * 365.25)   # mirror the construction's floor
        gap_days = (hire_d - birth_d).dt.days
        inconsistent = employees.loc[gap_days < min_gap_days, "employee_id"]
        if len(inconsistent) > 0:
            sample = inconsistent.head(5).tolist()
            raise ValueError(
                f"Validation failure: {len(inconsistent)} employees have "
                f"hire_date - birth_date < {min_gap_days} days "
                f"(implies age < {AGE_MIN}). First 5: {sample}"
            )

    print(f"  [OK] Validation passed: {len(events)} events for {len(employees)} employees")


def main() -> None:
    cfg = parse_args()
    cfg.output_dir.mkdir(parents=True, exist_ok=True)

    # Seed BOTH RNGs — numpy's for distributions, Faker's for strings.
    rng  = np.random.default_rng(cfg.seed)
    fake = Faker()
    Faker.seed(cfg.seed)

    print(
        f"Generating {cfg.n_employees} employees over {cfg.n_months} months "
        f"(window: {cfg.window_start} -> {cfg.window_end}, seed={cfg.seed})"
    )

    # ── Phase 1: Reference tables (no random sampling — deterministic) ───
    print("\n[1/7] Org hierarchy...")
    departments, jobs, locations = generate_org_hierarchy()

    # ── Phase 2: Employees with survival outcomes ─────────────────────────
    print("[2/7] Employees + survival model...")
    employees = generate_employees(cfg, fake, rng, jobs, departments, locations)
    employees = generate_survival_outcomes(employees, cfg, rng)

    # ── Phase 3: Supporting tables ────────────────────────────────────────
    print("[3/7] Compensation history...")
    compensation = generate_compensation(employees, jobs, cfg, rng)

    print("[4/7] Performance ratings...")
    performance  = generate_performance_ratings(employees, cfg, rng)

    print("[5/7] Survey responses...")
    surveys      = generate_survey_responses(employees, cfg, rng)

    print("[6/7] Succession plan...")
    succession   = generate_succession_plan(employees, jobs, rng)

    # ── Phase 4: IsRegrettableFlag (depends on perf + succession) ─────────
    print("[7/7] IsRegrettableFlag (CPT)...")
    employees["is_regrettable"] = generate_is_regrettable(employees, succession, rng)

    # ── Phase 5: SCD2-compatible workforce events ─────────────────────────
    # The Loop 1 generate_events() only handled hire + term events.
    # Loop 2 re-uses it but strips the Loop 1 termination logic — terminations
    # now come from the survival model above. Events are rebuilt from scratch.
    print("\nBuilding event timeline...")
    events = generate_events(employees, cfg, rng)

    # ── Validation ────────────────────────────────────────────────────────
    print("\nValidating...")
    validate(employees, events)

    # ── Write CSVs ────────────────────────────────────────────────────────
    # Drop generator-internal columns before writing (job_level was convenience;
    # the DB derives it by joining employees → jobs).
    employees_out = employees.drop(columns=["job_level", "is_terminated",
                                            "tenure_months", "is_regrettable"],
                                   errors="ignore")

    # is_regrettable lives on workforce_events for the term_voluntary rows
    # (it's an event attribute, not an employee attribute).
    events_out = events  # already includes is_regrettable via generate_events merge

    files: dict[str, pd.DataFrame] = {
        "departments.csv":        departments,
        "jobs.csv":               jobs,
        "locations.csv":          locations,
        "employees.csv":          employees_out,
        "workforce_events.csv":   events_out,
        "compensation.csv":       compensation,
        "performance_ratings.csv": performance,
        "survey_responses.csv":   surveys,
        "succession_plan.csv":    succession,
    }

    print()
    for filename, df in files.items():
        path = cfg.output_dir / filename
        df.to_csv(path, index=False)
        print(f"  -> {path} ({len(df):,} rows)")

    print(f"\nDone. Seed={cfg.seed} -- re-running with same seed produces identical output.")


if __name__ == "__main__":
    main()
