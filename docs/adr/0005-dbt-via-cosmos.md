# ADR-0005: Expose dbt models and tests as Airflow tasks

- Status: Accepted
- Date: 2026-07-17

## Context

The transformation DAG is part of the project's observable orchestration surface. A single `dbt build` task reports the outcome of the full dbt invocation but does not expose the status or dependencies of individual models and tests in Airflow.

## Decision

Use **astronomer-cosmos** to render dbt models and tests as Airflow tasks. The transform DAG therefore exposes the dbt dependency graph and the outcome of each node, rather than running `dbt build` as one opaque task.

## Consequences

- The Airflow UI shows the status and dependencies of individual dbt models and tests.
- A failed dbt node can be retried or investigated without treating the full transformation as a single unit.
- The number of Airflow task instances grows with the number of dbt nodes.
- Cosmos must remain compatible with the Airflow runtime.
