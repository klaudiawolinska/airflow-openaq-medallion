# Architecture Decision Records

Short records of significant technical decisions: the context, the decision, and consequences. One decision per file, Nygard-lite. A later ADR may supersede an earlier one (noted in **Status**).

Template: [0000-template.md](0000-template.md)

| ADR | Decision | Status |
|-----|----------|--------|
| [0003](0003-wap-quality-gate.md) | Write-Audit-Publish quality gate via dbt tests | Accepted |
| [0004](0004-wap-failure-handling.md) | Data-quality failure handling | Accepted |
| [0005](0005-dbt-via-cosmos.md) | Expose dbt models and tests as Airflow tasks | Accepted |
| [0006](0006-scheduling-model.md) | Scheduled ingestion and asset-triggered transformation | Accepted |
| [0008](0008-bronze-load-strategy.md) | Bronze load by overwrite window | Accepted |
| [0009](0009-scheduled-provider-scope.md) | Scheduled ingestion provider scope | Accepted |
