# ADR-0008: Bronze load strategies

- Status: Accepted
- Date: 2026-08-06

## Context

Each ingest run retrieves two datasets with different source semantics. Measurements cover a rolling 24-hour window that overlaps consecutive runs. Location discovery returns the station metadata and embedded sensors needed to interpret those measurements, but has no equivalent time window to reconcile.

Neither dataset has produced evidence that requires a duplicate-resolution rule. The pipeline still needs to expose a repeated identity if one occurs without silently choosing a payload.

## Decision

Measurements are staged under the load ID and compared with bronze for the target window. When the sets differ, one Snowflake transaction replaces the bronze window with the staged rows. Each staged set must be unique by `(SENSOR_ID, PARAMETER_ID, MEASUREMENT_PERIOD_FROM_UTC)`; a repeated identity fails the load before bronze changes, and the stored procedure repeats the check as a database-side guard. This deliberate failure makes the occurrence visible without adding resolution logic for a case that has not been observed yet.

When a sensor request still returns a server error after the client's retries, ingestion logs the sensor ID and continues. The missing sensor contributes no rows to staging, so any of its existing measurements in the refreshed window are counted as absent and removed by the window replacement.

Every location record returned by discovery is stored unchanged under the load ID, including its embedded sensor array. Retrying the same load ID replaces that load's snapshot; another load creates another snapshot even when the source records are unchanged. Bronze does not reject a repeated location identity. The dbt transformation tests `(LOAD_ID, LOCATION_ID)` uniqueness and fails if it repeats within one snapshot, leaving the raw records available to determine whether the payloads are identical or conflicting before a resolution rule is introduced.


## Consequences

- Re-running a measurement window is idempotent and its replacement is atomic.
- Location snapshots preserve each discovery response as source history.
- Potential identity repetitions are exposed without adding resolution logic before evidence establishes that it is needed.
