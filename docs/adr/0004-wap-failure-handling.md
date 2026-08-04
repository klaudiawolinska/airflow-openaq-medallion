# ADR-0004: Data-quality failure handling

- Status: Accepted
- Date: 2026-07-17

## Context

The pipeline must distinguish invalid source records from failures that indicate that the transformation or its assumptions are no longer valid. dbt tests report pass or fail for a dataset; they do not determine how individual records should be handled.

## Decision

Invalid source records, including missing required values, duplicate observations, and measurements outside the accepted range, are excluded from gold and retained or marked in silver for inspection. Their presence does not block publication of valid data.

Tests that indicate a broken data contract, such as an unexpected schema change or a uniqueness failure after cleansing, block publication to gold and send an alert.

## Consequences

- Silver records why a source record was excluded from gold.
- Tests that block publication are explicitly configured as errors; record-level validation does not block the pipeline.
- The boundary between record-level validation and publication-blocking checks is maintained with the dbt tests.
