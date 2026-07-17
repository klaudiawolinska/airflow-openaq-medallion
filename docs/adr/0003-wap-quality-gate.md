# ADR-0003: Write-Audit-Publish quality gate via dbt tests

- Status: Accepted
- Date: 2026-07-17

## Context

Bad records must not reach consumers. OpenAQ contains gaps, duplicates, and out-of-range values, so records must be audited before they are exposed.

## Decision

Apply **Write-Audit-Publish**: write to silver (not exposed as gold), **audit** with dbt tests, and **publish** to gold only when the audit passes.

## Alternatives considered

- **Transform straight to gold, then test** — bad data is visible to consumers before a failing test catches it. Rejected.
- **External DQ tool (e.g. Great Expectations)** — dbt tests keep the gate inside the transformation layer with a single toolchain. Rejected for this project.

## Consequences

- Consumers never see unaudited data.
- The gate is a real Airflow/Cosmos task that can fail and block publication.
- Row-level handling of failures needs an explicit policy — see [ADR-0004](0004-wap-failure-handling.md).
