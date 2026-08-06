# ADR-0006: Scheduled ingestion and asset-triggered transformation

- Status: Accepted
- Date: 2026-07-17

## Context

Ingestion needs its own schedule because it has no upstream event to trigger it. The transformation must run after ingestion has written data to bronze, without relying on a fixed time offset between two schedules.

## Decision

The ingest DAG runs hourly. Each successful run emits one Airflow Asset representing the location snapshot and measurement window published together in bronze. The transform DAG is scheduled on that Asset.

## Consequences

- The transform DAG runs after an ingest run publishes bronze data, rather than on an independent schedule.
- Reprocessing an identical measurement window still emits the Asset because it records a separate location discovery snapshot.
