# Product Requirements Document — airflow-openaq-medallion

> Status: Draft · Last updated: 2026-07-17
> Scope of this document: product-level requirements only — no architecture or code.

## 0. Input decisions & assumptions

| # | Decision |
|---|---|
| A1 | Built on **Apache Airflow 3.2+**. Long-running-run alerting uses **Deadline Alerts (AIP-86)** — the DAG-level replacement for the classic task-level SLA that was removed in Airflow 3.0. |
| A2 | Warehouse: **Snowflake** (XS warehouse, aggressive auto-suspend for cost efficiency). |
| A3 | Source: **OpenAQ API v3** with a free API key, handled as a secret. |
| A4 | **SCD Type 2** on the station dimension, implemented with dbt snapshots. |
| A5 | **Email (SMTP)** as the single notification channel, sent via a custom `BaseNotifier`. |
| A6 | Solo development with a **PR-based flow**: branch protection requires green CI (no required human review, which GitHub blocks for a PR author); **CodeRabbit** provides automated review. |

### Resolved scope

| Topic | Decision |
|---|---|
| Geography | Whole of **Poland** (150+ GIOŚ stations available in OpenAQ). |
| Pollutants | **PM2.5, PM10, NO2, O3, SO2** (CO optional, added later if useful). |
| Cadence | **Hourly**. |
| Working window | The pipeline runs on a rolling **30-day window** for development and quick iteration. |
| Historical backfill | A one-time backfill of the **full calendar year 2025** (from 2025-01-01) is planned, to provide a complete year of history. Chunked (e.g. per month) and rate-limit-aware. |
| SCD2 snapshot cadence | **Daily**. |
| Serving | **Snowsight dashboard** on the gold layer — no additional stack. |
| Warehouse sizing | **XS** with aggressive auto-suspend (60 s minimum). |
| CI scope | DAG-integrity + lint **+ `dbt build`** (run + test) on every PR. |
| WAP failure handling | Expected dirt (nulls, out-of-range, duplicates) → **quarantined in silver** (non-blocking); integrity violations (uniqueness, freshness, schema) → **fail-closed at the gate** (block gold + alert). See ADR-0004. |

> **Decision log.** Technical decisions, with alternatives and consequences, are recorded as ADRs in [docs/adr/](adr/).

> **Volume note.** ~150 stations × ~5 pollutants at hourly granularity is on the order of **5–8M rows per year** — trivial for Snowflake. The binding constraint on backfill is the OpenAQ rate limit (**60 req/min, 2000 req/h**), so historical loads are chunked and use 429/backoff handling.

---

## 1. Product goal

- **(Portfolio)** Demonstrate production orchestration patterns in Airflow 3: incremental ingest, dynamic task mapping, data-aware scheduling (Assets), granular dbt integration via Cosmos, a Write-Audit-Publish quality gate, and native observability.
- **(Domain)** Deliver a reliable, denoised air-quality dataset in the gold layer — with preserved history of station-metadata changes (SCD2) — ready for analytics.

**Success =** a repository where (a) the local orchestration environment starts with a single command after a one-time credential setup, and (b) the pipeline passes green CI and publishes to gold only data that has passed the audit.

---

## 2. Problems we solve

- **Dirty source data** — OpenAQ contains gaps, duplicates (including across pagination pages), and out-of-range values; naive ingestion produces unreliable analytics.
- **Bad data reaching consumers** — without a quality gate, an invalid record becomes visible before anyone catches it. WAP prevents this: data reaches gold only after passing the audit.
- **Costly / rate-limited re-ingest** — re-fetching from the API is slow and rate-limited; isolating a raw bronze layer allows reprocessing without hitting the API again.
- **Duplication on re-runs** — an idempotent MERGE (instead of append) means re-running a window does not duplicate data.
- **Silent failure** — without observability a failure passes unnoticed; three complementary alerting layers surface it before it propagates downstream.
- **Loss of dimension history** — station attributes change over time; without SCD2 the "as-it-was" state is lost.

---

## 3. User stories

### P1 — Operator / Data Engineer
- As an operator I want to start the local orchestration environment with a single command after a one-time credential setup, so I can iterate without standing up individual components by hand.
- As an operator I want incremental, date-parameterized loads with safe backfill, so reprocessing a window does not duplicate data.
- As an operator I want a failure in one location's ingest not to fail the entire run, so partial success is possible (dynamic mapping).
- As an operator I want granular retry of a single dbt model/test, so one failure does not force re-running the whole transform (Cosmos).
- As an operator I want an alert when a task fails or a run exceeds its deadline, so I don't have to watch the UI.

### P2 — Technical reviewer
- As a reviewer I want to see design decisions with their rationale in the README, so I can assess the soundness of the architecture without reading all the code.
- As a reviewer I want to see green CI and a PR history, so I can confirm the project is functional and developed through a controlled, repeatable process.
- As a reviewer I want a readable DAG graph and dbt lineage, so I can understand the data flow in a few minutes.

### P3 — Analyst / data consumer
- As an analyst I want to trust that gold contains no data that failed the audit, so I can build reports without manual cleaning.
- As an analyst I want ready-made aggregates (per station / pollutant / time window), so I don't recompute them from raw data.
- As an analyst I want the history of station attributes (SCD2), so I can correctly interpret data "as the station was" at a given time.

