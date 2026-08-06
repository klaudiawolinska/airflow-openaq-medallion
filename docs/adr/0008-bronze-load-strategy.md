# ADR-0008: Bronze load by overwrite window

- Status: Accepted
- Date: 2026-07-17

## Context

Each hourly ingest run re-fetches the preceding 24-hour interval. Consecutive runs therefore overlap. Retaining a separate copy of every response would grow bronze storage without improving the pipeline's ability to reprocess data.

## Decision

An ingest run writes its raw API response to a transient staging table under its load ID. A stored procedure compares that staging set with bronze for the target window. When the sets differ, one Snowflake transaction replaces the bronze window with the staged rows.

Within one staged measurement set, `(SENSOR_ID, PARAMETER_ID, MEASUREMENT_PERIOD_FROM_UTC)` must be unique. This constraint keeps window comparison and replacement simple; it is specific to measurement overwrite and is not a general bronze-layer deduplication rule.

When a sensor measurements request still returns a server error after the client's retries, ingestion logs the sensor ID and continues. The missing sensor contributes no rows to staging, so any of its existing measurements in the refreshed window are counted as absent and removed by the window replacement.

Bronze retains one current source representation for each ingest window, rather than a history of every retrieval.

## Consequences

- Re-running a window is idempotent.
- Bronze is never observed after its window has been deleted but before the replacement rows are written.
- Analytical deduplication remains a silver-layer responsibility.
