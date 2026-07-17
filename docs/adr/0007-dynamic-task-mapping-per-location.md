# ADR-0007: Dynamic task mapping per location

- Status: Accepted
- Date: 2026-07-17

## Context

The OpenAQ v3 API exposes measurements **per sensor / location** — there is no country-wide feed. Poland has 150+ locations (~750 sensors), and the set is discovered at runtime and changes over time.

## Decision

`.expand` the ingest over **locations discovered at runtime**; each mapped task pulls that location's sensors.

## Alternatives considered

- **Per-sensor mapping (~750 tasks/run)** — excessive scheduler overhead for little benefit. Rejected.
- **Per-batch of locations (~10–15 tasks)** — viable fallback if ~150 tasks/run proves heavy; trade-off is coarser fault isolation. Kept as a fallback.
- **A single task looping over locations** — no per-station fault isolation or parallelism. Rejected.

## Consequences

- Per-station fault isolation and partial success (one location failing does not fail the run).
- ~150 mapped tasks per hourly run.
- The mapped-task count tracks the live station set, which ties into station history ([ADR-0009](0009-scd2-station-dimension.md)) and the "station appears/disappears between runs" edge case.
