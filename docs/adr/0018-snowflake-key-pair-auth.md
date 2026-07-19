# ADR-0018: Snowflake key-pair authentication for service accounts

- Status: Accepted
- Date: 2026-07-18

## Context

The pipeline authenticates to Snowflake as a service account (`AIRFLOW_USER`),
and CI will do the same (`OPENAQ_CI_USER`, M4). [ADR-0016](0016-snowflake-rbac.md)
says credentials live outside code as an Airflow connection / `.env` secret but
does not fix the *authentication method*; the initial `.env.example` stubbed a
password.

Snowflake has since **deprecated single-factor password sign-in for
programmatic/service users** (the 2025 auth policy rollout), moving service
accounts to key-pair or OAuth and adding a first-class `TYPE = SERVICE` user for
which password/MFA sign-in is disabled outright. A password-based service login
is now liable to be blocked, so the committed password stub is no longer a valid
default.

## Decision

Authenticate both service users with **RSA key-pair**, and create them as
**`TYPE = SERVICE`**. The bootstrap sets `RSA_PUBLIC_KEY` on each user
(`include/sql/bootstrap/03_users.sql`); the private key stays local, gitignored
under `include/.keys/`, and is referenced from the Airflow connection extra via
`private_key_file` (`authenticator = snowflake_jwt`). `.env.example` ships the
key-pair form of `AIRFLOW_CONN_SNOWFLAKE_DEFAULT` (no password).

## Alternatives considered

- **Password auth** (the original stub) — simplest, but deprecated for service
  users and liable to be blocked; keeping it would ship a default that does not
  work. Rejected.
- **OAuth / external browser SSO** — appropriate for human users, but a service
  account has no interactive browser and OAuth adds an identity-provider
  dependency the project does not have. Rejected.
- **Encrypted key + passphrase everywhere** — stronger, but adds passphrase
  handling to local dev for little gain on a single-developer machine.
  Documented as the production/CI hardening (`private_key_file_pwd`); local dev
  uses an unencrypted key.

## Consequences

- A one-time key-generation step in setup (documented in the bootstrap README);
  `include/.keys/` is gitignored so private keys are never committed.
- `TYPE = SERVICE` users cannot fall back to a password — the key must be present
  and valid, which is the intended posture.
- CI (M4) provisions `OPENAQ_CI_USER`'s key as a GitHub Actions secret; the
  bootstrap already creates the user with a placeholder key.
- Supersedes the password assumption implicit in the original `.env.example`;
  refines, but does not replace, [ADR-0016](0016-snowflake-rbac.md).
