# ADR-0014: Layered testing strategy

- Status: Accepted
- Date: 2026-07-17

## Context

The project needs a testing approach that is distinct from the WAP data-quality gate. So far "tests" conflate two things: **data quality** (dbt data tests, which are the gate) and **software correctness** (the Python and transformation logic). Data tests validate data; they do not catch regressions in the ingest client, the load logic, the notifier, or the dbt transformations. A layered strategy is needed. The detailed per-component test plan and coverage targets are deferred to the functional-scope stage.

## Decision

Adopt a layered test strategy:

- **Python unit tests** (pytest) for the OpenAQ client (pagination, 429/backoff), the overwrite-per-window load builder, the `BaseNotifier`, and callbacks — external systems (HTTP, SMTP, Snowflake) mocked.
- **dbt unit tests** (dbt ≥ 1.8) for transformation logic on mocked inputs: deduplication, casting/units, SCD2 hashdiff, quarantine filtering. Distinct from data tests.
- **dbt data tests** as the WAP gate: `not_null`, `unique`, `accepted_range`, `freshness`, plus custom tests.
- **DAG-integrity tests**: import errors, no cycles, `default_args`, tags.
- **Integration / e2e**: recorded OpenAQ API responses as fixtures (seeded from the PRD edge-case list), and a dedicated CI Snowflake schema for `dbt build`.

CI runs fast unit + DAG-integrity + lint on every PR; `dbt build` + data tests run against the CI schema.

## Alternatives considered

- **Rely only on the WAP data gate** — validates data, not code; logic regressions slip through. Rejected.
- **Only DAG-integrity tests** — no coverage of business logic. Rejected.
- **Full e2e against live OpenAQ / Snowflake on every PR** — slow, flaky, and rate-limited; use mocks/fixtures plus a scoped CI schema instead. Rejected.

## Consequences

- A clear taxonomy: data-quality vs unit vs integration.
- Requires test fixtures (recorded API payloads) and a CI Snowflake schema/role.
- The PRD edge-case list becomes the initial test backlog.
- The detailed per-component test plan and coverage targets are defined at the functional-scope stage.
