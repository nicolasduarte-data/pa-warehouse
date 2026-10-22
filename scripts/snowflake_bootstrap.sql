-- scripts/snowflake_bootstrap.sql — one-shot Snowflake provisioning for pa-warehouse.
--
-- PURPOSE: After signup, paste this into a Snowflake worksheet (Snowsight UI →
-- Worksheets → New Worksheet) and run all statements. It creates the minimal
-- objects dbt needs:
--   - 1 warehouse (compute)
--   - 1 database (logical container)
--   - 3 schemas mirroring BigQuery layout (RAW / CORE / MARTS)
--   - 1 role bound to all of the above
--   - 1 user (DBT_USER) wearing that role — this is the identity dbt uses
--
-- WHY a separate role + user (not the ACCOUNTADMIN):
-- ACCOUNTADMIN has god-mode; using it from dbt would mean credential leak =
-- account takeover. A scoped role (PA_WAREHOUSE_ROLE) has only what dbt
-- needs — read raw, write core/marts. Least privilege.
--
-- WHY no PASSWORD:
-- dbt-snowflake supports key-pair auth. We create the user
-- here WITHOUT a password and attach the public key in a follow-up statement
-- (also in this file, at the bottom). Password-based auth would leak via
-- profiles.yml if it's ever accidentally committed; the private key is a file
-- path that stays in ~/.ssh and never touches the repo.

-- ── 1. Switch to ACCOUNTADMIN role for setup ──────────────────────────────
-- ACCOUNTADMIN is the only role that can create roles, warehouses, and users.
-- Everything below grants permissions DOWN to PA_WAREHOUSE_ROLE; dbt never
-- touches ACCOUNTADMIN again after this script.
USE ROLE ACCOUNTADMIN;

-- ── 2. Compute warehouse ──────────────────────────────────────────────────
-- XSMALL is the smallest size — 1 credit/hour while running. With
-- AUTO_SUSPEND=60 it suspends after 60s of idle, so a typical dbt build
-- (~3 min) consumes ~0.05 credit. $400 trial credit = ~8000 builds.
CREATE WAREHOUSE IF NOT EXISTS COMPUTE_WH
    WITH WAREHOUSE_SIZE = 'XSMALL'
    AUTO_SUSPEND = 60
    AUTO_RESUME  = TRUE
    INITIALLY_SUSPENDED = TRUE
    COMMENT = 'Compute for pa-warehouse dbt builds. Auto-suspends to preserve trial credit.';

-- ── 3. Database + schemas (mirror BigQuery layout) ────────────────────────
-- Snowflake uses DATABASE.SCHEMA two-tier hierarchy; BigQuery uses just
-- PROJECT.DATASET (flat). We model BigQuery's dataset as Snowflake's
-- schema-within-a-database so dbt sources and refs feel identical in
-- both targets after the dialect port.
CREATE DATABASE IF NOT EXISTS PA_WAREHOUSE
    COMMENT = 'pa-warehouse portfolio project — Snowflake validation port.';

USE DATABASE PA_WAREHOUSE;

CREATE SCHEMA IF NOT EXISTS RAW       COMMENT = 'Mirrors BigQuery raw dataset — source CSVs loaded here.';
CREATE SCHEMA IF NOT EXISTS STAGING   COMMENT = 'Mirrors BigQuery staging dataset — stg_* views.';
CREATE SCHEMA IF NOT EXISTS CORE      COMMENT = 'Mirrors BigQuery core dataset — dims + facts + SCD2 snapshot.';
CREATE SCHEMA IF NOT EXISTS MARTS     COMMENT = 'Mirrors BigQuery marts dataset — dashboard + ML views.';

-- ── 4. Role with scoped permissions ───────────────────────────────────────
CREATE ROLE IF NOT EXISTS PA_WAREHOUSE_ROLE
    COMMENT = 'dbt service identity for pa-warehouse. Only the privileges dbt needs.';

-- Warehouse usage — required to issue any query.
GRANT USAGE ON WAREHOUSE COMPUTE_WH TO ROLE PA_WAREHOUSE_ROLE;

-- Database usage + ALL privileges on its objects so dbt can CREATE OR REPLACE
-- models. ALL on database is broad-but-bounded — only this one database, and
-- the role still can't touch ACCOUNTADMIN-tier objects (roles, users, etc.).
GRANT USAGE ON DATABASE PA_WAREHOUSE TO ROLE PA_WAREHOUSE_ROLE;
GRANT ALL   ON DATABASE PA_WAREHOUSE TO ROLE PA_WAREHOUSE_ROLE;

