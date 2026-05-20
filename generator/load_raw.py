"""
load_raw.py — load all 9 Loop 2 CSVs into BigQuery raw layer.

Usage (from projects/hrds/pa-warehouse/):
    python generator/load_raw.py

Requires GOOGLE_APPLICATION_CREDENTIALS env var pointing to service account JSON.
WRITE_TRUNCATE: re-running replaces table contents — safe, CSVs are the source of truth.

Load order: static dims → employee spine → events → transactional facts.
This mirrors dependency order in dbt (dims before facts that reference them).
"""

import os
from pathlib import Path
import pandas as pd
from google.cloud import bigquery

PROJECT = "pa-warehouse-prod"
DATASET = "raw"
DATA_DIR = Path(__file__).parent.parent / "data" / "raw"


def get_client() -> bigquery.Client:
    key_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not key_path:
        raise EnvironmentError(
            "GOOGLE_APPLICATION_CREDENTIALS is not set. Point it at your BigQuery "
            "service-account JSON key. Examples:\n"
            "  PowerShell:  $env:GOOGLE_APPLICATION_CREDENTIALS = 'C:\\path\\to\\sa-key.json'\n"
            "  Bash:        export GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa-key.json"
        )
    return bigquery.Client(project=PROJECT)


def load_table(
    client: bigquery.Client,
    df: pd.DataFrame,
    table_name: str,
    schema: list[bigquery.SchemaField],
) -> None:
    full_id = f"{PROJECT}.{DATASET}.{table_name}"
    job_config = bigquery.LoadJobConfig(
        schema=schema,
        # WRITE_TRUNCATE replaces table contents on each run.
        # Safe for raw layer — source CSVs are the truth; BigQuery is a copy.
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    job = client.load_table_from_dataframe(df, full_id, job_config=job_config)
    job.result()  # blocks until the load job completes
    table = client.get_table(full_id)
    print(f"  OK  {full_id}  ({table.num_rows} rows)")


def _parse_date(df: pd.DataFrame, col: str) -> pd.DataFrame:
    # Centralised helper: parse_dates → Timestamp → python date object.
    # BigQuery's load_table_from_dataframe requires datetime.date (not Timestamp)
    # when the target column type is DATE.
    df[col] = pd.to_datetime(df[col]).dt.date
    return df


def main() -> None:
    client = get_client()

    # ── 1. departments ───────────────────────────────────────────────────────
    # Tiny static lookup — two columns, no dates, no booleans.
    print("Loading raw.departments ...")
    departments_df = pd.read_csv(DATA_DIR / "departments.csv")
    departments_schema = [
        bigquery.SchemaField("dept_id",   "STRING", mode="REQUIRED"),
        bigquery.SchemaField("dept_name", "STRING"),
    ]
    load_table(client, departments_df, "departments", departments_schema)

    # ── 2. jobs ──────────────────────────────────────────────────────────────
    # is_critical_role arrives as Python bool from the CSV ("True"/"False").
    # Pandas reads "True"/"False" strings as bool automatically, but we cast
    # explicitly (.astype(bool)) to guarantee dtype=bool before BigQuery sees it.
    # band_midpoint is always a whole-dollar salary midpoint — INT64 is exact.
    print("Loading raw.jobs ...")
    jobs_df = pd.read_csv(DATA_DIR / "jobs.csv")
    jobs_df["is_critical_role"] = jobs_df["is_critical_role"].astype(bool)
    jobs_schema = [
        bigquery.SchemaField("job_id",             "STRING",  mode="REQUIRED"),
        bigquery.SchemaField("job_title",          "STRING"),
        bigquery.SchemaField("job_level",          "STRING"),
        bigquery.SchemaField("job_family",         "STRING"),
        bigquery.SchemaField("is_critical_role",   "BOOL"),
        bigquery.SchemaField("skill_scarcity_tier","STRING"),
        bigquery.SchemaField("band_midpoint",      "INT64"),
    ]
    load_table(client, jobs_df, "jobs", jobs_schema)

    # ── 3. locations ─────────────────────────────────────────────────────────
    print("Loading raw.locations ...")
    locations_df = pd.read_csv(DATA_DIR / "locations.csv")
    locations_schema = [
        bigquery.SchemaField("location_id",   "STRING", mode="REQUIRED"),
        bigquery.SchemaField("location_name", "STRING"),
        bigquery.SchemaField("location_type", "STRING"),
        bigquery.SchemaField("region",        "STRING"),
    ]
    load_table(client, locations_df, "locations", locations_schema)

    # ── 4. employees ─────────────────────────────────────────────────────────
    # exit_date is nullable (NaN for active/right-censored employees).
    # pd.to_datetime(NaN) returns NaT; .dt.date converts NaT → None, which
    # BigQuery accepts for a nullable DATE column.
    print("Loading raw.employees ...")
    employees_df = pd.read_csv(DATA_DIR / "employees.csv")
    employees_df = _parse_date(employees_df, "hire_date")
    employees_df["exit_date"] = pd.to_datetime(employees_df["exit_date"], errors="coerce").dt.date
    employees_schema = [
        bigquery.SchemaField("employee_id", "STRING",  mode="REQUIRED"),
        bigquery.SchemaField("first_name",  "STRING"),
        bigquery.SchemaField("last_name",   "STRING"),
        bigquery.SchemaField("email",       "STRING"),
        bigquery.SchemaField("hire_date",   "DATE"),
        bigquery.SchemaField("job_id",      "STRING"),
        bigquery.SchemaField("gender",      "STRING"),
        bigquery.SchemaField("dept_id",     "STRING"),
        bigquery.SchemaField("location_id", "STRING"),
        bigquery.SchemaField("manager_id",  "STRING"),   # nullable — CEO has no manager
        bigquery.SchemaField("perf_tier",   "INT64"),    # ordinal 1–5 performance tier
        bigquery.SchemaField("compa_ratio", "FLOAT64"),
        bigquery.SchemaField("exit_date",   "DATE"),     # nullable — active employees have no exit date
        bigquery.SchemaField("exit_type",   "STRING"),   # nullable — same reason
    ]
    load_table(client, employees_df, "employees", employees_schema)

    # ── 5. workforce_events ──────────────────────────────────────────────────
    # is_regrettable arrives as "True"/"False" strings in CSV — cast to bool
    # so BigQuery receives the correct BOOL type rather than STRING.
    print("Loading raw.workforce_events ...")
    events_df = pd.read_csv(DATA_DIR / "workforce_events.csv")
    events_df = _parse_date(events_df, "event_date")
    events_df["is_regrettable"] = events_df["is_regrettable"].astype(bool)
    events_schema = [
        bigquery.SchemaField("event_id",       "STRING", mode="REQUIRED"),
        bigquery.SchemaField("employee_id",    "STRING", mode="REQUIRED"),
        bigquery.SchemaField("event_date",     "DATE"),
        bigquery.SchemaField("event_type",     "STRING"),
        bigquery.SchemaField("is_regrettable", "BOOL"),  # only meaningful for term_voluntary rows
    ]
    load_table(client, events_df, "workforce_events", events_schema)

    # ── 6. compensation ──────────────────────────────────────────────────────
    # salary: FLOAT64 (not INT64) — future generators may produce fractional values.
    # compa_ratio: ratio of actual salary to band midpoint; always fractional (e.g. 1.052).
    print("Loading raw.compensation ...")
    comp_df = pd.read_csv(DATA_DIR / "compensation.csv")
    comp_df = _parse_date(comp_df, "effective_date")
    comp_schema = [
        bigquery.SchemaField("comp_id",       "STRING",  mode="REQUIRED"),
        bigquery.SchemaField("employee_id",   "STRING",  mode="REQUIRED"),
        bigquery.SchemaField("effective_date","DATE"),
        bigquery.SchemaField("salary",        "FLOAT64"),
        bigquery.SchemaField("currency",      "STRING"),
        bigquery.SchemaField("pay_band_id",   "STRING"),
        bigquery.SchemaField("compa_ratio",   "FLOAT64"),
    ]
    load_table(client, comp_df, "compensation", comp_schema)

    # ── 7. performance_ratings ───────────────────────────────────────────────
    # rating is an ordinal integer (1–5); INT64 preserves that without loss.
    # potential_flag is a categorical string (LOW / MID / HIGH).
    print("Loading raw.performance_ratings ...")
    ratings_df = pd.read_csv(DATA_DIR / "performance_ratings.csv")
    ratings_df = _parse_date(ratings_df, "review_date")
    ratings_schema = [
        bigquery.SchemaField("rating_id",    "STRING", mode="REQUIRED"),
        bigquery.SchemaField("employee_id",  "STRING", mode="REQUIRED"),
        bigquery.SchemaField("review_date",  "DATE"),
        bigquery.SchemaField("review_cycle", "STRING"),
        bigquery.SchemaField("rating",       "INT64"),
        bigquery.SchemaField("potential_flag","STRING"),
    ]
    load_table(client, ratings_df, "performance_ratings", ratings_schema)

    # ── 8. survey_responses ──────────────────────────────────────────────────
    # enps_score: raw NPS response integer (0–10).
    # response_category: derived label (PROMOTER / PASSIVE / DETRACTOR) — kept
    # as STRING here; staging layer will validate accepted values via dbt test.
    print("Loading raw.survey_responses ...")
    survey_df = pd.read_csv(DATA_DIR / "survey_responses.csv")
    survey_df = _parse_date(survey_df, "survey_date")
    survey_schema = [
        bigquery.SchemaField("survey_id",         "STRING", mode="REQUIRED"),
        bigquery.SchemaField("employee_id",       "STRING", mode="REQUIRED"),
        bigquery.SchemaField("survey_date",       "DATE"),
        bigquery.SchemaField("enps_score",        "INT64"),
        bigquery.SchemaField("response_category", "STRING"),
    ]
    load_table(client, survey_df, "survey_responses", survey_schema)

    # ── 9. succession_plan ───────────────────────────────────────────────────
    # successor_readiness_count: how many ready successors exist for this role — INT64.
    # is_critical_role: same bool pattern as jobs — cast explicitly.
    print("Loading raw.succession_plan ...")
    succession_df = pd.read_csv(DATA_DIR / "succession_plan.csv")
    succession_df["is_critical_role"] = succession_df["is_critical_role"].astype(bool)
    succession_schema = [
        bigquery.SchemaField("succession_id",            "STRING", mode="REQUIRED"),
        bigquery.SchemaField("employee_id",              "STRING", mode="REQUIRED"),
        bigquery.SchemaField("successor_readiness_count","INT64"),
        bigquery.SchemaField("is_critical_role",         "BOOL"),
    ]
    load_table(client, succession_df, "succession_plan", succession_schema)

    print("\nDone. All 9 raw tables loaded.")


if __name__ == "__main__":
    main()
