FROM astrocrpublic.azurecr.io/runtime:3.3-2-python-3.13

COPY --chown=astro:0 dbt-requirements.txt /tmp/dbt-requirements.txt
RUN python -m venv /usr/local/airflow/dbt-venv \
    && /usr/local/airflow/dbt-venv/bin/pip install --no-cache-dir -r /tmp/dbt-requirements.txt
