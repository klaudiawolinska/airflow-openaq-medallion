# ADR-0006: Scheduled ingestion and asset-triggered transformation

- Status: Accepted
- Date: 2026-07-17

## Context

Ingestion needs its own schedule because it has no upstream event to trigger it. The transformation must run after ingestion has written data to bronze, without relying on a fixed time offset between two schedules.

## Decision

The ingest DAG runs hourly. A run that writes data to bronze emits an Airflow Asset. The transform DAG is scheduled on that Asset.

## Consequences

- The transform DAG runs after an ingest run has written data to bronze, rather than on an independent schedule.
- An ingest run that writes no records does not emit the Asset, so it does not trigger a transform run.
