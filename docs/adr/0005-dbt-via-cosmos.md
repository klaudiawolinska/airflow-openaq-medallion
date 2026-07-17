# ADR-0005: Orchestrate dbt with Cosmos (per-model tasks)

- Status: Accepted
- Date: 2026-07-17

## Context

dbt models and tests should be orchestrated with granular retry and a readable graph, not as one opaque step.

## Decision

Run dbt through **astronomer-cosmos**, so each dbt model and test becomes a separate Airflow task.

## Alternatives considered

- **Single `BashOperator` running `dbt build`** — coarse retry (rerun everything on one failure) and an opaque graph. Rejected.
- **dbt Cloud** — an external dependency and cost, outside the "native, self-contained" stance. Rejected.

## Consequences

- Granular retry and selective runs; the dbt DAG is visible inside Airflow.
- More task instances per run.
- The Cosmos version must track Airflow 3 compatibility.
