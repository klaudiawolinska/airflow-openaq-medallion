-- ============================================================================
-- 03_users.sql — service accounts (key-pair auth)
--
-- Last of the ordered bootstrap scripts. Creates the pipeline and CI service
-- users and binds each to its functional role.
--
-- Authentication is KEY-PAIR ONLY (ADR-0018): both users are TYPE = SERVICE,
-- for which Snowflake disables password / MFA sign-in. You MUST paste a real
-- RSA public key into AIRFLOW_USER's RSA_PUBLIC_KEY placeholder below — the
-- script fails on the placeholder by design (Snowflake rejects a malformed key),
-- which stops a keyless pipeline user from silently "working".
--
-- OPENAQ_CI_USER's key is deliberately deferred to M4 (commented out below): the
-- user is created without a key and therefore cannot authenticate at all, which
-- is preferable to provisioning a dormant credential weeks before CI needs it.
-- See include/sql/bootstrap/README.md for key generation.
--
-- Idempotent: CREATE USER IF NOT EXISTS + ALTER USER ... SET converges defaults
-- and the key on re-run; GRANT ROLE is a no-op when already granted.
--
-- Role: USERADMIN — owns the users it creates, so it can ALTER them (incl. the
-- key) without SECURITYADMIN.
-- ============================================================================

USE ROLE USERADMIN;

-- ---------------------------------------------------------------------------
-- AIRFLOW_USER — the pipeline service account used by the snowflake_default
-- Airflow connection. Defaults mirror the connection extra in .env.example.
-- ---------------------------------------------------------------------------
CREATE USER IF NOT EXISTS AIRFLOW_USER
    TYPE              = SERVICE
    DEFAULT_ROLE      = OPENAQ_PIPELINE
    DEFAULT_WAREHOUSE = OPENAQ_WH
    DEFAULT_NAMESPACE = OPENAQ.BRONZE
    COMMENT           = 'Airflow pipeline service account — key-pair (ADR-0018)';

-- >>> EDIT: paste AIRFLOW_USER's public key (one line, no PEM header/footer). <<<
ALTER USER AIRFLOW_USER SET
    DEFAULT_ROLE      = OPENAQ_PIPELINE
    DEFAULT_WAREHOUSE = OPENAQ_WH
    DEFAULT_NAMESPACE = OPENAQ.BRONZE
    RSA_PUBLIC_KEY    = 'PASTE_AIRFLOW_USER_RSA_PUBLIC_KEY';

GRANT ROLE OPENAQ_PIPELINE TO USER AIRFLOW_USER;

-- ---------------------------------------------------------------------------
-- OPENAQ_CI_USER — the CI (GitHub Actions) service account for `dbt build` in
-- the CI schema. Created now so the RBAC shape (role, defaults, isolation from
-- the medallion schemas) is real and testable; the key pair is wired in M4
-- together with the GitHub secret. Until then the user holds no key.
-- ---------------------------------------------------------------------------
CREATE USER IF NOT EXISTS OPENAQ_CI_USER
    TYPE              = SERVICE
    DEFAULT_ROLE      = OPENAQ_CI
    DEFAULT_WAREHOUSE = OPENAQ_WH
    DEFAULT_NAMESPACE = OPENAQ.CI
    COMMENT           = 'CI service account — dbt build in the CI schema (M4)';

ALTER USER OPENAQ_CI_USER SET
    DEFAULT_ROLE      = OPENAQ_CI
    DEFAULT_WAREHOUSE = OPENAQ_WH
    DEFAULT_NAMESPACE = OPENAQ.CI;

-- >>> M4: enable key-pair auth for CI. Generate a second key pair (see README),
-- then uncomment the statement below with the one-line public key (no PEM
-- header/footer) and re-run this script — ALTER USER converges, so re-running
-- the whole bootstrap stays a no-op for every other object. <<<
-- ALTER USER OPENAQ_CI_USER SET
--     RSA_PUBLIC_KEY = 'PASTE_OPENAQ_CI_USER_RSA_PUBLIC_KEY';

GRANT ROLE OPENAQ_CI TO USER OPENAQ_CI_USER;
