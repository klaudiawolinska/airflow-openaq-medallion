# Architecture Decision Records

Short records of significant technical decisions: the context, the decision, alternatives considered, and consequences. One decision per file, Nygard-lite. A later ADR may supersede an earlier one (noted in **Status**).

Template: [0000-template.md](0000-template.md)

| ADR | Decision | Status |
|-----|----------|--------|
| [0001](0001-airflow-3-deadline-alerts.md) | Build on Apache Airflow 3.2+; Deadline Alerts replace the task-level SLA | Accepted |
| [0002](0002-medallion-architecture.md) | Medallion architecture (bronze / silver / gold) | Accepted |
| [0003](0003-wap-quality-gate.md) | Write-Audit-Publish quality gate via dbt tests | Accepted |
| [0004](0004-wap-failure-handling.md) | WAP failure handling: quarantine expected dirt, fail-closed on integrity | Accepted |
| [0005](0005-dbt-via-cosmos.md) | Orchestrate dbt with Cosmos (per-model tasks) | Accepted |
| [0006](0006-scheduling-model.md) | Scheduled ingest + Asset-driven transform | Accepted |
| [0007](0007-dynamic-task-mapping-per-location.md) | Dynamic task mapping per location | Accepted |
| [0008](0008-bronze-load-strategy.md) | Bronze load: idempotent overwrite-per-window (not MERGE) | Accepted |
| [0009](0009-scd2-station-dimension.md) | SCD Type 2 on the station dimension via dbt snapshots | Accepted |
| [0010](0010-native-email-alerting.md) | Native email alerting via a custom BaseNotifier | Accepted |
| [0011](0011-snowflake-warehouse.md) | Snowflake warehouse (XS, aggressive auto-suspend) | Accepted |
| [0012](0012-astro-cli-only.md) | Local dev via the Astro CLI only | Accepted |
| [0013](0013-no-deferrable-operator.md) | Deferrable operator out of scope | Accepted |
| [0014](0014-testing-strategy.md) | Layered testing strategy (unit, dbt unit, data, integration) | Accepted |
| [0015](0015-single-environment.md) | Single environment; no dev/prod separation or CD | Accepted |
| [0016](0016-snowflake-rbac.md) | Basic Snowflake RBAC and provisioning | Accepted |
| [0017](0017-dbt-execution-mode.md) | dbt execution mode: LOCAL with a dedicated virtualenv | Accepted |
