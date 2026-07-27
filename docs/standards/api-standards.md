# API & Observability Standards

Binding conventions for the HTTP API surface and runtime observability.
Introduced Increment 4 (Stage A / Phase 0); the `/api/v1/` prefix has been the
de-facto convention since Increment 1 (`GET /api/v1/config`).

## §1. API versioning

- **Every application endpoint lives under a version prefix: `/api/v1/…`.**
  Health/liveness (`/health`) and the root (`/`) are unversioned operational
  endpoints.
- **Additive within a major version.** New endpoints, new optional request
  fields, and new response fields may be added under `v1` without a version
  bump — clients must ignore unknown response fields.
- **Breaking changes require a new major prefix (`/api/v2/`).** Removing/renaming
  a field, changing a type, tightening validation, or changing status-code
  semantics is breaking. `v1` and `v2` coexist during a documented deprecation
  window.
- **Never break a shipped contract in place.** Version, don't mutate.
- Routers are mounted from `office_connect/core/api/` (core) and, later, per
  module — each under `/api/v1/<area>`.

## §2. Request/response conventions

- **`X-Request-ID`** — every request is tagged with a request id (honored from an
  inbound `X-Request-ID`, else generated). It is echoed on the response and flows
  into structured logs and the audit context. Since Stage B / Increment 2 the
  authenticated **actor** also flows in: `AuthPrincipalMiddleware` resolves the
  session cookie to `request.state.user`, and `get_session` injects `actor_id` so
  audited writes attribute to the real user (`created_by`/`updated_by`/audit chain).
- **JSON only** for request and response bodies (`application/json`); file
  downloads stream bytes with the correct `Content-Type` + `Content-Disposition`.
- **Money is server-computed**; the API returns computed `numeric(12,2)` values
  and formatted strings — the client never does money math (database-standards
  §10).
- **Times are UTC ISO-8601** on the wire (`timestamptz`); the client renders
  Asia/Manila (core/time.py).
- **Config never 500s** — `/api/v1/config` is fail-safe and returns all feature
  flags OFF under any backend degradation (never leaks non-public `settings`).

## §3. Error envelope

Error responses use a consistent shape so clients branch on `error.code`, not on
prose:

```json
{ "error": { "code": "validation_error", "message": "human-readable summary",
             "details": [ ... ] }, "request_id": "…" }
```

- HTTP status carries the class (400/401/403/404/409/422/500); `error.code` is a
  stable machine slug. Never leak DSNs, hostnames, stack traces, or SPI in an
  error body (the `/health` endpoint already exposes only the exception *type*).

## §4. Observability

- **Structured JSON logs** (`core/logging.py`): one JSON object per line with
  `ts` (UTC), `level`, `logger`, `message`, and `request_id` when set. Toggle to
  human-readable with `LOG_JSON=false`. `LOG_LEVEL` sets the threshold.
- **Request-id propagation**: the request-id middleware sets a `ContextVar` so
  every log emitted while handling a request carries its id.
- **Self-hosted error tracker** (`core/observability.py`): Sentry-SDK compatible
  (GlitchTip). **Fail-safe optional** — active only when `SENTRY_DSN` is set; no
  DSN is a no-op and a bad DSN never crashes startup. GlitchTip runs behind the
  compose `observability` profile (not in the default stack); full production
  hardening is a Stage-C/deploy task.
- **Celery operability** (master-plan §3.2): tasks use `acks_late`, bounded
  `max_retries` + back-off, and a dead-letter concept — notification dispatch
  moves exhausted rows to `status='dead'` with an append-only
  `core_notification_deliveries` trail (the failed-jobs substrate). Beat is a
  single instance.

## §5. Deferred to later stages

- **AuthN** landed Stage B / Increment 2 — see §6. **AuthZ** landed Stage B /
  Increment 3 — see §7. The **attachments / provisioning / directory** routers landed
  Stage B / Increment 4 — see §8.
- **Rate limiting, pagination envelope, WebSocket channels** (Stage D+) as the
  first real read/write endpoints land.

