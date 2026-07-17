# ADR-0009: SCD Type 2 on the station dimension via dbt snapshots

- Status: Accepted
- Date: 2026-07-17

## Context

Station metadata (name, coordinates, sensors, status) changes rarely but does change, and consumers need the "as-was" state at a point in time. Hourly measurements are append-only facts, not a slowly-changing dimension. OpenAQ offers no change events, so changes are detected by snapshotting metadata over time.

## Decision

Apply **SCD Type 2 to the station dimension** using **dbt snapshots**, snapshotted **daily**.

## Alternatives considered

- **Overwrite station attributes on change** — loses history. Rejected.
- **SCD2 on measurements** — facts are not a slowly-changing dimension. Rejected.
- **Snapshot more frequently than daily** — station metadata does not change intra-day; extra cadence only adds cost and noise. Rejected.

## Consequences

- Station state can be reconstructed for any past date.
- Change detection needs a hashdiff / coordinate normalization to avoid spurious changes from float jitter.
- The station dimension is the only slowly-changing dimension in this data; changes are infrequent, so the daily snapshot is cheap.
