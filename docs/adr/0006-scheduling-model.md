# ADR-0006: Scheduled ingest + Asset-driven transform

- Status: Accepted
- Date: 2026-07-17

## Context

The transform should run when new data lands, but the head of the chain still needs a trigger — data-aware scheduling cannot start a chain from nothing.

## Decision

The **ingest DAG runs on an hourly schedule** (cron/timetable). On success it **emits an Asset**; the **transform DAG is triggered by that Asset** (data-aware).

## Alternatives considered

- **Both DAGs on independent crons** — requires guessing an offset and risks races between ingest and transform. Rejected.
- **A single DAG for ingest + transform** — couples them, losing independent scheduling and retry. Rejected.

## Consequences

- The transform runs exactly when new data is available, not on a guessed cron offset.
- Ingest cadence is explicit; the two DAGs are linked by an Asset.
- If ingest produces no data (0 records → no Asset), the transform does not run — an edge case to handle (stale-looking data).