## §6. Sessions, authentication & CSRF (Stage B / Increment 2)

**Cookie-based server-side sessions — no bearer tokens.** Login verifies the
Argon2id password (`core/security/password.py`, reused) and mints an opaque session
id (`secrets.token_urlsafe`, 256-bit) stored server-side in Redis (db 4); the id
rides an **HttpOnly, `SameSite=Lax`, `Secure` (off only for local http), `Path=/api`**
cookie (`oc_session`). The raw id never appears in a response body — sessions are
addressed by their `sha256` handle. The id is fresh at login (fixation defense) and
**rotates** on privilege change (MFA completion, password change).

- **Timeouts (server-enforced every request):** 12 h absolute; idle 30 min for
  system_admin/approver/auditor, 60 min for staff; a used session slides its
  `last_seen_at`. Logout **destroys the server-side record** (not just the cookie).
- **Revocation:** a password change revokes all other sessions; deactivation +
  admin reset revoke all. Concurrent sessions are capped (default 3, oldest evicted).
- **Password policy (NIST 800-63B-4):** min 12, no composition, no rotation, a
  bundled top-100k blocklist; the reference's "min 8 + letter+number" is a recorded
  deviation.
- **Throttle-not-lockout:** per-account + per-IP counters, exponential backoff after
  5 failures (never a permanent lock), generic failure message (no user enumeration).
- **TOTP MFA** (approver/admin) is a two-step challenge; break-glass local admin
  bypasses the future LDAP backend but not password/MFA.
- **CSRF:** `SameSite=Lax` is the floor; every non-safe method (POST/PUT/PATCH/
  DELETE) must additionally carry the custom header `X-Requested-With` (the SPA
  fetch wrapper sets it) or the request is rejected `403 csrf_failed` before any IO.
- **Error slugs** (envelope §3): `invalid_credentials` (401, generic),
  `too_many_attempts` (429 + `Retry-After`), `mfa_required` (200 body /
  `mfa_failed` 401), `password_change_required` / `mfa_setup_required` (403 gates),
  `password_policy` (422, `details` = failing rule codes), `csrf_failed` (403).
- **Auditability:** login/throttle/MFA outcomes → `core_login_attempts`; password
  and MFA-enable changes ride the hash chain via the `core_users` UPDATE (secret
  redacted); logout / session-revoke → `append_auth_event` (a hash-chained
  `core_audit_logs` row, no secret). Never a credential in any log.

## §7. Authorization / RBAC (Stage B / Increment 3)

**Every protected route declares the permission it needs, as a STRING** — never a
role name (a role rename or a new tenant must never require a code change):

```python
@router.get("/rbac/roles")
async def list_roles(_: Principal = Depends(require_permission("rbac.role.read")), ...):
```

- **Permission strings** are the authorization currency (`module.resource.action`,
  e.g. `rbac.role.grant`, `audit.verify`, `reimb.claim.approve`). The catalog +
  the built-in role→permission grants live in `core/seeds/rbac.py`; code checks
  strings, the DB decides which roles carry them.
- **`require_permission(perm, scope=OrgUnitScope.GLOBAL)`** — the gate. The default
  `GLOBAL` scope reads the actor's effective permission set from **Redis** (db 4,
  the auth keyspace), keyed by `core_users.permissions_version`; a **cache hit takes
  no DB hit**. `scope=OrgUnitScope.REQUESTER` runs an uncached, org-bounded check
  (`core.org_units.authorize_scoped`): the actor must hold the permission globally,
  or via a scoped `core_user_roles.org_unit_id` grant whose unit is an
  ancestor-or-self of the request's org unit (walk the `parent_org_unit_id` tree).
- **Invalidation is version-keyed.** A grant/revoke bumps `permissions_version` and
  stamps it onto the target's live session records, so the change lands on their
  **next request** (no re-login) — see the RBAC admin routes below. Delegation/OIC
  windows (`core_user_roles.valid_from`/`valid_to`) are honored in the resolver and
  the cache TTL is capped at the next window edge, so an expiring grant drops
  precisely.
