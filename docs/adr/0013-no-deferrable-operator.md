# ADR-0013: Deferrable operator out of scope

- Status: Accepted
- Date: 2026-07-17

## Context

An early roadmap item suggested a deferrable operator for "long polling" of the API. A deferrable operator frees a worker slot during a long asynchronous wait by handing a Trigger to the Triggerer. The OpenAQ ingest, however, is a quick REST call with no genuine long-running wait.

## Decision

**Do not** use a deferrable operator. There is no real long async wait in this pipeline to justify it.

## Alternatives considered

- **Add a deferrable operator anyway, to showcase the pattern** — complexity without benefit; it would be contrived. Rejected.
- **Apply it to a genuinely long wait** (e.g. an async Snowflake query) — no such step exists in the current design. Not applicable.

## Consequences

- Simpler ingest.
- Deferrable execution (the Triggerer) is not used here.
- Can be revisited if a real long-running async step appears (e.g. async warehouse jobs, a rate-limited long paginated pull).
