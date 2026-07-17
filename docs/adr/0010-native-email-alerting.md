# ADR-0010: Native email alerting via a custom BaseNotifier

- Status: Accepted
- Date: 2026-07-17

## Context

The project needs failure alerting without standing up an external observability stack. Airflow provides `BaseNotifier` (since 2.6) as a reusable, templated notification class, delivered through callback hooks.

## Decision

A custom **`BaseNotifier`** subclass sends **email over SMTP**, attached via **`on_failure_callback`**. **Deadline Alerts** ([ADR-0001](0001-airflow-3-deadline-alerts.md)) cover run overruns. Retries are **not** alerted on.

## Alternatives considered

- **External stack (Prometheus/Grafana, PagerDuty/Opsgenie)** — adds infrastructure and is out of scope for a self-contained project. Rejected.
- **A bare callback function** — a `BaseNotifier` is reusable across DAGs, supports templated fields, and is testable in isolation. Rejected.
- **Alerting on `on_retry_callback`** — retries are expected and transient; alerting on them is noise. Rejected.

## Consequences

- One reusable notifier across DAGs, one channel (email).
- The notifier is the **payload** delivered *through* a callback hook — not a separate "layer".
- Additional channels (Slack, PagerDuty) can be added later through the same `BaseNotifier` interface.
