-- Creates the pipeline and CI service users. Run last as USERADMIN.
-- Paste both public keys into the placeholders before running this script.

USE ROLE USERADMIN;

-- AIRFLOW_USER is the service account used by the default Airflow connection.
CREATE USER IF NOT EXISTS AIRFLOW_USER
    TYPE              = SERVICE
    DEFAULT_ROLE      = OPENAQ_PIPELINE
    DEFAULT_WAREHOUSE = OPENAQ_WH
    DEFAULT_NAMESPACE = OPENAQ.BRONZE
    COMMENT           = 'Airflow pipeline service account — key-pair';

-- >>> EDIT: paste AIRFLOW_USER's public key (one line, no PEM header/footer). <<<
ALTER USER AIRFLOW_USER SET
    DEFAULT_ROLE      = OPENAQ_PIPELINE
    DEFAULT_WAREHOUSE = OPENAQ_WH
    DEFAULT_NAMESPACE = OPENAQ.BRONZE
    RSA_PUBLIC_KEY    = 'PASTE_AIRFLOW_USER_RSA_PUBLIC_KEY';

GRANT ROLE OPENAQ_PIPELINE TO USER AIRFLOW_USER;

-- OPENAQ_CI_USER is the service account for `dbt build` in the CI schema.
CREATE USER IF NOT EXISTS OPENAQ_CI_USER
    TYPE              = SERVICE
    DEFAULT_ROLE      = OPENAQ_CI
    DEFAULT_WAREHOUSE = OPENAQ_WH
    DEFAULT_NAMESPACE = OPENAQ.CI
    COMMENT           = 'CI service account — dbt build in the CI schema';

ALTER USER OPENAQ_CI_USER SET
    DEFAULT_ROLE      = OPENAQ_CI
    DEFAULT_WAREHOUSE = OPENAQ_WH
    DEFAULT_NAMESPACE = OPENAQ.CI;

-- >>> EDIT: paste OPENAQ_CI_USER's public key (one line, no PEM header/footer). <<<
ALTER USER OPENAQ_CI_USER SET
    RSA_PUBLIC_KEY = 'PASTE_OPENAQ_CI_USER_RSA_PUBLIC_KEY';

GRANT ROLE OPENAQ_CI TO USER OPENAQ_CI_USER;
