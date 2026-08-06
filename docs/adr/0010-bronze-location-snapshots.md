# ADR-0010: Raw location snapshots in bronze

- Status: Accepted
- Date: 2026-08-06

## Context

Scheduled ingestion fetches the OpenAQ locations in scope to discover the sensors whose measurements it requests. Each location record also contains the station metadata and its embedded sensors, but measurement ingestion alone does not preserve that source context for downstream transformations.

Location discovery has no measurement window to reconcile. Applying the measurement overwrite strategy would add comparison logic without a corresponding storage or processing benefit.

## Decision

Each successful ingest load appends every raw record returned by its provider-scoped location request to `OPENAQ.BRONZE.LOCATION_SNAPSHOTS`. The embedded sensor array remains inside `RAW_LOCATION`; bronze does not create a separate sensor table.

Location records are staged under the ingest load ID and published in the same Snowflake transaction as the measurement refresh. Retrying the same load ID replaces only that load's location snapshot. A separate ingest run creates a separate snapshot even when the source records are unchanged.

Bronze does not deduplicate location records or validate their business fields and relationships. Silver is responsible for flattening sensors, typing fields, resolving duplicates, and applying data-quality rules.

## Consequences

- Downstream transformations can resolve measurements to sensors and locations without calling OpenAQ again.
- Repeated location records across snapshots are expected source history.
- The location snapshot grows with every successful ingest load.
- The location and measurement load strategies differ because measurements reconcile an overlapping time window while locations preserve each discovery response.
