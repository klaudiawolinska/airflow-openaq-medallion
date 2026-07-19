# Snowflake bootstrap

Idempotent SQL that provisions the Snowflake side of the pipeline: one database
with the medallion schemas, an XS warehouse, least-privilege roles, and key-pair
service users. Run **once by an admin**; the pipeline itself then runs as the
least-privilege role `OPENAQ_PIPELINE` — never `ACCOUNTADMIN`.

See [ADR-0016](../../../docs/adr/0016-snowflake-rbac.md) (RBAC),
[ADR-0011](../../../docs/adr/0011-snowflake-warehouse.md) (warehouse) and
[ADR-0018](../../../docs/adr/0018-snowflake-key-pair-auth.md) (key-pair auth).

## What gets created

| Object | Name | Notes |
|---|---|---|
| Warehouse | `OPENAQ_WH` | XS, `AUTO_SUSPEND=60`, `AUTO_RESUME` |
| Database | `OPENAQ` | medallion |
| Schemas | `BRONZE` / `SILVER` / `GOLD` / `CI` | managed access (owners cannot re-grant); `CI` isolates `dbt build` in CI |
| Role | `OPENAQ_PIPELINE` | least-privilege; read/write on the medallion schemas |
| Role | `OPENAQ_CI` | CI schema only; no access to the main tables |
| Role | `OPENAQ_READ` | read-only on `GOLD` (consumers / Snowsight); optional |
| User | `AIRFLOW_USER` | `TYPE=SERVICE`, key-pair; used by `snowflake_default` |
| User | `OPENAQ_CI_USER` | `TYPE=SERVICE`, key-pair; wired in M4 |

## Prerequisites

An admin session. Each script starts with `USE ROLE` on the least-privileged
system role that can do its job — `USERADMIN` (roles/users), `SYSADMIN`
(warehouse/database/schemas), `SECURITYADMIN` (grants). `ACCOUNTADMIN` inherits
all three, so running as `ACCOUNTADMIN` also works; the split just avoids relying
on it. The **pipeline never needs `ACCOUNTADMIN`** — that is asserted by the
smoke DAG (`current_role` = `OPENAQ_PIPELINE`) and the negative-permission check.

## 1. Generate the key pair (key-pair auth)

`AIRFLOW_USER` is `TYPE = SERVICE`, so Snowflake accepts key-pair only (no
password / MFA). Generate an unencrypted PKCS#8 key for local dev:

```bash
mkdir -p include/.keys                       # gitignored — private keys never committed
openssl genrsa 2048 \
  | openssl pkcs8 -topk8 -inform PEM -nocrypt \
      -out include/.keys/airflow_user_rsa.p8
openssl rsa -in include/.keys/airflow_user_rsa.p8 \
      -pubout -out include/.keys/airflow_user_rsa.pub
# The one-line public key to paste into 03_users.sql (strips PEM header/footer):
grep -v -- '-----' include/.keys/airflow_user_rsa.pub | tr -d '\n'; echo
```

> For production/CI prefer an **encrypted** key (drop `-nocrypt`, add a passphrase)
> and pass the passphrase via `private_key_file_pwd` in the connection extra.

## 2. Run the scripts (in order)

Paste the public key from step 1 into the `RSA_PUBLIC_KEY` placeholder in
`03_users.sql` first (the script fails on the placeholder by design). Then run,
in order, in Snowsight or snowsql:

```text
00_warehouse_database.sql   # warehouse, database, schemas
01_roles.sql                # functional roles
02_grants.sql               # least-privilege grants (+ future grants)
03_users.sql                # service users (key-pair)
```

**Idempotency check:** run all four **a second time** — every statement is a
no-op or a converging `ALTER`; a second run must complete without error.

## 3. Point Airflow at Snowflake

```bash
cp .env.example .env
```

Fill `account` in `AIRFLOW_CONN_SNOWFLAKE_DEFAULT`. Use the **organisation
account identifier** `<orgname>-<account_name>` (hyphen); both parts are visible
in the Snowsight URL, `https://app.snowflake.com/<orgname>/<account_name>/...`.
A bare account locator (`ab12345`) resolves only for accounts in AWS
`us-west-2` — anywhere else the connector fails with
`404 Not Found: post <account>.snowflakecomputing.com/session/v1/login-request`
before it ever reaches authentication.

The connection uses `private_key_file` at
`/usr/local/airflow/include/.keys/airflow_user_rsa.p8` (Astro bind-mounts the
project into the container, so the key from step 1 is visible in-container).
Then:

```bash
astro dev start
```

> `.env` is read when the containers start. After editing it, run
> `astro dev restart` — re-triggering the DAG alone picks up nothing.

## 4. Verify (completion criteria)

- **Smoke connection** — trigger the `_snowflake_smoke` DAG in the UI. The task
  turns green and logs the Snowflake version with `current_role=OPENAQ_PIPELINE`.
- **Idempotency** — the second run in step 2 completed without error.
- **Negative permissions** — run [`../tests/negative_permissions.sql`](../tests/negative_permissions.sql);
  every statement fails as annotated (pipeline role cannot escalate or act out of
  scope). See that file's header for the two run modes.

## Teardown

`99_teardown.sql` drops everything (database + **all data**, roles, users,
warehouse) for a clean idempotency re-test. Destructive — not part of a normal run.