- **RBAC admin** (`/api/v1/rbac/*`): `GET roles` / `GET permissions` / `GET
  users/{id}/roles` (read perms); `POST users/{id}/roles` (`rbac.role.grant`) and
  `DELETE users/{id}/roles/{grant_id}` (`rbac.role.revoke`). Grants may be
  org-scoped (`org_unit_id`) and time-bounded (`valid_from`/`valid_to`, delegation).
  Grant/revoke emit `rbac.role.granted` / `rbac.role.revoked` hash-chain events.
- **Maker-checker / SoD** (`core.maker_checker.assert_segregation`): a reusable
  no-self-approval / distinct-approver-per-DV-Box check (COA 92-389, NGICS) the
  approval flow calls; the DB-level constraint lands with the approval table
  (Stage C).
- **Auditor** (`/api/v1/audit/*`, COA Res. 2020-034): `GET audit/verify`
  (`audit.verify`) returns a printable HTML chain-verification report (JSON with
  `Accept: application/json`); `GET audit/records/{table}/{row_pk}` (`audit.read`)
  is the per-record timeline. The built-in `auditor` role holds only read/verify
  grants, so it is read-only on every route with no extra mechanism.
- **New error slugs** (envelope §3): `forbidden` (403 — lacks the permission),
  `segregation_of_duties` (409 — maker-checker violation), plus `unavailable`
  (503) if the permission cache / session store is missing (lifespan not run).

## §8. Attachments, provisioning, directory & the query log (Stage B / Increment 4)

- **Attachments** (`/api/v1/attachments`, `attachment.*` gates): `POST` (multipart
  `file`; validated + size-capped + stored `pending`, then a malware scan is enqueued
  after commit), `GET /{id}` (metadata), `GET /{id}/content` (streaming, auth-checked,
  serves the EXIF-stripped derivative), `DELETE /{id}` (soft delete), `GET
  /disposal-report`. **No static mounts** — downloads are always streamed through the
  permission gate. File downloads stream bytes with `Content-Type` + `Content-Disposition`
  + `X-Content-Type-Options: nosniff`. New slugs: `attachment_rejected` (422),
  `payload_too_large` (413), `attachment_not_ready` (409). The per-row `authorize`
  hook is a **holder-scoping seam** (`register_holder_authorizer`) — coarse RBAC is
  the only gate until a holder module wires it (Stage C).
- **Provisioning** (`/api/v1/users`, `user.*`): `POST` creates a login from a staff
  record (temp password + forced change; **no self-registration endpoint exists**),
  `GET` list/`{id}`, `POST /{id}/deactivate` (flips `is_active` **and** revokes every
  Redis session immediately; self + break-glass are `409`-protected), `POST
  /{id}/reactivate`. Every event is hash-chained (`user.created` / `user.deactivated`
  / `user.reactivated`); role grants reuse `/rbac/*`, password reset reuses
  `/auth/users/{id}/reset-password`.
- **Directory** (`/api/v1/directory`): `POST /import` (`staff.import`, multipart CSV
  org-units + staff → the pure, atomically-validated `core.directory.ingest` upsert),
  `GET /staff` + `/staff/{id}` (`staff.read`), `GET /org-units` (`orgunit.read`).
- **Query log** (append-only `core_query_logs`): a middleware records **one row per
  `/api/v1` request** (reads + writes, authed + anonymous), excluding `/config` +
  `OPTIONS`. It stores `module`/`resource`/`action` + ids + query-param **names** +
  status + duration — **never** request/response bodies, headers, or query **values**,
  so no SPI enters the log. Gated by `query_log_enabled`; a logging failure never
  breaks the request.
- **Person-field SPI in the audit timeline**: `GET /api/v1/audit/records/{table}/{pk}`
  renders `[redacted]` for excluded person fields (`core_staff` names/email,
  notification recipient/body/payload) **by design** — the immutable chain records the
  field name, not the value; the current value is read from the live row.
