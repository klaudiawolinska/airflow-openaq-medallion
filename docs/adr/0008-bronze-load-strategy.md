# ADR-0008: Bronze load by overwrite window

- Status: Accepted
- Date: 2026-07-17

## Context

Each hourly ingest run re-fetches the preceding 24-hour interval. Consecutive runs therefore overlap. Retaining a separate copy of every response would grow bronze storage without improving the pipeline's ability to reprocess data.

## Decision

Before loading an ingest run, delete the bronze records for its target window and insert the current raw API response with load metadata.

Bronze therefore retains one current source representation for each ingest window, rather than a history of every retrieval.

## Consequences

- Re-running a window is idempotent.
- A later run replaces the earlier bronze representation of the same window with the latest response from OpenAQ.
- Deduplication for gold remains a silver-layer responsibility.
