# ADR-0001: Build on Apache Airflow 3.2+; Deadline Alerts replace the task-level SLA

- Status: Accepted
- Date: 2026-07-17

## Context

The project needs a target Airflow version. The classic task-level `sla` / `sla_miss_callback` was **removed in Airflow 3.0** and replaced by **Deadline Alerts (AIP-86)** — a DAG-level mechanism introduced in Airflow 3.1. Synchronous deadline callbacks became available in 3.2 (3.1 supports async callbacks only, executed by the Triggerer). Astro Runtime supports Airflow 3.x.

## Decision

Pin the project to **Airflow 3.2+** and use **Deadline Alerts** for run-duration alerting.

## Alternatives considered

- **Airflow 2.x** — has the classic SLA, but it is legacy, the SLA mechanism was long considered unreliable, and 2.x misses Airflow 3 features (Assets, Task SDK, DAG versioning). Rejected.
- **Airflow 3.1** — usable, but deadline callbacks are async-only. 3.2 adds synchronous callbacks, which are simpler for our case. Rejected in favour of 3.2.

## Consequences

- No `sla=`; long-run alerting is expressed at the **DAG level** — there is no native per-task SLA granularity anymore.
- We gain Assets (data-aware scheduling), the Task SDK, and DAG versioning.
- Ties the project to a recent runtime; Cosmos and provider versions must be Airflow-3 compatible.
