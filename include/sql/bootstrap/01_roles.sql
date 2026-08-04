-- Creates functional roles. Run after 00_warehouse_database.sql as USERADMIN.
-- Grants are defined in 02_grants.sql and service users in 03_users.sql.

USE ROLE USERADMIN;

-- The pipeline receives its permissions through this role.
CREATE ROLE IF NOT EXISTS OPENAQ_PIPELINE
    COMMENT = 'Least-privilege functional role for the Airflow pipeline';

-- CI is restricted to its own schema.
CREATE ROLE IF NOT EXISTS OPENAQ_CI
    COMMENT = 'Isolated CI role — CI schema only, no access to bronze/silver/gold';

-- Optional read-only role for consumers and the Snowsight dashboard on GOLD.
CREATE ROLE IF NOT EXISTS OPENAQ_READ
    COMMENT = 'Read-only on GOLD for consumers / Snowsight';

-- SYSADMIN can manage objects owned by these roles (standard Snowflake role hierarchy).
GRANT ROLE OPENAQ_PIPELINE TO ROLE SYSADMIN;
GRANT ROLE OPENAQ_CI       TO ROLE SYSADMIN;
GRANT ROLE OPENAQ_READ     TO ROLE SYSADMIN;
