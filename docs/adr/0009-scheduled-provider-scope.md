# ADR-0009: Scheduled ingestion provider scope

- Status: Accepted
- Date: 2026-08-05

## Context

The manual `openaq_audit` DAG examines every Polish sensor for the target parameters during a requested UTC window. An audit covering 2026-04-06 22:00 UTC through 2026-08-04 22:00 UTC found measurements only from AirGradient and EEA. Scheduled ingestion must define a provider scope instead of polling every Polish provider.

## Decision

Scheduled ingestion includes Polish locations from AirGradient (provider ID 66) and EEA (provider ID 70). The manual audit remains unfiltered by provider so it can assess the wider Polish source landscape.

## Alternatives considered

- **Ingest every Polish provider** — rejected because the audit found no measurements from the other providers in the audited window.

## Consequences

- Scheduled ingestion does not retrieve measurements from other Polish providers.
- The provider IDs are part of the ingest configuration and must change with any future change to the scheduled provider scope.
