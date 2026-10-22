"""
scripts/parity_check.py — execute parity_check.sql on BOTH targets and compare.

Runs the same aggregate query against `marts.v_attrition_features` in BigQuery
and Snowflake, then asserts column-by-column equivalence within tolerance:

  - Integer counts (row_count, employee_count, label_positive_count, gender
    counts, count_critical_role): EXACT match required.
  - Continuous stats (avg/std/min/max/avg_*): within 0.1% relative tolerance.
  - Date columns: EXACT match.

Exits 0 on full pass, 1 on any mismatch (with a per-column report).

Run:
    source ~/.dbt/snowflake.env
    python scripts/parity_check.py

Requires GOOGLE_APPLICATION_CREDENTIALS set for BigQuery auth.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path

from google.cloud import bigquery
from google.oauth2 import service_account
import snowflake.connector

# ─── Config ───────────────────────────────────────────────────────────────────
BQ_KEYFILE = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS",
                            os.path.expanduser("~/.gcp/pa-warehouse-sa.json"))
BQ_PROJECT = "pa-warehouse-prod"

SF_ACCOUNT   = os.environ.get("SNOWFLAKE_ACCOUNT")
SF_USER      = os.environ.get("SNOWFLAKE_USER",      "DBT_USER")
SF_ROLE      = os.environ.get("SNOWFLAKE_ROLE",      "PA_WAREHOUSE_ROLE")
SF_WAREHOUSE = os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH")
SF_DATABASE  = os.environ.get("SNOWFLAKE_DATABASE",  "PA_WAREHOUSE")
SF_KEY_PATH  = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH")
SF_KEY_PASS  = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")

# Tolerances per the parity contract.
EXACT_COLUMNS = {
    "row_count",
    "employee_count",
    "label_positive_count",
    "count_gender_m",
    "count_gender_f",
    "count_gender_nb",
    "count_critical_role",
    "min_tenure_months",
    "max_tenure_months",
    "min_age",
    "max_age",
    "min_successor_count",
    "max_successor_count",
}
DATE_COLUMNS = {"min_snapshot_date", "max_snapshot_date"}
RELATIVE_TOLERANCE = 0.001   # 0.1%


SQL_TEMPLATE = """
SELECT
    'v_attrition_features' AS table_name,
    COUNT(*)               AS row_count,
    COUNT(DISTINCT employee_id) AS employee_count,
    MIN(snapshot_date) AS min_snapshot_date,
    MAX(snapshot_date) AS max_snapshot_date,
    SUM(CASE WHEN voluntary_exit_label THEN 1 ELSE 0 END) AS label_positive_count,
    AVG(CASE WHEN voluntary_exit_label THEN 1.0 ELSE 0.0 END) AS label_positive_rate,
    MIN(tenure_months)    AS min_tenure_months,
    MAX(tenure_months)    AS max_tenure_months,
    AVG(tenure_months)    AS avg_tenure_months,
    STDDEV(tenure_months) AS std_tenure_months,
    MIN(compa_ratio)      AS min_compa_ratio,
    MAX(compa_ratio)      AS max_compa_ratio,
    AVG(compa_ratio)      AS avg_compa_ratio,
    STDDEV(compa_ratio)   AS std_compa_ratio,
    MIN(age_at_window_close)    AS min_age,
    MAX(age_at_window_close)    AS max_age,
    AVG(age_at_window_close)    AS avg_age,
    STDDEV(age_at_window_close) AS std_age,
    SUM(CASE WHEN gender = 'M'  THEN 1 ELSE 0 END) AS count_gender_m,
    SUM(CASE WHEN gender = 'F'  THEN 1 ELSE 0 END) AS count_gender_f,
    SUM(CASE WHEN gender = 'NB' THEN 1 ELSE 0 END) AS count_gender_nb,
    SUM(CASE WHEN is_critical_role THEN 1 ELSE 0 END) AS count_critical_role,
    MIN(successor_count)    AS min_successor_count,
    MAX(successor_count)    AS max_successor_count,
    AVG(successor_count)    AS avg_successor_count
