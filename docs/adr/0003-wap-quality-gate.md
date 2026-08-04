# ADR-0003: Write-Audit-Publish quality gate via dbt tests

- Status: Accepted
- Date: 2026-07-17

## Context

The gold layer is the consumer-facing dataset. OpenAQ data can contain gaps, duplicate observations, and measurements outside the accepted range, so publication to gold must be conditional on a data-quality audit.

## Decision

The pipeline writes data to silver, runs the data-quality audit with dbt tests, and publishes data to gold only after the audit passes.

## Alternatives considered

- **Use an external data-quality tool** — dbt tests keep validation within the existing transformation toolchain. Rejected for this project.



## Consequences

- Gold contains only data that has passed the audit.
- The audit is an Airflow/Cosmos task; a failure prevents publication to gold.
- The handling of individual invalid rows is defined in [ADR-0004](0004-wap-failure-handling.md).
