# ADR-0004: WAP failure handling — quarantine expected dirt, fail-closed on integrity

- Status: Accepted
- Date: 2026-07-17

## Context

Standard dbt tests are **dataset-level** pass/fail; they do not route individual bad rows. We need a policy for what happens when data fails the audit, given that some dirtiness in OpenAQ is expected and some failures signal a real regression.

## Decision

Two tiers:

- **Expected dirtiness** (nulls, out-of-range values, duplicate rows) → cleaned / **quarantined in silver** (filtered or flagged into a quarantine table). Non-blocking.
- **Integrity / structural violations** (uniqueness, freshness, schema) → **fail-closed at the gate**: block publication to gold and alert.

## Alternatives considered

- **Fail-closed on everything** — a single bad row blocks all good data, and OpenAQ dirt is expected. Rejected.
- **Quarantine everything** — hides genuine integrity regressions behind a quarantine table. Rejected.

## Consequences

- Silver needs models that separate/flag invalid rows (or use dbt `store_failures`).
- Two classes of test with different severities; a quarantine table becomes an observable artifact.
- Feeds the data-quality metrics gold model (a candidate future enhancement).
