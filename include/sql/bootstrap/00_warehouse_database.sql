-- ============================================================================
-- 00_warehouse_database.sql — account objects: warehouse, database, schemas
--
-- First of the ordered bootstrap scripts (00 -> 03). Run once by an admin; see
-- include/sql/bootstrap/README.md for the full run order and prerequisites.
--
-- Idempotent: safe to re-run. Uses CREATE ... IF NOT EXISTS plus ALTER ... SET
-- so a second run converges settings without dropping any object. No
-- CREATE OR REPLACE on stateful objects — that would destroy data on re-run.
--
-- Role: SYSADMIN. Creating a warehouse and a database needs neither ACCOUNTADMIN
-- nor account-level privileges beyond what SYSADMIN holds by default.
-- ============================================================================

USE ROLE SYSADMIN;

-- Compute: a single XS warehouse with aggressive auto-suspend (ADR-0011). The
-- workload is intermittent hourly ELT, so cost efficiency beats a warm cache.
CREATE WAREHOUSE IF NOT EXISTS OPENAQ_WH
    WAREHOUSE_SIZE      = 'XSMALL'
    AUTO_SUSPEND        = 60
    AUTO_RESUME         = TRUE
    INITIALLY_SUSPENDED = TRUE
    COMMENT             = 'OpenAQ ELT compute — XS, 60s auto-suspend (ADR-0011)';

-- Converge settings if the warehouse already existed with different values
-- (AUTO_SUSPEND / size drift). INITIALLY_SUSPENDED is a create-time-only option,
-- so it is intentionally not repeated here.
ALTER WAREHOUSE OPENAQ_WH SET
    WAREHOUSE_SIZE = 'XSMALL'
    AUTO_SUSPEND   = 60
    AUTO_RESUME    = TRUE;

-- One database with the three medallion schemas (ADR-0002) plus an isolated CI
-- schema so `dbt build` in CI never touches the main tables (ADR-0016).
CREATE DATABASE IF NOT EXISTS OPENAQ
    COMMENT = 'OpenAQ air-quality pipeline — bronze/silver/gold medallion';

CREATE SCHEMA IF NOT EXISTS OPENAQ.BRONZE
    COMMENT = 'Raw as received (VARIANT); overwrite-per-window (ADR-0008)';
CREATE SCHEMA IF NOT EXISTS OPENAQ.SILVER
    COMMENT = 'Cleaned, typed, deduplicated';
CREATE SCHEMA IF NOT EXISTS OPENAQ.GOLD
    COMMENT = 'Business aggregates + station dimension (SCD2)';
CREATE SCHEMA IF NOT EXISTS OPENAQ.CI
    COMMENT = 'Isolated schema for dbt build in CI (ADR-0016)';

-- Snowflake auto-creates a PUBLIC schema in every new database; this project
-- addresses schemas explicitly and never uses PUBLIC, so drop it to keep stray
-- objects from landing in an ungoverned namespace. IF EXISTS keeps this a no-op
-- on re-run.
DROP SCHEMA IF EXISTS OPENAQ.PUBLIC;
