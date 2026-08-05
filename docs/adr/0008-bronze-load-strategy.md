# ADR-0008: Bronze load by overwrite window

- Status: Accepted
- Date: 2026-07-17

## Context

Each hourly ingest run re-fetches the preceding 24-hour interval. Consecutive runs therefore overlap. Retaining a separate copy of every response would grow bronze storage without improving the pipeline's ability to reprocess data.

## Decision

An ingest run writes its raw API response to a transient staging table under its load ID. A stored procedure compares that staging set with bronze for the target window. When the sets differ, one Snowflake transaction replaces the bronze window with the staged rows.

Bronze retains one current source representation for each ingest window, rather than a history of every retrieval.

## Consequences

- Re-running a window is idempotent.
- Bronze is never observed after its window has been deleted but before the replacement rows are written.
- Deduplication for gold remains a silver-layer responsibility.