-- Each schema needs ALL privileges so dbt can create tables / views in it.
-- Future-grant `ALL ON FUTURE TABLES/VIEWS` so anything dbt creates inherits
-- the role's ownership (otherwise subsequent `dbt build` runs fail on access).
GRANT USAGE ON ALL SCHEMAS IN DATABASE PA_WAREHOUSE TO ROLE PA_WAREHOUSE_ROLE;
GRANT ALL   ON ALL SCHEMAS IN DATABASE PA_WAREHOUSE TO ROLE PA_WAREHOUSE_ROLE;
GRANT ALL   ON FUTURE SCHEMAS IN DATABASE PA_WAREHOUSE TO ROLE PA_WAREHOUSE_ROLE;
GRANT ALL   ON ALL TABLES IN DATABASE PA_WAREHOUSE TO ROLE PA_WAREHOUSE_ROLE;
GRANT ALL   ON ALL VIEWS  IN DATABASE PA_WAREHOUSE TO ROLE PA_WAREHOUSE_ROLE;
GRANT ALL   ON FUTURE TABLES IN DATABASE PA_WAREHOUSE TO ROLE PA_WAREHOUSE_ROLE;
GRANT ALL   ON FUTURE VIEWS  IN DATABASE PA_WAREHOUSE TO ROLE PA_WAREHOUSE_ROLE;

-- ── 5. dbt service user (key-pair auth — no password) ─────────────────────
-- DEFAULT_WAREHOUSE / DEFAULT_NAMESPACE so dbt can omit USE statements.
-- DEFAULT_ROLE so the user immediately operates under the scoped role.
-- RSA_PUBLIC_KEY is set in a separate ALTER USER below — paste the contents
-- of ~/.ssh/snowflake_rsa_key.pub (between BEGIN/END markers, single line) there.
CREATE USER IF NOT EXISTS DBT_USER
    DEFAULT_WAREHOUSE = COMPUTE_WH
    DEFAULT_NAMESPACE = PA_WAREHOUSE.RAW
    DEFAULT_ROLE      = PA_WAREHOUSE_ROLE
    COMMENT = 'Service identity used by dbt CLI from local machine. Key-pair auth only.';

GRANT ROLE PA_WAREHOUSE_ROLE TO USER DBT_USER;

-- Also grant PA_WAREHOUSE_ROLE to ACCOUNTADMIN so the human admin can query
-- objects DBT_USER created (otherwise ACCOUNTADMIN gets "Insufficient
-- privileges" on PA_WAREHOUSE.MARTS.* even though they're the account owner).
-- Snowflake's role hierarchy is opt-in — admin roles do not auto-inherit
-- from custom roles unless explicitly granted. Discovered 2026-05-22 during
-- the parity-screenshot capture.
GRANT ROLE PA_WAREHOUSE_ROLE TO ROLE ACCOUNTADMIN;

-- ── 6. Attach the public key ─────────────────────────────────────────────
-- ⚠ EDIT THE LINE BELOW BEFORE RUNNING: replace <<PASTE_PUBLIC_KEY_BODY_HERE>>
-- with the output of:
--   cat ~/.ssh/snowflake_rsa_key.pub | grep -v 'PUBLIC KEY' | tr -d '\n'
-- That command emits the public key as a single line — paste it exactly,
-- inside the single quotes. Then run this ALTER USER statement.
--
-- Example of the FORMAT (do not use this key — illustration only):
--   ALTER USER DBT_USER SET RSA_PUBLIC_KEY = 'MIIBIjANBgkqhki...AB';
--
-- If you skip this step, dbt-snowflake authentication will fail with
-- "JWT token is invalid" — that's the symptom that means "no public key
-- attached or the wrong key attached."

ALTER USER DBT_USER SET RSA_PUBLIC_KEY = '<<PASTE_PUBLIC_KEY_BODY_HERE>>';

-- ── 7. Sanity check — show what got created ───────────────────────────────
SHOW WAREHOUSES LIKE 'COMPUTE_WH';
SHOW DATABASES  LIKE 'PA_WAREHOUSE';
SHOW SCHEMAS    IN DATABASE PA_WAREHOUSE;
SHOW ROLES      LIKE 'PA_WAREHOUSE_ROLE';
SHOW USERS      LIKE 'DBT_USER';