> **Acceptance (general).** Each story is "done" when the corresponding mechanism works end-to-end and is either covered by a test in CI or visible in the UI/README. Detailed acceptance criteria will be defined during the functional-scope stage.

---

## 4. Non-functional requirements

| Category | Requirement | Measure / rationale |
|---|---|---|
| Idempotency | Re-running the same window does not change the result | Bronze: overwrite-per-window (delete + insert). Silver/gold: dbt incremental (merge on key). Test for absence of duplicates |
| Reproducibility | Local environment starts with one command after a one-time credential setup | `astro dev start`; pinned Airflow 3.2+, dbt, Cosmos; `.env` from `.env.example` |
| Reliability / recovery | Retries, backfill, partial success | retries + backoff, date parameterization, dynamic mapping |
| Data quality | Data reaches gold only after audit | WAP gate = dbt tests (not_null, unique, accepted_range, freshness) |
| Observability & alerting | Three complementary layers, native | custom Notifier, callbacks, Deadline Alerts; no external stack |
| Security / secrets | Credentials outside code | `.env` / Secrets Backend; repo ships only `.env.example`; OpenAQ key as a secret |
| Maintainability | Green CI required before merge | layered tests — Python unit, dbt unit + data tests, DAG-integrity (pytest), `dbt build`; lint; CodeRabbit on PRs (see ADR-0014) |
| Cost / footprint | Low cost, small footprint | local start, public repo (CodeRabbit Pro free), XS warehouse with aggressive auto-suspend |
| Scalability | Handles the Poland-wide hourly volume | dynamic mapping + incremental model |
| Documentation | README + dbt docs + PRD | decision rationale, diagram, lineage |
| Versioning / portability | Deliberate pin to Airflow 3.2+ | dependency on Deadline Alerts / Task SDK / Asset API |

---

## 5. Edge cases

### Source / API
- 429 (rate limit), 5xx, timeout, no response, empty result page.
- Pagination: duplicate records across pages; incomplete last page.
- Schema drift (new/changed fields), inconsistent units, missing/null measurement values.
- Out-of-range values: negative concentrations, implausibly high readings.
- Time zones / DST in timestamps; late-arriving data after a window closes.
- A station appears or disappears between runs.

### Orchestration
- Partial failure of dynamic mapping (some locations fail, some succeed) — how to report and resume.
- Backfill of an already-loaded window (idempotency).
- Overlapping runs / concurrency; retry storms.
- A run exceeds its deadline → Deadline Alert (rather than failing the task).
- Missing/expired secret; loss of the Snowflake connection mid-load (bronze) or mid-MERGE (silver/gold).

### WAP / dbt
- An integrity test fails → no publish to gold + alert (fail-closed); expected-dirt rows are quarantined in silver rather than blocking (see ADR-0004).
- Ingest emitted no Asset (0 records) → transform does not run → data looks "stale".
- Empty silver / a window with no measurements (a legitimate absence vs an error).

### SCD2 (station dimension)
- Spurious change due to float jitter in coordinates → needs normalization / hashdiff.
- A station disappears (soft-delete → `is_current = false`?) and later reappears.
- A change in the station's set of sensors.

### Alerting
- Alert storm (many tasks fail at once) — deduplication / throttling.
- The notifier itself fails — fallback / graceful degradation.
- Alerting on an expected zero-row window — avoid false positives.

---

## 6. Open items (to close during the functional-scope stage)

The concrete set of gold marts and the analytical question each one answers. Candidate questions to preserve:

1. **Limit exceedances** — days per year a station exceeds the PM10 daily limit, the PM2.5 annual mean, etc.; station/city rankings by number of exceedances.
2. **Seasonality** — winter PM/SO2 (domestic heating) vs the summer O3 peak.
3. **Diurnal profile** — NO2 rush-hour peaks, O3 afternoon peaks.
4. **Geography** — cleanest / dirtiest regions.
5. **O3 ↔ NO2 relationship** — titration chemistry (locally high NO2 suppresses O3).
6. **Per-station data completeness / quality** — the data-quality gold model.

Also to confirm: whether the "single-command start" stays a success criterion or moves to a convenience note under NFRs.

---

## 7. Improvement proposals (future, outside the core)

- **Data-quality metrics as a dedicated gold model** + a dashboard.
- **dbt source freshness** + freshness-based alerting.
- **Model contracts** (dbt 1.5+) on gold marts — enforced schema.
- **Slim CI** with state deferral (`state:modified+`) as the project grows.
- **Schema-drift detection** on the bronze ingest + a circuit breaker if the API shape changes.
- **Statistical anomaly detection** on measurements as an advanced audit step.
- **End-to-end / operational lineage via OpenLineage.** Note: Airflow 3 emits OpenLineage events natively, but a full Marquez backend adds a stack that conflicts with the "no extra observability stack" stance — a lightweight native emission is the lighter alternative.
- **Additional notification channels** (e.g. Slack, PagerDuty) through the same `BaseNotifier`.
- **Parameterized DAG** for ad-hoc backfill of an arbitrary window/location.
