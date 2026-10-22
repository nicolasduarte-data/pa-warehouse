"""
load_raw_snowflake.py — load all 9 generator CSVs into the Snowflake raw schema.

PROJECT: hrds/pa-warehouse
PURPOSE: Sibling of load_raw.py — same CSVs, same intent, different target.
         Loads source CSVs into PA_WAREHOUSE.RAW.* tables on Snowflake so the
         dbt build can run against `--target snowflake`.

WHY a separate file (not a unified loader with --target flag):
The BigQuery and Snowflake APIs are different enough (auth, client object,
write method, schema declaration style) that a unified loader would obscure
both paths with conditionals. Two parallel files = each is small + readable.
The CSVs themselves are the truth source for both.

USAGE:
    source ~/.dbt/snowflake.env        # set key path + passphrase
    python generator/load_raw_snowflake.py

DEPENDENCIES (already in pyproject.toml via dbt-snowflake):
    - snowflake-connector-python[pandas] >= 4.0  (provides write_pandas)

DETERMINISM:
    Re-running drops + recreates each raw.* table (`overwrite=True`).
    CSVs are the source of truth — Snowflake is a copy of whatever the
    generator's current output is.

IDENTIFIER CASE NOTE:
    write_pandas with `quote_identifiers=False` lets Snowflake fold all
    identifiers to UPPERCASE by default. This matches dbt-snowflake's lowercase
    unquoted SQL refs through Snowflake's case-insensitive identifier
    resolution: `select employee_id from raw.employees` resolves to
    `SELECT EMPLOYEE_ID FROM RAW.EMPLOYEES` at compile-time inside Snowflake.
    If we LEFT the default (quote_identifiers=True), the columns would be
    stored as `"employee_id"` (case-sensitive) and dbt SQL would not match.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas

# ─── Config ───────────────────────────────────────────────────────────────────
ACCOUNT   = os.environ.get("SNOWFLAKE_ACCOUNT")
USER      = os.environ.get("SNOWFLAKE_USER",      "DBT_USER")
ROLE      = os.environ.get("SNOWFLAKE_ROLE",      "PA_WAREHOUSE_ROLE")
WAREHOUSE = os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH")
DATABASE  = os.environ.get("SNOWFLAKE_DATABASE",  "PA_WAREHOUSE")
SCHEMA    = os.environ.get("SNOWFLAKE_SCHEMA",    "RAW")

PRIVATE_KEY_PATH = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH")
PRIVATE_KEY_PASS = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")

DATA_DIR = Path(__file__).parent.parent / "data" / "raw"


def get_conn() -> snowflake.connector.SnowflakeConnection:
    """Open a Snowflake connection authenticated via key-pair.

    `private_key_file` + `private_key_file_pwd` were added in
    snowflake-connector-python 3.7+; we require >=4.0 in pyproject.toml so
    this path is always available.
    """
    if not ACCOUNT or not PRIVATE_KEY_PATH or not PRIVATE_KEY_PASS:
        raise EnvironmentError(
            "SNOWFLAKE_PRIVATE_KEY_PATH or SNOWFLAKE_PRIVATE_KEY_PASSPHRASE not set.\n"
            "Source ~/.dbt/snowflake.env before running this script."
        )
    return snowflake.connector.connect(
        account              = ACCOUNT,
        user                 = USER,
        role                 = ROLE,
        warehouse            = WAREHOUSE,
        database             = DATABASE,
        schema               = SCHEMA,
        private_key_file     = PRIVATE_KEY_PATH,
        private_key_file_pwd = PRIVATE_KEY_PASS,
        session_parameters   = {
            "QUERY_TAG": "pa_warehouse_load_raw",
        },
    )


def load_table(conn, df: pd.DataFrame, table_name: str) -> None:
    """Drop + recreate the target table from the DataFrame.

    `quote_identifiers=False` is critical — see the IDENTIFIER CASE NOTE in the
    module docstring. `auto_create_table=True` lets Snowflake infer column
    types from pandas dtypes (object→VARCHAR, int64→NUMBER, float64→FLOAT,
    bool→BOOLEAN, date→DATE). For nullable booleans coming in as 'True'/'False'
    strings from CSV, we cast to bool BEFORE calling this — same pattern as
    load_raw.py.
    """
    success, n_chunks, n_rows, _ = write_pandas(
        conn              = conn,
        df                = df,
        table_name        = table_name.upper(),
        schema            = SCHEMA,
        database          = DATABASE,
        auto_create_table = True,
        overwrite         = True,
        quote_identifiers = False,
    )
    if not success:
        raise RuntimeError(f"write_pandas reported failure for {table_name}")
    print(f"  OK  {DATABASE}.{SCHEMA}.{table_name.upper()}  ({n_rows} rows, {n_chunks} chunk{'s' if n_chunks != 1 else ''})")


def _parse_date(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Mirror load_raw.py — coerce date strings to datetime.date for Snowflake DATE."""
    df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
    return df


