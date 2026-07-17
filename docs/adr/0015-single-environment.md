# ADR-0015: Single environment; no dev/prod separation or CD

- Status: Accepted
- Date: 2026-07-17

## Context

A full dev → prod promotion flow with continuous deployment would add infrastructure — multiple Snowflake databases, environment-specific configuration, and a deploy pipeline — without changing the orchestration and data patterns the project is built around.

## Decision

Run a **single environment**. No dev/prod separation and no CD. The pipeline runs via the Astro CLI ([ADR-0012](0012-astro-cli-only.md)) against one Snowflake database. CI uses an isolated schema purely to keep test runs from touching the main tables.

## Alternatives considered

- **Full dev/prod environments + CD** (e.g. deploying to Astro Cloud) — infrastructure overhead, out of scope, and it does not change the patterns being built. Rejected.

## Consequences

- One Snowflake database and one dbt target; "deployment" means running locally.
- The pipeline is production-shaped but is not hosted as a running production service.
- CI still uses an isolated schema/role so its runs stay separate from the main tables ([ADR-0016](0016-snowflake-rbac.md)).
