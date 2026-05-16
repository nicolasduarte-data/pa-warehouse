"""
load_raw.py — load Loop 1 CSVs into BigQuery raw layer.

Usage (from projects/hrds/pa-warehouse/):
    python generator/load_raw.py

Requires GOOGLE_APPLICATION_CREDENTIALS env var pointing to service account JSON.
WRITE_TRUNCATE: re-running this script replaces existing table contents — safe to run repeatedly.
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
            "GOOGLE_APPLICATION_CREDENTIALS is not set. "
            "Run: $env:GOOGLE_APPLICATION_CREDENTIALS = 'C:\\Users\\PREDATOR\\.gcp\\pa-warehouse-sa.json'"
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


def main() -> None:
    client = get_client()

    # ── employees ────────────────────────────────────────────────────────────
    # parse_dates converts the hire_date column from string to pandas Timestamp.
    # .dt.date then converts to Python datetime.date — the type BigQuery expects
    # when writing a DATE column via load_table_from_dataframe.
    print("Loading raw.employees ...")
    employees_df = pd.read_csv(DATA_DIR / "employees.csv", parse_dates=["hire_date"])
    employees_df["hire_date"] = employees_df["hire_date"].dt.date

    employees_schema = [
        bigquery.SchemaField("employee_id", "STRING",  mode="REQUIRED"),
        bigquery.SchemaField("first_name",  "STRING"),
        bigquery.SchemaField("last_name",   "STRING"),
        bigquery.SchemaField("email",       "STRING"),
        bigquery.SchemaField("gender",      "STRING"),
        bigquery.SchemaField("hire_date",   "DATE"),
    ]
    load_table(client, employees_df, "employees", employees_schema)

    # ── workforce_events ─────────────────────────────────────────────────────
    print("Loading raw.workforce_events ...")
    events_df = pd.read_csv(DATA_DIR / "workforce_events.csv", parse_dates=["event_date"])
    events_df["event_date"] = events_df["event_date"].dt.date

    events_schema = [
        bigquery.SchemaField("event_id",    "STRING", mode="REQUIRED"),
        bigquery.SchemaField("employee_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("event_date",  "DATE"),
        bigquery.SchemaField("event_type",  "STRING"),
    ]
    load_table(client, events_df, "workforce_events", events_schema)

    print("\nDone. Raw layer loaded.")


if __name__ == "__main__":
    main()
