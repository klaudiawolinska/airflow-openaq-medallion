"""Test-wide runtime configuration.

These tests disable the Cosmos `dbt ls` cache. Cosmos stores that cache in an
Airflow Variable, but DAG-integrity tests parse DAGs without a metadatabase.
"""

import os


os.environ["AIRFLOW__COSMOS__ENABLE_CACHE"] = "False"
