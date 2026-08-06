# ADR-0004: Data-quality failure handling

- Status: Accepted
- Date: 2026-07-17

## Context

The pipeline must distinguish invalid source records from failures that indicate that the transformation or its assumptions are no longer valid. dbt tests report pass or fail for a dataset; they do not determine how individual records should be handled.

## Decision

Records that fail row-level validation are excluded during the silver transformation. Their presence does not block processing or publication of valid records.

Tests that indicate a broken data contract block publication to gold and send an alert.

## Consequences

- Silver contains only records that passed row-level validation.
- Tests that block publication are explicitly configured as errors; record-level validation does not block the pipeline.
- Silver transformations handle row-level validation; dbt tests enforce publication-blocking contracts.
