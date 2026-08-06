# Product Requirements Document — airflow-openaq-medallion

> Status: Draft
>
> Scope: product requirements. Implementation details belong in the README and ADRs.

## 0. Scope

| Topic | Requirement |
| --- | --- |
| Source | OpenAQ API v3. |
| Geography & providers | The manual audit covers all Polish providers. Scheduled ingestion uses AirGradient and EEA locations in Poland. |
| Pollutants | PM2.5, PM10, NO2, O3, SO2, CO, BC. |
| Cadence | Hourly. |
| Ingest lookback | Each scheduled run covers the preceding 24 hours to account for source publication lag. |
| Historical backfill | A one-time backfill covers the 2025 calendar year. |
| Serving | A Snowsight dashboard reads the gold layer. |

---

## 1. Product goal

- **(Portfolio)** Demonstrate production orchestration patterns in Airflow 3: rolling-window ingest, rate-limited API access, data-aware scheduling (Assets), granular dbt integration via Cosmos, a Write-Audit-Publish quality gate, and native observability.
- **(Domain)** Deliver a reliable, denoised air-quality dataset in the gold layer, ready for analytics.

**Success =** a repository where (a) the local orchestration environment starts with a single command after a one-time credential setup, and (b) the pipeline passes green CI and publishes to gold only data that has passed the audit.

---

## 2. Problems we solve

- **Source-data quality issues** — OpenAQ contains gaps, duplicates (including across pagination pages), and out-of-range values; naive ingestion produces unreliable analytics.
- **Bad data reaching consumers** — without a quality gate, an invalid record becomes visible before anyone catches it. WAP prevents this: data reaches gold only after passing the audit.
- **Costly / rate-limited re-ingest** — re-fetching from the API is slow and rate-limited; isolating a raw bronze layer allows reprocessing without hitting the API again.
- **Duplication on re-runs** — overwriting the ingest window means re-running it does not duplicate bronze data.

---

## 3. User stories

### P1 — Operator / Data Engineer

- As an operator I want to start the local orchestration environment with a single command after a one-time credential setup, so I can iterate without standing up individual components by hand.
- As an operator I want date-parameterized, overwrite-per-window loads with safe backfill, so reprocessing a window does not duplicate data.
- As an operator I want granular retry of a single dbt model/test, so one failure does not force re-running the whole transform (Cosmos).

### P2 — Technical reviewer

- As a reviewer I want to see design decisions with their rationale in the README, so I can assess the soundness of the architecture without reading all the code.
- As a reviewer I want to see green CI and a PR history, so I can confirm the project is functional and developed through a controlled, repeatable process.
- As a reviewer I want a readable DAG graph and dbt lineage, so I can understand the data flow in a few minutes.

### P3 — Analyst / data consumer

- As an analyst I want to trust that gold contains no data that failed the audit, so I can build reports without manual cleaning.
- As an analyst I want ready-made aggregates (per station / pollutant / time window), so I don't recompute them from raw data.

> **Acceptance (general).** Each story is "done" when the corresponding mechanism works end-to-end and is either covered by a test in CI or visible in the UI/README. Detailed acceptance criteria will be defined during the functional-scope stage.

---

## 4. Non-functional requirements

| Category | Requirement |
| --- | --- |
| Idempotency | Reprocessing a window produces the same published result and does not create duplicates. |
| Reproducibility | A contributor can start the local environment with one command after one-time credential setup. |
| Reliability and recovery | The pipeline retries transient source failures and supports date-parameterized backfill. |
| Data quality | Gold receives only data that has passed the quality audit; invalid source records remain available for inspection outside gold. |
| Pipeline alerts | The pipeline alerts its operator when a run fails. |
| Security and secrets | Credentials remain outside code and access is limited to each workload's scope. |
| Maintainability | Green CI is required before merge, with unit, data, and DAG-integrity checks. |
| Cost and footprint | The project runs locally and uses a small warehouse footprint. |
| Scalability | Ingestion stays within the OpenAQ request limit. |
| Documentation | The README and dbt documentation explain usage, source behavior, and lineage. |

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

- A persistent sensor-fetch server error — log the affected sensor and continue the ingest run; the window summary exposes any resulting absent records.
- Backfill of an already-loaded window (idempotency).
- Overlapping runs / concurrency; retry storms.
- Missing or expired secret; loss of the Snowflake connection during a load or transformation.

### WAP / dbt

- A data-contract test fails → no publication to gold + alert; invalid source records are excluded from gold without blocking publication (see ADR-0004).
- Ingest fails before emitting its Asset → transform does not run and the published data remains unchanged.
- Empty silver / a window with no measurements (a legitimate absence vs an error).

## 6. Open items

The concrete set of gold marts and the analytical question each one answers. Candidate questions to preserve:

1. **Limit exceedances** — days per year a station exceeds the PM10 daily limit, the PM2.5 annual mean, etc.; station/city rankings by number of exceedances.
2. **Seasonality** — winter PM/SO2 (domestic heating) vs the summer O3 peak.
3. **Diurnal profile** — NO2 rush-hour peaks, O3 afternoon peaks.
4. **Geography** — cleanest / dirtiest regions.
5. **O3 ↔ NO2 relationship** — titration chemistry (locally high NO2 suppresses O3).
6. **Per-station data completeness / quality** — the data-quality gold model.

Also to confirm: whether the "single-command start" stays a success criterion or moves to a convenience note under NFRs.

---

## 7. Improvement proposals

- **Data-quality metrics as a dedicated gold model** + a dashboard.
- **Slim CI** with state deferral (`state:modified+`) as the project grows.
- **Statistical anomaly detection** on measurements as an advanced audit step.
- **Operational lineage** through OpenLineage.
- **Parameterized DAG** for ad-hoc backfill of an arbitrary window/location.
- **Historical reconciliation:** manually compare an arbitrary closed UTC window with the current OpenAQ response and report differences.
