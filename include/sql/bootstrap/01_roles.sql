-- ============================================================================
-- 01_roles.sql — functional roles (least privilege)
--
-- Second of the ordered bootstrap scripts. Creates the functional roles; grants
-- are applied in 02_grants.sql, users in 03_users.sql.
--
-- Idempotent: CREATE ROLE IF NOT EXISTS; re-granting a role is a no-op.
--
-- Role: USERADMIN — the least-privileged system role that owns role management.
-- ============================================================================

USE ROLE USERADMIN;

-- The Airflow pipeline runs as this role: usage on the warehouse/database and
-- write on the medallion schemas, and nothing else (see 02_grants.sql).
CREATE ROLE IF NOT EXISTS OPENAQ_PIPELINE
    COMMENT = 'Least-privilege functional role for the Airflow pipeline';

-- CI (dbt build in GitHub Actions, M4) runs as this role, scoped to the CI
-- schema only so its runs never touch the main tables (ADR-0016).
CREATE ROLE IF NOT EXISTS OPENAQ_CI
    COMMENT = 'Isolated CI role — CI schema only, no access to bronze/silver/gold';

-- Optional read-only role for consumers / the Snowsight dashboard on GOLD (M11).
CREATE ROLE IF NOT EXISTS OPENAQ_READ
    COMMENT = 'Read-only on GOLD for consumers / Snowsight (optional)';

-- Wire the functional roles under SYSADMIN so SYSADMIN (not ACCOUNTADMIN) can
-- manage the objects they own — the standard Snowflake role hierarchy.
GRANT ROLE OPENAQ_PIPELINE TO ROLE SYSADMIN;
GRANT ROLE OPENAQ_CI       TO ROLE SYSADMIN;
GRANT ROLE OPENAQ_READ     TO ROLE SYSADMIN;
