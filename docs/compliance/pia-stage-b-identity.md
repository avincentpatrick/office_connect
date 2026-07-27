# Privacy Impact Assessment (PIA) — Identity, Directory & Access

Per **NPC Advisory 2017-03** (the per-module governance gate, master-plan §3.1).
Completed before real personal data enters the identity/directory subsystem in ANY
environment. Follows [`pia-template.md`](pia-template.md); see
[`../modules/foundation.md`](../modules/foundation.md) §5/§7 (Stage B) for the build.

> **Module:** Identity, Directory & Access (authentication · RBAC · staff directory)
> **PIC/PIP:** BLHSD / DOH (reference tenant)
> **Assessor:** Office-Connect engineering (Stage B) **Date:** 2026-07-27 **Version:** 1.0

## 1. Description of the processing

- **Purpose & lawful basis.** Authenticate and authorize personnel, and maintain the
  plantilla-authoritative person directory that other modules join. Lawful basis:
  **RA 10173 §12(b)** (processing necessary for compliance with a legal obligation)
  and **§12(e)** (functions of a public authority / the office's mandate) — **not
  consent**. **No §13 sensitive-personal-information category is processed** (no
  race/ethnicity, health, genetic/sexual life, offenses, or government-issued ID
  numbers); the identity data is ordinary personal information.
- **Personal data collected — by table:**
  - `core_staff` (directory): `employee_no`, `given_name`, `middle_name`, `surname`,
    `full_name`, `email`, `position_title`, `plantilla_item_no`, `employment_status`,
    `division_id`, `section_id`. *(Personal information; no RA-10173 SPI category.)*
  - `core_users` (login accounts): `email` (login handle), `password_hash`
    (Argon2id — a credential, never in the audit chain), `mfa_secret` (TOTP secret —
    never in the chain), `must_change_password`/`mfa_enabled`/`is_active`/
    `is_break_glass`/`auth_source` flags, `permissions_version`, `last_login_at`,
    `staff_id`.
  - `core_login_attempts` (append-only): identifier, outcome, IP, session-id hash,
    timestamps — the anti-enumeration / throttle trail. **Never the password.**
  - `core_sessions` (Redis db 4, ephemeral): opaque session id, user id, a roles
    snapshot, timeout stamps. TTL-bounded; destroyed on logout / password change /
    deactivation.
  - `core_notification_preferences`: `user_id`, `channel`, `module`, `enabled`
    (a delivery opt-out choice — not personal-sensitive).
- **Data subjects.** Employees / plantilla persons (the directory superset) and the
  subset who hold login accounts.
- **Data flow.** **CSS-IS inbound feed (feed-only; no code dependency, no live link)
  → `core_org_units` / `core_staff`** (dev/UAT run on synthetic fixtures) → admin
  provisioning creates a `core_users` login (**no self-registration**) → login
  (Argon2id + throttle + TOTP MFA for privileged roles) mints a **server-side Redis
  session** → `AuthPrincipalMiddleware` resolves it to a request Principal → RBAC
  (`require_permission`, Redis-cached, org-scoped) authorizes → every write is
  **hash-chained** in `core_audit_logs` with **person-field SPI redaction** (values
  withheld, field names kept) → every `/api/v1` request is recorded in
  `core_query_logs` (ids + param names only, never values) → offboarding =
  `is_active=false` + immediate session revocation (soft delete, never a hard delete;
  no automated purge).
- **Systems/actors.** This platform (FastAPI · PostgreSQL 16 · Redis · Celery);
  the reverse proxy (TLS termination); CSS-IS (upstream directory feed); the DPO and
  the read-only auditor role.

## 2. Necessity & proportionality

- **Field necessity.** Name / email / position / plantilla item / employee number are
  the minimum for a usable directory and for payroll-adjacent correlation; the auth
  fields are the minimum for login, MFA, and RBAC. Nothing is collected beyond
  directory + authentication needs; no SPI category is collected at all.
- **Retention.** Identity/directory records follow the personnel-record posture:
  retention class **`default` (10 years, GRDS-conservative)**; offboarding is soft
  delete + session revocation, **not** records disposition; **no automated purge**
  (`legal_hold` blocks disposal unconditionally). Access logs (`core_query_logs`) and
  login attempts (`core_login_attempts`) are operational security records; a defined
  purge window is a documented follow-up (no purge job exists today — consistent with
  the no-auto-purge posture). See [`retention-schedule.md`](retention-schedule.md).
- **Disclosures / sharing.** Internal only, RBAC-gated. The read-only **auditor** role
  (COA Res. 2020-034) may read the trail and run chain verification. **No external
  sharing** in this subsystem.

## 3. Risks to data subjects

| Risk | Likelihood | Impact | Existing control | Residual | Action |
|---|---|---|---|---|---|
| Unauthorized access | Low | High | RBAC + least-privilege `oc_app` (no DELETE) + server-side sessions + TOTP MFA for privileged roles + throttle-not-lockout | Low | — |
| Excessive collection | Low | Low | field minimization (directory + auth only; no SPI category) | Low | — |
| Loss of integrity | Low | High | hash-chained `core_audit_logs` + `verify_chain()` + proven-restore backups | Low | — |
| Improper retention | Medium | Medium | retention schedule + `legal_hold` + no auto-purge | Low | define a `core_query_logs` retention window (follow-up) |
| Breach in transit / at rest | Low | High | TLS at the edge + encrypted volume; credentials never leave the server (Argon2id, opaque session ids) | Low | — |
| **SPI/PII exposure in logs** | Low | High | **person-field values redacted from the immutable audit chain (WS5); query log stores ids/param-names only, never values/bodies (WS4); credentials never logged** | Low | — |

## 4. Controls mapped to this platform

- **Access control.** Least-privilege `oc_app` (no DELETE anywhere; no UPDATE on
  append-only tables); RBAC on permission strings; admin-only provisioning (no
  self-registration); deactivation revokes all sessions immediately.
- **Authentication.** Argon2id + NIST 800-63B-4 policy (length + top-100k blocklist,
  no composition/rotation); throttle-not-lockout; custom-header CSRF; server-side
  Redis sessions (opaque id, HttpOnly/Secure/SameSite, rotation on privilege change);
  TOTP MFA for approver/admin (NPC Circular 2023-06); a break-glass local admin.
- **Auditability.** Hash-chained `core_audit_logs` + `verify_chain()`; the read-only
  auditor report + per-record timeline (COA Res. 2020-034).
- **Person-field SPI in logs.** Direct identifiers (`core_staff` names + directory
  email; notification recipient/body/payload) are **excluded from the immutable audit
  payload** — the field name is recorded, the value is resolved at read from the live
  row. Credentials (`password_hash`, `mfa_secret`) were already excluded in B1.
- **Privacy-preserving access log.** `core_query_logs` records who accessed what
  (module/resource/action + ids + param names + status), never bodies or query values.
- **Retention.** `retention_class` / `retention_starts_at` / `legal_hold`; no
  auto-purge; disposal-eligibility report.
- **Breach readiness.** [`breach-runbook.md`](breach-runbook.md) (72-hour notify /
  5-day report).

## 5. Sign-off

- **Residual risk acceptable?** **Yes** — ordinary personal information only (no
  RA-10173 SPI category), processed under a public-authority mandate, behind layered
  access / audit / redaction controls; residual risks are Low after controls.
- **DPO / HoPE approval:** __________ **Date:** __________
- **Review date (re-assess on material change):** on any change to the identity data
  set or a new authentication backend (e.g. enabling the LDAP verifier), else at the
  next annual NPC registration renewal.
