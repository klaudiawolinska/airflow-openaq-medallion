# Snowflake bootstrap

Idempotent SQL that provisions the Snowflake side of the pipeline: one database with the medallion schemas, an XS warehouse, least-privilege roles, and key-pair service users. Run by an administrator to provision the Snowflake environment.

## What gets created

| Object    | Name                                | Notes                                                 |
| --------- | ----------------------------------- | ----------------------------------------------------- |
| Warehouse | `OPENAQ_WH`                         | XS, `AUTO_SUSPEND=60`, `AUTO_RESUME`                  |
| Database  | `OPENAQ`                            | medallion                                             |
| Schemas   | `BRONZE` / `SILVER` / `GOLD` / `CI` | managed access; `CI` isolates `dbt build` in CI       |
| Role      | `OPENAQ_PIPELINE`                   | least-privilege; read/write on the medallion schemas  |
| Role      | `OPENAQ_CI`                         | CI schema only; no access to the main tables          |
| Role      | `OPENAQ_READ`                       | read-only on `GOLD` (consumers / Snowsight)           |
| User      | `AIRFLOW_USER`                      | `TYPE=SERVICE`, key-pair; used by the default Airflow Snowflake connection |
| User      | `OPENAQ_CI_USER`                    | `TYPE=SERVICE`, key-pair                              |

## Prerequisites

Each script starts with `USE ROLE` for the least-privileged system role required to perform its task:
- `SYSADMIN` – warehouse, database, schemas
- `SECURITYADMIN` – grants
- `USERADMIN` – roles and users

## 1. Generate RSA key pairs

`AIRFLOW_USER` and `OPENAQ_CI_USER` are `SERVICE` users and authenticate using RSA key pairs.

Generate unencrypted PKCS#8 private keys for local development only:

```bash
mkdir -p include/keys                       # gitignored
for user in airflow_user openaq_ci_user; do
  openssl genrsa 2048 \
    | openssl pkcs8 -topk8 -inform PEM -nocrypt \
        -out "include/keys/${user}_rsa.p8"
  openssl rsa -in "include/keys/${user}_rsa.p8" \
        -pubout -out "include/keys/${user}_rsa.pub"
done
```

Extract each public key as one line and paste it into the matching placeholder in `03_users.sql`:

```bash
for user in airflow_user openaq_ci_user; do
  printf '%s: ' "$user"
  grep -v -- '-----' "include/keys/${user}_rsa.pub" | tr -d '\n'; echo
done
```

> For production or CI, use an **encrypted** private key (omit `-nocrypt` and provide a passphrase). Configure the passphrase using the `private_key_file_pwd` connection parameter.

## 2. Run the bootstrap scripts

Run the following scripts in order using Snowsight or `snowsql`:

```text
00_warehouse_database.sql   # warehouse, database, schemas
01_roles.sql                # functional roles
02_grants.sql               # least-privilege grants (+ future grants)
03_users.sql                # service users and authentication
```

The bootstrap scripts are idempotent and can be run multiple times safely.

## 3. Configure the Snowflake connection

```bash
cp .env.example .env
```

Update `AIRFLOW_CONN_SNOWFLAKE_DEFAULT` in `.env`:

- Set `account` to your organisation account identifier in the form `<orgname>-<account_name>`. This identifier is visible in the Snowsight URL:
  ```text
  https://app.snowflake.com/<orgname>/<account_name>/...
  ```
- The account locator alone (for example `ab12345`) works only for AWS `us-west-2`. For all other regions or cloud providers, use the organisation account identifier.
- The connection is configured to use the private key generated in step 1 at:
  ```
  /usr/local/airflow/include/keys/airflow_user_rsa.p8
  ```
  Astro bind-mounts the project into the container, so no additional configuration is required.

Start the local environment:

```bash
astro dev start
```

> `.env` is read only when the containers start. If you change it later, restart the environment with `astro dev restart`.

## 4. Verify the setup

- **Test the Snowflake connection** – trigger the `_snowflake_smoke` DAG in the Airflow UI. The DAG should complete successfully.
- **Least-privilege verification (optional)** – run [`../tests/negative_permissions.sql`](../tests/negative_permissions.sql). Every statement in the script is expected to fail, demonstrating that `OPENAQ_PIPELINE` cannot perform actions outside its intended scope.

## Teardown

`99_teardown.sql` removes all resources created by the bootstrap scripts, including the database (and all data), roles, users, and warehouse.

> **Warning:** This script is destructive and is not intended for normal use. Run it only when you need to reset the environment and bootstrap it again from scratch.
