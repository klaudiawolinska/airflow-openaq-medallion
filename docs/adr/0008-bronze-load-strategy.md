# ADR-0008: Bronze load — idempotent overwrite-per-window (not MERGE)

- Status: Accepted
- Date: 2026-07-17

## Context

Re-running a window must be idempotent, but bronze should remain a raw, append-style landing zone rather than an upserted, keyed table. A key-based MERGE at bronze would push silver concerns (deduplication, natural keys) into the raw layer.

## Decision

Load bronze by **overwrite-per-window**: delete the target window's rows, then insert the current API response as raw `VARIANT` plus load metadata (load timestamp, request parameters). **No key-based MERGE at bronze.** Deduplication and merge-on-key live in silver/gold (dbt incremental).

## Alternatives considered

- **MERGE-on-key into bronze** — mixes silver logic into the raw layer and breaks the "raw as received" property. Rejected.
- **Append-only with `load_ts`, dedupe in silver** — viable and gives fuller audit history, but bronze grows unbounded. Rejected for now in favour of bounded storage.

## Consequences

- Idempotent and bounded bronze; a re-run converges to the source's current state for that window.
- All dedup/merge semantics are concentrated in silver/gold.
- Late-arriving data for a window is picked up on re-run.
