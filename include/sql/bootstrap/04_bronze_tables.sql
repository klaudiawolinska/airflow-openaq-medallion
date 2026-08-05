-- Creates the bronze tables used by OpenAQ ingestion, auditing, and reconciliation.

USE ROLE SYSADMIN;

CREATE TABLE IF NOT EXISTS OPENAQ.BRONZE.MEASUREMENTS (
    SENSOR_ID NUMBER(38, 0) NOT NULL,
    PARAMETER_ID NUMBER(38, 0) NOT NULL,
    MEASUREMENT_PERIOD_FROM_UTC TIMESTAMP_TZ NOT NULL,
    RAW_MEASUREMENT VARIANT NOT NULL,
    LOAD_ID VARCHAR NOT NULL,
    LOADED_AT TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

COMMENT ON COLUMN OPENAQ.BRONZE.MEASUREMENTS.MEASUREMENT_PERIOD_FROM_UTC IS
    'Part of the source measurement identity; separates adjacent hourly measurements.';

CREATE TRANSIENT TABLE IF NOT EXISTS OPENAQ.BRONZE.MEASUREMENT_STAGING (
    LOAD_ID VARCHAR NOT NULL,
    SENSOR_ID NUMBER(38, 0) NOT NULL,
    PARAMETER_ID NUMBER(38, 0) NOT NULL,
    MEASUREMENT_PERIOD_FROM_UTC TIMESTAMP_TZ NOT NULL,
    RAW_MEASUREMENT VARIANT NOT NULL,
    STAGED_AT TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

COMMENT ON COLUMN OPENAQ.BRONZE.MEASUREMENT_STAGING.LOAD_ID IS
    'Separates concurrent or retried loads in the shared staging table.';

CREATE OR REPLACE PROCEDURE OPENAQ.BRONZE.REFRESH_STAGED_MEASUREMENTS(
    LOAD_ID VARCHAR,
    REFRESH_FROM TIMESTAMP_TZ,
    REFRESH_TO TIMESTAMP_TZ
)
RETURNS OBJECT
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
    duplicate_staged_measurements EXCEPTION (-20001, 'Staged measurements contain duplicate source identities.');
    duplicate_staged_measurement_count NUMBER;
    new_record_count NUMBER;
    changed_record_count NUMBER;
    absent_record_count NUMBER;
    oldest_new_measurement_at TIMESTAMP_TZ;
BEGIN
    BEGIN TRANSACTION;

    SELECT COUNT(*)
    INTO :duplicate_staged_measurement_count
    FROM (
        SELECT SENSOR_ID, PARAMETER_ID, MEASUREMENT_PERIOD_FROM_UTC
        FROM OPENAQ.BRONZE.MEASUREMENT_STAGING
        WHERE LOAD_ID = :LOAD_ID
          AND MEASUREMENT_PERIOD_FROM_UTC >= :REFRESH_FROM
          AND MEASUREMENT_PERIOD_FROM_UTC < :REFRESH_TO
        GROUP BY SENSOR_ID, PARAMETER_ID, MEASUREMENT_PERIOD_FROM_UTC
        HAVING COUNT(*) > 1
    ) AS duplicate_staged_identities;

    IF (duplicate_staged_measurement_count > 0) THEN
        RAISE duplicate_staged_measurements;
    END IF;

    WITH staged AS (
        SELECT SENSOR_ID, PARAMETER_ID, MEASUREMENT_PERIOD_FROM_UTC, RAW_MEASUREMENT
        FROM OPENAQ.BRONZE.MEASUREMENT_STAGING
        WHERE LOAD_ID = :LOAD_ID
          AND MEASUREMENT_PERIOD_FROM_UTC >= :REFRESH_FROM
          AND MEASUREMENT_PERIOD_FROM_UTC < :REFRESH_TO
    ), bronze AS (
        SELECT SENSOR_ID, PARAMETER_ID, MEASUREMENT_PERIOD_FROM_UTC, RAW_MEASUREMENT
        FROM OPENAQ.BRONZE.MEASUREMENTS
        WHERE MEASUREMENT_PERIOD_FROM_UTC >= :REFRESH_FROM
          AND MEASUREMENT_PERIOD_FROM_UTC < :REFRESH_TO
    )
    SELECT
        (
            SELECT COUNT(*)
            FROM staged AS staged_row
            LEFT JOIN bronze AS bronze_row
                ON bronze_row.SENSOR_ID = staged_row.SENSOR_ID
                AND bronze_row.PARAMETER_ID = staged_row.PARAMETER_ID
                AND bronze_row.MEASUREMENT_PERIOD_FROM_UTC = staged_row.MEASUREMENT_PERIOD_FROM_UTC
            WHERE bronze_row.SENSOR_ID IS NULL
        ),
        (
            SELECT COUNT(*)
            FROM staged AS staged_row
            INNER JOIN bronze AS bronze_row
                ON bronze_row.SENSOR_ID = staged_row.SENSOR_ID
                AND bronze_row.PARAMETER_ID = staged_row.PARAMETER_ID
                AND bronze_row.MEASUREMENT_PERIOD_FROM_UTC = staged_row.MEASUREMENT_PERIOD_FROM_UTC
            WHERE staged_row.RAW_MEASUREMENT IS DISTINCT FROM bronze_row.RAW_MEASUREMENT
        ),
        (
            SELECT COUNT(*)
            FROM bronze AS bronze_row
            LEFT JOIN staged AS staged_row
                ON staged_row.SENSOR_ID = bronze_row.SENSOR_ID
                AND staged_row.PARAMETER_ID = bronze_row.PARAMETER_ID
                AND staged_row.MEASUREMENT_PERIOD_FROM_UTC = bronze_row.MEASUREMENT_PERIOD_FROM_UTC
            WHERE staged_row.SENSOR_ID IS NULL
        ),
        (
            SELECT MIN(staged_row.MEASUREMENT_PERIOD_FROM_UTC)
            FROM staged AS staged_row
            LEFT JOIN bronze AS bronze_row
                ON bronze_row.SENSOR_ID = staged_row.SENSOR_ID
                AND bronze_row.PARAMETER_ID = staged_row.PARAMETER_ID
                AND bronze_row.MEASUREMENT_PERIOD_FROM_UTC = staged_row.MEASUREMENT_PERIOD_FROM_UTC
            WHERE bronze_row.SENSOR_ID IS NULL
        )
    INTO :new_record_count, :changed_record_count, :absent_record_count, :oldest_new_measurement_at;

    IF (new_record_count + changed_record_count + absent_record_count) > 0 THEN
        DELETE FROM OPENAQ.BRONZE.MEASUREMENTS
        WHERE MEASUREMENT_PERIOD_FROM_UTC >= :REFRESH_FROM
          AND MEASUREMENT_PERIOD_FROM_UTC < :REFRESH_TO;

        INSERT INTO OPENAQ.BRONZE.MEASUREMENTS (
            SENSOR_ID,
            PARAMETER_ID,
            MEASUREMENT_PERIOD_FROM_UTC,
            RAW_MEASUREMENT,
            LOAD_ID
        )
        SELECT
            SENSOR_ID,
            PARAMETER_ID,
            MEASUREMENT_PERIOD_FROM_UTC,
            RAW_MEASUREMENT,
            :LOAD_ID
        FROM OPENAQ.BRONZE.MEASUREMENT_STAGING
        WHERE LOAD_ID = :LOAD_ID
          AND MEASUREMENT_PERIOD_FROM_UTC >= :REFRESH_FROM
          AND MEASUREMENT_PERIOD_FROM_UTC < :REFRESH_TO;
    END IF;

    DELETE FROM OPENAQ.BRONZE.MEASUREMENT_STAGING
    WHERE LOAD_ID = :LOAD_ID;

    COMMIT;

    RETURN OBJECT_CONSTRUCT_KEEP_NULL(
        'new_record_count', new_record_count,
        'changed_record_count', changed_record_count,
        'absent_record_count', absent_record_count,
        'oldest_new_measurement_at', oldest_new_measurement_at,
        'bronze_changed', (new_record_count + changed_record_count + absent_record_count) > 0
    );
EXCEPTION
    WHEN OTHER THEN
        ROLLBACK;
        RAISE;
END;
$$;

GRANT USAGE ON PROCEDURE OPENAQ.BRONZE.REFRESH_STAGED_MEASUREMENTS(VARCHAR, TIMESTAMP_TZ, TIMESTAMP_TZ)
    TO ROLE OPENAQ_PIPELINE;

CREATE TABLE IF NOT EXISTS OPENAQ.BRONZE.SENSOR_AUDIT_RESULTS (
    AUDIT_ID VARCHAR NOT NULL,
    AUDITED_AT TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    AUDIT_FROM_UTC TIMESTAMP_TZ NOT NULL,
    AUDIT_TO_UTC TIMESTAMP_TZ NOT NULL,
    PROVIDER_ID NUMBER(38, 0),
    PROVIDER_NAME VARCHAR,
    LOCATION_ID NUMBER(38, 0) NOT NULL,
    LOCATION_NAME VARCHAR,
    SENSOR_ID NUMBER(38, 0) NOT NULL,
    SENSOR_NAME VARCHAR,
    PARAMETER_ID NUMBER(38, 0) NOT NULL,
    PARAMETER_NAME VARCHAR NOT NULL,
    AUDIT_RESULT VARCHAR NOT NULL,
    RECORD_COUNT NUMBER(38, 0) NOT NULL,
    OLDEST_MEASUREMENT_AT TIMESTAMP_TZ,
    NEWEST_MEASUREMENT_AT TIMESTAMP_TZ,
    ERROR_DETAIL VARCHAR
);

COMMENT ON COLUMN OPENAQ.BRONZE.SENSOR_AUDIT_RESULTS.AUDIT_FROM_UTC IS
    'Start of the period checked for this sensor.';
COMMENT ON COLUMN OPENAQ.BRONZE.SENSOR_AUDIT_RESULTS.AUDIT_TO_UTC IS
    'End of the period checked for this sensor.';
COMMENT ON COLUMN OPENAQ.BRONZE.SENSOR_AUDIT_RESULTS.OLDEST_MEASUREMENT_AT IS
    'Earliest returned measurement; shows where source data begins in the checked period.';
COMMENT ON COLUMN OPENAQ.BRONZE.SENSOR_AUDIT_RESULTS.NEWEST_MEASUREMENT_AT IS
    'Latest returned measurement; shows where source data ends in the checked period.';

CREATE TABLE IF NOT EXISTS OPENAQ.BRONZE.LOAD_SUMMARY (
    LOAD_ID VARCHAR NOT NULL,
    LOAD_TYPE VARCHAR NOT NULL,
    REFRESH_FROM_UTC TIMESTAMP_TZ NOT NULL,
    REFRESH_TO_UTC TIMESTAMP_TZ NOT NULL,
    API_RECORD_COUNT NUMBER(38, 0) NOT NULL,
    NEW_RECORD_COUNT NUMBER(38, 0) NOT NULL,
    CHANGED_RECORD_COUNT NUMBER(38, 0) NOT NULL,
    ABSENT_RECORD_COUNT NUMBER(38, 0) NOT NULL,
    OLDEST_NEW_MEASUREMENT_AT TIMESTAMP_TZ,
    BRONZE_CHANGED BOOLEAN NOT NULL,
    COMPLETED_AT TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

COMMENT ON COLUMN OPENAQ.BRONZE.LOAD_SUMMARY.REFRESH_FROM_UTC IS
    'Start of the data range this summary describes.';
COMMENT ON COLUMN OPENAQ.BRONZE.LOAD_SUMMARY.REFRESH_TO_UTC IS
    'End of the data range this summary describes.';
COMMENT ON COLUMN OPENAQ.BRONZE.LOAD_SUMMARY.ABSENT_RECORD_COUNT IS
    'Measurements that had been in bronze but were no longer returned by the API.';
COMMENT ON COLUMN OPENAQ.BRONZE.LOAD_SUMMARY.OLDEST_NEW_MEASUREMENT_AT IS
    'Oldest timestamp among measurements newly seen in bronze; exposes late source backfill.';
