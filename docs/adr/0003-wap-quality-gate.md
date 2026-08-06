# ADR-0003: Write-Audit-Publish quality gate via dbt tests

- Status: Accepted
- Date: 2026-07-17

## Context

The gold layer is the consumer-facing dataset, so publication must be conditional on validation of the source contract and analytical values.

## Decision

The pipeline writes data to silver, runs the data-quality audit with dbt tests, and publishes data to gold only after the audit passes.

## Alternatives considered

- **Use an external data-quality tool** — dbt tests keep validation within the existing transformation toolchain. Rejected for this project.



## Consequences

- Gold contains only data that has passed the audit.
- The audit is an Airflow/Cosmos task; a failure prevents publication to gold.
- The handling of individual invalid rows is defined in [ADR-0004](0004-wap-failure-handling.md).
