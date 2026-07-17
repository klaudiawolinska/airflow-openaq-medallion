# ADR-0012: Local dev via the Astro CLI only

- Status: Accepted
- Date: 2026-07-17

## Context

The project needs one local entry point. The Astro CLI (`astro dev start`) already runs Airflow on Docker under the hood, so shipping a hand-maintained `docker-compose.yml` alongside it duplicates the entry point.

## Decision

Use a **single entry point: the Astro CLI** (`astro dev start`). No separate hand-maintained `docker-compose.yml`.

## Alternatives considered

- **Ship docker-compose.yml as well** — two entry points, double maintenance, redundant with what Astro generates. Rejected.
- **Plain `pip` Airflow install** — more setup friction and less reproducible. Rejected.

## Consequences

- One documented setup path.
- The repo follows the Astro project layout (`Dockerfile`, `requirements.txt`, `packages.txt`, `dags/`, `include/`, `tests/`).
- Depends on contributors having the Astro CLI installed.
