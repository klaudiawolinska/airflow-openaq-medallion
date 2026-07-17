"""DAG-integrity tests.

Fast, runtime-free checks that every DAG in ``dags/``:
  * imports without error (this also surfaces dependency cycles, which Airflow
    reports as import errors during parsing);
  * defines at least one tag;
  * sets ``default_args['retries'] >= MIN_RETRIES`` so transient failures are
    retried before an alert fires.

Run inside the Astro runtime image in CI (``python -m pytest tests``), so the
DagBag parses against the exact Airflow version we deploy.
"""

import logging
from contextlib import contextmanager

import pytest
from airflow.models import DagBag

MIN_RETRIES = 2


@contextmanager
def _suppress_airflow_logging():
    logger = logging.getLogger("airflow")
    previously_disabled = logger.disabled
    logger.disabled = True
    try:
        yield
    finally:
        logger.disabled = previously_disabled


@pytest.fixture(scope="module")
def dag_bag() -> DagBag:
    # include_examples=False -> only this project's DAGs. DagBag records import
    # errors (including cycles) rather than raising, so we assert on them below.
    with _suppress_airflow_logging():
        return DagBag(include_examples=False)


def test_no_import_errors(dag_bag: DagBag) -> None:
    assert not dag_bag.import_errors, "DAG import errors:\n" + "\n".join(
        f"  {path}: {error}" for path, error in dag_bag.import_errors.items()
    )


def test_at_least_one_dag(dag_bag: DagBag) -> None:
    assert dag_bag.dags, "No DAGs found in the dags/ folder."


def test_all_dags_have_tags(dag_bag: DagBag) -> None:
    untagged = [dag_id for dag_id, dag in dag_bag.dags.items() if not dag.tags]
    assert not untagged, f"DAGs missing tags: {untagged}"


def test_all_dags_set_retries(dag_bag: DagBag) -> None:
    offenders = []
    for dag_id, dag in dag_bag.dags.items():
        retries = (dag.default_args or {}).get("retries")
        if retries is None or retries < MIN_RETRIES:
            offenders.append((dag_id, retries))
    assert not offenders, (
        f"DAGs must set default_args['retries'] >= {MIN_RETRIES}; "
        f"offenders (dag_id, retries): {offenders}"
    )