FROM {table}
"""


def fetch_bq() -> dict:
    creds = service_account.Credentials.from_service_account_file(BQ_KEYFILE)
    client = bigquery.Client(credentials=creds, project=BQ_PROJECT)
    sql = SQL_TEMPLATE.format(table=f"`{BQ_PROJECT}.marts.v_attrition_features`")
    rows = list(client.query(sql).result())
    return {k: v for k, v in rows[0].items()}


def fetch_sf() -> dict:
    if not SF_ACCOUNT or not SF_KEY_PATH or not SF_KEY_PASS:
        raise EnvironmentError("Source ~/.dbt/snowflake.env first.")
    conn = snowflake.connector.connect(
        account              = SF_ACCOUNT,
        user                 = SF_USER,
        role                 = SF_ROLE,
        warehouse            = SF_WAREHOUSE,
        database             = SF_DATABASE,
        schema               = "MARTS",
        private_key_file     = SF_KEY_PATH,
        private_key_file_pwd = SF_KEY_PASS,
    )
    cur = conn.cursor()
    sql = SQL_TEMPLATE.format(table=f"{SF_DATABASE}.MARTS.V_ATTRITION_FEATURES")
    cur.execute(sql)
    cols = [d[0].lower() for d in cur.description]
    row = cur.fetchone()
    conn.close()
    return dict(zip(cols, row))


def compare(bq: dict, sf: dict) -> tuple[int, int]:
    """Returns (passed, failed) counts. Prints a per-column verdict."""
    all_cols = sorted(bq.keys() | sf.keys())
    passed = failed = 0
    print(f"{'column':<28} {'bigquery':>20} {'snowflake':>20} {'verdict':>10}")
    print("-" * 82)
    for col in all_cols:
        bv = bq.get(col)
        sv = sf.get(col)
        verdict = "PASS"
        if col == "table_name":
            ok = str(bv) == str(sv)
        elif col in DATE_COLUMNS:
            ok = bv == sv
        elif col in EXACT_COLUMNS:
            ok = bv == sv
        else:
            # Continuous — relative tolerance. Skip if both None or 0.
            if bv is None and sv is None:
                ok = True
            elif bv == 0 and sv == 0:
                ok = True
            else:
                try:
                    bvf = float(bv) if bv is not None else 0.0
                    svf = float(sv) if sv is not None else 0.0
                    denom = max(abs(bvf), 1e-12)
                    ok = abs(bvf - svf) / denom < RELATIVE_TOLERANCE
                except (TypeError, ValueError):
                    ok = False
        if ok:
            passed += 1
        else:
            failed += 1
            verdict = "MISMATCH"
        # Pretty-print values
        bv_s = f"{bv:.6g}" if isinstance(bv, float) else str(bv)
        sv_s = f"{sv:.6g}" if isinstance(sv, float) else str(sv)
        print(f"{col:<28} {bv_s:>20} {sv_s:>20} {verdict:>10}")
    return passed, failed


def main() -> int:
    print(f"Parity check — {dt.datetime.now().isoformat(timespec='seconds')}\n")
    print("Fetching BigQuery ...")
    bq = fetch_bq()
    print(f"  {bq['row_count']} rows")
    print("Fetching Snowflake ...")
    sf = fetch_sf()
    print(f"  {sf['row_count']} rows")
    print()
    passed, failed = compare(bq, sf)
    print("-" * 82)
    print(f"Total: {passed} passed, {failed} mismatched out of {passed + failed} columns")
    if failed == 0:
        print("\n>>> PARITY VALIDATED. <<<")
        return 0
    else:
        print("\n>>> PARITY FAILED. See per-column verdicts above. <<<")
        return 1


if __name__ == "__main__":
    sys.exit(main())
