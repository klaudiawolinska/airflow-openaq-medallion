-- Provisions the warehouse, database, and schemas. Run first as SYSADMIN.
-- It is safe to re-run: existing objects are updated without being replaced.

USE ROLE SYSADMIN;

-- The hourly workload does not need a running warehouse between jobs.
CREATE WAREHOUSE IF NOT EXISTS OPENAQ_WH
    WAREHOUSE_SIZE      = 'XSMALL'
    AUTO_SUSPEND        = 60
    AUTO_RESUME         = TRUE
    INITIALLY_SUSPENDED = TRUE
    COMMENT             = 'OpenAQ ELT compute — XS, 60s auto-suspend';

-- `INITIALLY_SUSPENDED` applies only when the warehouse is created.
ALTER WAREHOUSE OPENAQ_WH SET
    WAREHOUSE_SIZE = 'XSMALL'
    AUTO_SUSPEND   = 60
    AUTO_RESUME    = TRUE;

-- The CI schema keeps `dbt build` separate from the main tables.
CREATE DATABASE IF NOT EXISTS OPENAQ
    COMMENT = 'OpenAQ air-quality pipeline — bronze/silver/gold medallion';

-- Managed access keeps grants with the schema owner instead of object creators.
CREATE SCHEMA IF NOT EXISTS OPENAQ.BRONZE WITH MANAGED ACCESS
    COMMENT = 'Raw as received (VARIANT); overwrite-per-window (ADR-0008)';
CREATE SCHEMA IF NOT EXISTS OPENAQ.SILVER WITH MANAGED ACCESS
    COMMENT = 'Cleaned, typed, deduplicated';
CREATE SCHEMA IF NOT EXISTS OPENAQ.GOLD WITH MANAGED ACCESS
    COMMENT = 'Business aggregates + station dimension';
CREATE SCHEMA IF NOT EXISTS OPENAQ.CI WITH MANAGED ACCESS
    COMMENT = 'Isolated schema for dbt build in CI';

-- Apply managed access to schemas created by an earlier bootstrap run.
ALTER SCHEMA OPENAQ.BRONZE ENABLE MANAGED ACCESS;
ALTER SCHEMA OPENAQ.SILVER ENABLE MANAGED ACCESS;
ALTER SCHEMA OPENAQ.GOLD   ENABLE MANAGED ACCESS;
ALTER SCHEMA OPENAQ.CI     ENABLE MANAGED ACCESS;

-- The project uses named schemas only, so remove Snowflake's default PUBLIC schema.
DROP SCHEMA IF EXISTS OPENAQ.PUBLIC;