def main() -> None:
    print(f"Connecting to Snowflake account={ACCOUNT} as user={USER} ...")
    conn = get_conn()
    print(f"Connected.\nLoading from {DATA_DIR}\n")

    # ── Static dimension lookups ──────────────────────────────────────────
    print("Loading raw.departments ...")
    departments_df = pd.read_csv(DATA_DIR / "departments.csv")
    load_table(conn, departments_df, "departments")

    print("Loading raw.jobs ...")
    jobs_df = pd.read_csv(DATA_DIR / "jobs.csv")
    # is_critical_role: CSV may have it as string "True"/"False" — cast explicitly.
    jobs_df["is_critical_role"] = jobs_df["is_critical_role"].astype(bool)
    load_table(conn, jobs_df, "jobs")

    print("Loading raw.locations ...")
    locations_df = pd.read_csv(DATA_DIR / "locations.csv")
    load_table(conn, locations_df, "locations")

    # ── Employee spine ────────────────────────────────────────────────────
    # The age columns birth_date + age_at_hire flow through here.
    print("Loading raw.employees ...")
    employees_df = pd.read_csv(DATA_DIR / "employees.csv")
    employees_df = _parse_date(employees_df, "hire_date")
    employees_df = _parse_date(employees_df, "birth_date")
    employees_df["exit_date"] = pd.to_datetime(
        employees_df["exit_date"], errors="coerce"
    ).dt.date
    load_table(conn, employees_df, "employees")

    # ── Events ────────────────────────────────────────────────────────────
    print("Loading raw.workforce_events ...")
    events_df = pd.read_csv(DATA_DIR / "workforce_events.csv")
    events_df = _parse_date(events_df, "event_date")
    events_df["is_regrettable"] = events_df["is_regrettable"].astype(bool)
    load_table(conn, events_df, "workforce_events")

    # ── Transactional facts ───────────────────────────────────────────────
    print("Loading raw.compensation ...")
    comp_df = pd.read_csv(DATA_DIR / "compensation.csv")
    comp_df = _parse_date(comp_df, "effective_date")
    load_table(conn, comp_df, "compensation")

    print("Loading raw.performance_ratings ...")
    ratings_df = pd.read_csv(DATA_DIR / "performance_ratings.csv")
    ratings_df = _parse_date(ratings_df, "review_date")
    load_table(conn, ratings_df, "performance_ratings")

    print("Loading raw.survey_responses ...")
    survey_df = pd.read_csv(DATA_DIR / "survey_responses.csv")
    survey_df = _parse_date(survey_df, "survey_date")
    load_table(conn, survey_df, "survey_responses")

    print("Loading raw.succession_plan ...")
    succession_df = pd.read_csv(DATA_DIR / "succession_plan.csv")
    succession_df["is_critical_role"] = succession_df["is_critical_role"].astype(bool)
    load_table(conn, succession_df, "succession_plan")

    conn.close()
    print("\nDone. All 9 raw tables loaded to Snowflake.")


if __name__ == "__main__":
    main()
