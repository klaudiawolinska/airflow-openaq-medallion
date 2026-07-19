-- ============================================================================
-- 99_teardown.sql — full teardown (DESTRUCTIVE)
--
-- Drops everything the bootstrap created: the database (and ALL its data), the
-- roles, the users, and the warehouse. Its purpose is a clean re-test of
-- idempotency and cleanup — NOT part of a normal run.
--
-- Idempotent: every DROP uses IF EXISTS.
--
-- Roles: USERADMIN owns the roles/users; SYSADMIN owns the database/warehouse.
-- ============================================================================

USE ROLE USERADMIN;
DROP USER IF EXISTS AIRFLOW_USER;
DROP USER IF EXISTS OPENAQ_CI_USER;
DROP ROLE IF EXISTS OPENAQ_PIPELINE;
DROP ROLE IF EXISTS OPENAQ_CI;
DROP ROLE IF EXISTS OPENAQ_READ;

USE ROLE SYSADMIN;
DROP DATABASE  IF EXISTS OPENAQ;
DROP WAREHOUSE IF EXISTS OPENAQ_WH;
