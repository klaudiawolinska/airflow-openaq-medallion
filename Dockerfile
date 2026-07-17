# Astro Runtime 3.3-2 bundles Apache Airflow 3.3.0 (Python 3.14).
# Airflow 3.2+ is required for Deadline Alerts (AIP-86) — see docs/adr/0001.
# Local dev and CI both build from this single image (ADR-0012).
FROM astrocrpublic.azurecr.io/runtime:3.3-2
