# ADR-0016: Basic Snowflake RBAC and provisioning

- Status: Accepted
- Date: 2026-07-17

## Context

The pipeline needs Snowflake objects (database, schemas, warehouse) and an access model. Nothing should run as `ACCOUNTADMIN`, and CI must not touch the pipeline's main tables. A full RBAC-as-code tool (Terraform, Permifrost) is more than this project needs.

## Decision

A **basic, least-privilege RBAC** model, provisioned by versioned, idempotent SQL bootstrap scripts (in `include/sql/`):

- One database (e.g. `OPENAQ`) with schemas `BRONZE` / `SILVER` / `GOLD`.
- A dedicated **XS warehouse** ([ADR-0011](0011-snowflake-warehouse.md)).
- A functional role (e.g. `OPENAQ_PIPELINE`) with **least privilege** — `USAGE` on the database and warehouse, write on the schemas — granted to the pipeline user; **not** `ACCOUNTADMIN`.
- A separate **CI role and schema** so `dbt build` in CI is isolated from the main tables.
- *(Optional)* a read-only role on `GOLD` for consumers / the Snowsight dashboard.
- Credentials stored as an Airflow connection / `.env` secret, never in code.

## Alternatives considered

- **Run everything as `ACCOUNTADMIN`** — no least privilege; a security anti-pattern. Rejected.
- **Terraform / Permifrost (RBAC-as-code)** — more than a basic setup needs; revisit if the model grows. Rejected for now.

## Consequences

- Bootstrap SQL scripts create the objects, roles, and grants (idempotent, run once).
- CI needs its own role, schema, and secret.
- The exact grants and role hierarchy are finalized at the functional/architecture stage.
