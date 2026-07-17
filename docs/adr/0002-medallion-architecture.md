# ADR-0002: Medallion architecture (bronze / silver / gold)

- Status: Accepted
- Date: 2026-07-17

## Context

Raw OpenAQ data is dirty (gaps, duplicates, out-of-range values), and reprocessing should not require re-fetching from a rate-limited API.

## Decision

Use a three-layer **medallion** model: **bronze** (raw as received), **silver** (cleaned, typed, deduplicated), **gold** (business aggregates and dimensions).

## Alternatives considered

- **Single transformation stage** (API → business tables) — no raw retention, cannot reprocess without re-fetching, and mixes raw/clean/business concerns. Rejected.

## Consequences

- Clear separation of concerns; reprocessing runs from bronze without hitting the API.
- More storage and more models to maintain.
- Layer boundaries create natural places for the WAP gate ([ADR-0003](0003-wap-quality-gate.md)) and idempotency choices ([ADR-0008](0008-bronze-load-strategy.md)).
