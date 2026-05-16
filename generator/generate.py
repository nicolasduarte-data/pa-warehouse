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
    cfg: GeneratorConfig, fake: Faker, rng: np.random.Generator
) -> pd.DataFrame:
    """
    Generate the employee population.

    Each employee gets:
      - employee_id: zero-padded ID (EMP_00001, EMP_00002, ...)
      - first_name, last_name, email: via Faker (plausible-sounding but fictional)
      - hire_date: uniformly sampled from the observation window
      - gender: F / M / NB sampled with light skew (~46% F / 53% M / 1% NB).
        Loop 2 will replace this with conditional sampling on job_level (per
        Story 2.1.0): senior levels under-represent women, producing the
        13% unadjusted / 2% controlled gender pay gap benchmark naturally
        once compensation is layered in (Story 2.1.2).

    Loop 1 simplification: ALL hires fall within the observation window, so
    every employee has a 'hire' event in workforce_events.csv. Loop 2 will
    introduce pre-window hires (employees who joined before observation
    started — their hire is implied, not stored as an event).
    """
    # Zero-padded IDs keep CSV sort order stable and visually scannable.
    # %05d pads to 5 digits — fine through 99,999 employees (Loop 2 needs ~2,500).
    employee_ids = [f"EMP_{i + 1:05d}" for i in range(cfg.n_employees)]

    # Hire date sampling: uniform across the observation window.
    # rng.integers gives day-offsets from window_start; we add them as timedeltas.
    window_length_days = (cfg.window_end - cfg.window_start).days
    day_offsets = rng.integers(low=0, high=window_length_days, size=cfg.n_employees)
    hire_dates = [cfg.window_start + timedelta(days=int(d)) for d in day_offsets]

    # Faker is seeded in main() before this function is called → outputs are deterministic.
    first_names = [fake.first_name() for _ in range(cfg.n_employees)]
    last_names = [fake.last_name() for _ in range(cfg.n_employees)]
    # Construct emails from names rather than calling fake.email() — keeps
    # the email/name relationship consistent (Jane Doe → jane.doe@example.com).
    # At 50 employees we don't worry about collisions; Loop 2 may need a
    # uniqueness suffix for 2,500.
    emails = [
        f"{fn.lower()}.{ln.lower()}@example.com"
        for fn, ln in zip(first_names, last_names)
    ]

    # Gender sampling — Loop 1 uses a light skew (~46% F / 53% M / 1% NB).
    # Loop 2 will switch to conditional-on-job_level sampling per Story 2.1.0
    # to produce the ~13% unadjusted / ~2% adjusted gender pay gap naturally.
    # NB ≈ 1% reflects real-world distribution; we keep it small but visible
    # because the dashboard's compa-ratio heatmap (Story 3.6.1) will need a
    # third category to demonstrate it handles non-binary gender data correctly.
    genders = rng.choice(["F", "M", "NB"], size=cfg.n_employees, p=[0.46, 0.53, 0.01])

    return pd.DataFrame({
        "employee_id": employee_ids,
        "first_name": first_names,
        "last_name": last_names,
        "email": emails,
        "gender": genders,
        "hire_date": hire_dates,
    })


def generate_events(
    employees: pd.DataFrame, cfg: GeneratorConfig, rng: np.random.Generator
) -> pd.DataFrame:
    """
    Generate workforce events per employee.

    Loop 1 emits at most 2 events per employee:
      1. 'hire' on the employee's hire_date — always present in Loop 1
      2. Optional 'term_voluntary' or 'term_involuntary' — sampled
         independently using the constants above. Term date is uniform
         within [hire_date + MIN_TENURE_DAYS_BEFORE_TERM, window_end].

    Validation invariants (enforced by validate() below):
      - All events for an employee are date-sorted ascending
      - No two events for the same employee share a date
      - No event_date < hire_date for that employee
    """
    event_rows: list[dict] = []
    event_counter = 1

    for row in employees.itertuples(index=False):
        emp_id = row.employee_id
        hire_date = row.hire_date

        # Hire event — always emitted in Loop 1 (every employee's hire falls in-window).
        event_rows.append({
            "event_id": f"EVT_{event_counter:07d}",
            "employee_id": emp_id,
            "event_date": hire_date,
            "event_type": "hire",
        })
        event_counter += 1

        # Decide if this employee terminates within the window.
        # Voluntary and involuntary sampled independently — at our rates the joint
        # probability (0.05 × 0.02 = 0.001) is negligible. If both fire we keep
        # voluntary because it's the differentiating signal Loop 3 cares about.
        terms_voluntary = rng.random() < P_TERM_VOLUNTARY_LOOP1
        terms_involuntary = (not terms_voluntary) and (rng.random() < P_TERM_INVOLUNTARY_LOOP1)

        if terms_voluntary or terms_involuntary:
            earliest_term = hire_date + timedelta(days=MIN_TENURE_DAYS_BEFORE_TERM)

            # If the employee was hired too recently for the 30-day minimum
            # tenure to fit before window_end, skip the termination. This is
            # a Loop 1 simplification — Loop 2's lognorm survival handles this naturally.
            if earliest_term < cfg.window_end:
                days_available = (cfg.window_end - earliest_term).days
                term_offset = rng.integers(low=0, high=max(days_available, 1))
                term_date = earliest_term + timedelta(days=int(term_offset))

                event_rows.append({
                    "event_id": f"EVT_{event_counter:07d}",
                    "employee_id": emp_id,
                    "event_date": term_date,
                    "event_type": "term_voluntary" if terms_voluntary else "term_involuntary",
                })
                event_counter += 1

    # Sort by (employee_id, event_date) — this is the timeline invariant. Loop 2's
    # dbt snapshot expects ordered events when reconstructing SCD2 history.
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

    print(f"  [OK] Validation passed: {len(events)} events for {len(employees)} employees")


def main() -> None:
    cfg = parse_args()
    cfg.output_dir.mkdir(parents=True, exist_ok=True)

    # Seed BOTH RNGs — numpy's for distributions, Faker's for strings.
    # Without seeding both, names+emails would drift between runs even
    # with the same numpy seed.
    rng = np.random.default_rng(cfg.seed)
    fake = Faker()
    Faker.seed(cfg.seed)

    print(
        f"Generating {cfg.n_employees} employees over {cfg.n_months} months "
        f"(window: {cfg.window_start} -> {cfg.window_end}, seed={cfg.seed})"
    )

    employees = generate_employees(cfg, fake, rng)
    events = generate_events(employees, cfg, rng)

    validate(employees, events)

    employees_path = cfg.output_dir / "employees.csv"
    events_path = cfg.output_dir / "workforce_events.csv"
    employees.to_csv(employees_path, index=False)
    events.to_csv(events_path, index=False)

    print(f"  -> {employees_path} ({len(employees)} rows)")
    print(f"  -> {events_path} ({len(events)} rows)")


if __name__ == "__main__":
    main()
