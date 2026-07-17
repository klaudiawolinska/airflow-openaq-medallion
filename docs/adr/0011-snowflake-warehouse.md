# ADR-0011: Snowflake warehouse (XS, aggressive auto-suspend)

- Status: Accepted
- Date: 2026-07-17

## Context

The project needs a data warehouse for an intermittent, hourly batch ELT workload, where cost efficiency matters more than sustained compute.

## Decision

Use **Snowflake** with an **XS** warehouse and **aggressive auto-suspend** (60 s minimum).

## Alternatives considered

- **DuckDB (free, local)** — weakens the "production warehouse" story the project is built around. Rejected.
- **Larger warehouse / no auto-suspend** — unnecessary cost. This ELT touches new data each run, so a warm warehouse cache gives little; Snowflake's result cache (24 h) is warehouse-independent and still applies. Rejected.

## Consequences

- Standard warehouse patterns (layers, MERGE, VARIANT) at minimal cost.
- A separate CI database/schema is needed so `dbt build` in CI does not touch dev/prod ([ADR-0012](0012-astro-cli-only.md) context).
