-- ============================================================================
-- 02_grants.sql — least-privilege grants (existing + future objects)
--
-- Third of the ordered bootstrap scripts. Grants privileges to the roles from
-- 01_roles.sql. FUTURE grants mean objects created later (bronze tables in M3,
-- dbt models in M4/M5) are covered without re-running this script.
--
-- Idempotent: GRANT is inherently a no-op when the privilege already exists.
--
-- Role: SECURITYADMIN — holds MANAGE GRANTS, so it can grant privileges on
-- objects owned by SYSADMIN and set FUTURE grants, without ACCOUNTADMIN.
-- ============================================================================

USE ROLE SECURITYADMIN;

-- ---------------------------------------------------------------------------
-- OPENAQ_PIPELINE — usage on compute/database, read+write on the medallion
-- schemas (existing and future objects). No account-level or cross-schema
-- access; the negative-permission checks assert these boundaries.
-- (Bronze's load path may need CREATE STAGE / FILE FORMAT — added in M3 when the
-- load mechanism is decided; kept out here to stay minimal.)
-- ---------------------------------------------------------------------------
GRANT USAGE ON WAREHOUSE OPENAQ_WH TO ROLE OPENAQ_PIPELINE;
GRANT USAGE ON DATABASE  OPENAQ    TO ROLE OPENAQ_PIPELINE;

GRANT USAGE ON SCHEMA OPENAQ.BRONZE TO ROLE OPENAQ_PIPELINE;
GRANT USAGE ON SCHEMA OPENAQ.SILVER TO ROLE OPENAQ_PIPELINE;
GRANT USAGE ON SCHEMA OPENAQ.GOLD   TO ROLE OPENAQ_PIPELINE;

GRANT CREATE TABLE, CREATE VIEW ON SCHEMA OPENAQ.BRONZE TO ROLE OPENAQ_PIPELINE;
GRANT CREATE TABLE, CREATE VIEW ON SCHEMA OPENAQ.SILVER TO ROLE OPENAQ_PIPELINE;
GRANT CREATE TABLE, CREATE VIEW ON SCHEMA OPENAQ.GOLD   TO ROLE OPENAQ_PIPELINE;

-- DML on current + future tables in each medallion schema.
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE
    ON ALL    TABLES IN SCHEMA OPENAQ.BRONZE TO ROLE OPENAQ_PIPELINE;
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE
    ON FUTURE TABLES IN SCHEMA OPENAQ.BRONZE TO ROLE OPENAQ_PIPELINE;
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE
    ON ALL    TABLES IN SCHEMA OPENAQ.SILVER TO ROLE OPENAQ_PIPELINE;
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE
    ON FUTURE TABLES IN SCHEMA OPENAQ.SILVER TO ROLE OPENAQ_PIPELINE;
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE
    ON ALL    TABLES IN SCHEMA OPENAQ.GOLD   TO ROLE OPENAQ_PIPELINE;
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE
    ON FUTURE TABLES IN SCHEMA OPENAQ.GOLD   TO ROLE OPENAQ_PIPELINE;

-- SELECT on current + future views (dbt materializes some models as views).
GRANT SELECT ON ALL    VIEWS IN SCHEMA OPENAQ.BRONZE TO ROLE OPENAQ_PIPELINE;
GRANT SELECT ON FUTURE VIEWS IN SCHEMA OPENAQ.BRONZE TO ROLE OPENAQ_PIPELINE;
GRANT SELECT ON ALL    VIEWS IN SCHEMA OPENAQ.SILVER TO ROLE OPENAQ_PIPELINE;
GRANT SELECT ON FUTURE VIEWS IN SCHEMA OPENAQ.SILVER TO ROLE OPENAQ_PIPELINE;
GRANT SELECT ON ALL    VIEWS IN SCHEMA OPENAQ.GOLD   TO ROLE OPENAQ_PIPELINE;
GRANT SELECT ON FUTURE VIEWS IN SCHEMA OPENAQ.GOLD   TO ROLE OPENAQ_PIPELINE;

-- ---------------------------------------------------------------------------
-- OPENAQ_CI — usage on compute/database and full rights inside the CI schema
-- ONLY. Deliberately no grant on BRONZE/SILVER/GOLD: that is what isolates CI
-- runs from the main tables (ADR-0016). SYSADMIN keeps ownership of the schema;
-- objects dbt creates in CI are owned by OPENAQ_CI.
-- ---------------------------------------------------------------------------
GRANT USAGE ON WAREHOUSE OPENAQ_WH TO ROLE OPENAQ_CI;
GRANT USAGE ON DATABASE  OPENAQ    TO ROLE OPENAQ_CI;

GRANT ALL PRIVILEGES ON SCHEMA OPENAQ.CI TO ROLE OPENAQ_CI;
GRANT ALL PRIVILEGES ON ALL    TABLES IN SCHEMA OPENAQ.CI TO ROLE OPENAQ_CI;
GRANT ALL PRIVILEGES ON FUTURE TABLES IN SCHEMA OPENAQ.CI TO ROLE OPENAQ_CI;
GRANT ALL PRIVILEGES ON ALL    VIEWS  IN SCHEMA OPENAQ.CI TO ROLE OPENAQ_CI;
GRANT ALL PRIVILEGES ON FUTURE VIEWS  IN SCHEMA OPENAQ.CI TO ROLE OPENAQ_CI;

-- ---------------------------------------------------------------------------
-- OPENAQ_READ — read-only on GOLD (consumers / Snowsight, M11). Optional.
-- ---------------------------------------------------------------------------
GRANT USAGE ON WAREHOUSE OPENAQ_WH TO ROLE OPENAQ_READ;
GRANT USAGE ON DATABASE  OPENAQ    TO ROLE OPENAQ_READ;
GRANT USAGE ON SCHEMA    OPENAQ.GOLD TO ROLE OPENAQ_READ;

GRANT SELECT ON ALL    TABLES IN SCHEMA OPENAQ.GOLD TO ROLE OPENAQ_READ;
GRANT SELECT ON FUTURE TABLES IN SCHEMA OPENAQ.GOLD TO ROLE OPENAQ_READ;
GRANT SELECT ON ALL    VIEWS  IN SCHEMA OPENAQ.GOLD TO ROLE OPENAQ_READ;
GRANT SELECT ON FUTURE VIEWS  IN SCHEMA OPENAQ.GOLD TO ROLE OPENAQ_READ;
