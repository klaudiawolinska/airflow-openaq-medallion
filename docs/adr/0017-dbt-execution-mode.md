# ADR-0017: dbt execution mode — LOCAL with a dedicated virtualenv

- Status: Accepted
- Date: 2026-07-17

## Context

[ADR-0005](0005-dbt-via-cosmos.md) runs dbt through Cosmos (per-model tasks) but leaves the *execution mode* open. Cosmos can run dbt in the Airflow worker's own Python environment (`LOCAL`, `WATCHER`) or isolate it (`VIRTUALENV`, `DOCKER`, `KUBERNETES`). Two forces decide it:

- **dbt and Airflow should not share one dependency tree.** They genuinely overlap — `jinja2`, `pydantic`, `protobuf` and `click` are dependencies of both. Verified in the `3.3-2-python-3.13` image vs an isolated dbt-1.12 venv, the first three resolve to *identical* versions today (jinja2 3.1.6, pydantic 2.13.4, protobuf 6.33.6) and `click` already differs by a patch (8.4.1 vs 8.4.2). So there is **no conflict today**; the risk is the coupling itself — two independently-released tools pinned over a shared surface, where a future bump on either side can force a reconciliation or break the other. Isolation removes that coupling and contains blast radius.
- **Python version is not what forces isolation.** The image pins Python 3.13 (`3.3-2-python-3.13`), which sits inside `dbt-snowflake` 1.12's declared support (classifiers 3.10–3.13, `requires_python >=3.10`), and `snowflake-connector-python` 4.7.1 resolves there too — verified by installing the pinned dbt into a venv in the runtime image. So the isolation requirement is about the **dependency tree, not the interpreter**, and no second Python interpreter is needed.

Per Cosmos' "Choose an execution mode" guide, worker-based modes trade isolation for speed; `WATCHER` and `LOCAL` are rated `None/Lightweight` isolation, `VIRTUALENV` `Lightweight`, containers higher.

## Decision

Run Cosmos in **`ExecutionMode.LOCAL` with `ExecutionConfig.dbt_executable_path`** pointing at a **dedicated dbt virtualenv**, built on the runtime's Python 3.13, with `dbt-core` and `dbt-snowflake` pinned in `dbt-requirements.txt` (deliberately kept out of the image's `requirements.txt`). dbt runs as a subprocess against that venv's isolated site-packages.

## Alternatives considered

- **WATCHER** — fastest, but "behaves like `LOCAL`" and runs dbt in the worker's environment (`None/Lightweight` isolation), so it contradicts the isolation requirement. Its speed gains target large multi-model projects; here Snowflake, not task overhead, is the bottleneck. Getting watcher *and* isolation requires `WATCHER_KUBERNETES` → a K8s cluster, out of scope for single-node Astro (ADR-0012, ADR-0015). Rejected.
- **VIRTUALENV (Cosmos-managed)** — same `Lightweight` isolation, but Astronomer recommends `LOCAL` + `dbt_executable_path` "in most cases" as it keeps the Airflow deployment simpler. Rejected in favour of the simpler equivalent.
- **DOCKER / KUBERNETES** — higher isolation and a separate interpreter, but slower (container provisioning), needs Docker-in-Docker locally, and limits connections to dbt's `profiles.yml` instead of Airflow connections. Overkill for this project. Rejected.
- **dbt in the Airflow image (`LOCAL`, no isolation / as a library)** — couples the dbt and Airflow lifecycles and dependency trees; a bad dbt dependency could touch the scheduler/workers. Rejected on principle even though it currently resolves.

## Consequences

- dbt's dependency tree is isolated from Airflow; the two upgrade independently.
- A build step provisions the dbt venv from `dbt-requirements.txt` (persisted, not per-run).
- No second interpreter; the venv uses the runtime's Python 3.13. **Risk to monitor:** 3.13 is not the Runtime default, so every image bump has to carry the `-python-3.13` tag or the interpreter moves silently; if a future Runtime drops 3.13 before `dbt-snowflake` supports the newer interpreter, revisit with a pinned second interpreter or a container mode.
- Connections/secrets keep flowing through the Airflow/Cosmos profile mapping (container modes would have forced `profiles.yml`).
