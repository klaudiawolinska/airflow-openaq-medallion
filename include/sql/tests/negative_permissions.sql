-- ============================================================================
-- negative_permissions.sql — least-privilege verification (run manually)
--
-- Confirms OPENAQ_PIPELINE cannot act outside its scope. This is NOT a CI test:
-- it needs a live account, and every statement below is EXPECTED TO FAIL — a
-- success is a finding. Run statement by statement (Snowsight / snowsql) and
-- check each raises the noted error.
--
-- HOW TO RUN — two modes, different coverage:
--
--   A) As AIRFLOW_USER via key-pair (snowsql -a <acct> -u AIRFLOW_USER
--      --private-key-path include/.keys/airflow_user_rsa.p8). This is the FULL
--      check: the login user holds only OPENAQ_PIPELINE, so the role-escalation
--      block (section 3) is meaningful.
--
--   B) From an admin session with `USE ROLE OPENAQ_PIPELINE`. This validates the
--      privilege-boundary checks (sections 1-2) — those depend on the ACTIVE
--      role, not the login user. It does NOT validate section 3: your admin
--      login still holds ACCOUNTADMIN/SYSADMIN, so `USE ROLE ACCOUNTADMIN` would
--      falsely succeed. Skip section 3 in mode B.
-- ============================================================================

USE ROLE OPENAQ_PIPELINE;

-- --- Section 1: cannot create account-level objects -------------------------
CREATE DATABASE  should_fail;              -- EXPECT: insufficient privileges
CREATE WAREHOUSE should_fail;              -- EXPECT: insufficient privileges
CREATE ROLE      should_fail;              -- EXPECT: insufficient privileges
CREATE SCHEMA    OPENAQ.should_fail;       -- EXPECT: insufficient privileges
                                           -- (no CREATE SCHEMA on the database)

-- --- Section 2: cannot touch the isolated CI schema (owned scope of CI) ------
USE SCHEMA OPENAQ.CI;                       -- EXPECT: does not exist / not authorized
CREATE TABLE OPENAQ.CI.should_fail (x INT); -- EXPECT: insufficient privileges

-- --- Section 3: cannot escalate to an admin role (mode A only) ---------------
-- Only meaningful when authenticated AS AIRFLOW_USER; see header, mode B.
USE ROLE ACCOUNTADMIN;                      -- EXPECT: role not granted to user
USE ROLE SYSADMIN;                          -- EXPECT: role not granted to user
USE ROLE SECURITYADMIN;                     -- EXPECT: role not granted to user
