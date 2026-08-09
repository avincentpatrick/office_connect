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

> **SPA client contract — R-2-shell (2026-07-28).** The fetch wrapper this
> section anticipated now exists: **`web/src/api/http.ts`** is the ONE path for
> every API call — it sets `X-Requested-With` on every non-safe method
> (including `POST /auth/login`), sends `credentials: "same-origin"`, and
> raises the §3 envelope as a typed `ApiError` (`status/code/message/details/
> requestId/retryAfter`), surfacing `X-Request-ID` for support.
>
> **Dev connectivity is same-origin by design — NO CORS middleware exists.**
> The Vite dev server (:5174) proxies `/api` → the app container, so the
> browser origin is always the SPA origin and the `oc_session` cookie
> (`Path=/api`, `SameSite=Lax`) plus the CSRF header work unchanged; production
> serves the built SPA from the same origin as the API (on-prem reverse proxy).
> This supersedes the earlier "+ CORS" planning note: a `CORS_ALLOW_ORIGINS`
> knob is a **recorded deferral** until a genuine cross-origin consumer exists
> — do not add CORS "just in case".

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

## §9. Module routers & the feature-flag surface gate (Stage C R-2-wizard, 2026-07-30)

The reimbursement wizard shipped the codebase's **first module router** — these
are now the binding conventions for every module HTTP surface:

- **Mounting** — a module router lives in
  `office_connect/modules/<module>/api/` and self-prefixes its full path
  (`APIRouter(prefix="/api/v1/<area>")`). It is mounted from
  **`office_connect/main.py`** (the composition root), never from
  `core/api/router.py`: import-linter's "core never imports modules" contract
  forbids the latter. App → module imports are legal (same reasoning as the
  ops import in the lifespan).
- **Feature-flag gate → 404** — the whole module router declares
  `dependencies=[Depends(require_feature("<flag key>"))]`
  (`core/auth/dependencies.py`; core-legal — it takes a plain string).
  Flag OFF or missing → `404 not_found` on every route, **before** auth, so an
  OFF module is indistinguishable from absent (fail-safe OFF, rule of the
  house). Two ordering facts, both pinned by tests: the CSRF middleware wall
  fires even earlier (a header-less POST 403s `csrf_failed` with the flag
  OFF), and with the flag ON the normal 401/403 gates take over.
  The gate reads the DB per request (indexed single-row select); a
  Redis-cached variant is a recorded deferral. **The one exemption is §9a.**
- **Read scoping is the module's job** — coarse `require_permission` cannot
  express "owner sees own; scoped roles see their unit" when a role's grant is
  global (the `staff` role's `reimb.claim.read` is). Reimbursement's rule
  (`api/deps.py::can_read_claim`): owner, or `authorize_scoped` on any of the
  module's gate permissions against the claim's org unit. Claims are NOT
  bureau-public (spec §3.2) — future module list/read endpoints must make the
  same server-side choice explicitly.
- **Money on the wire** = 2-dp strings, server-computed (§2 reaffirmed): the
  wizard's money step PATCHes inputs and calls `POST …/compute`, which returns
  the recomputed claim — the client never does arithmetic.
- **Recorded deferrals** — the pagination envelope stays Stage D (`/my-work`
  hard-caps at 100 rows; `/regions` is a bounded reference list); an
  `Idempotency-Key` request-header convention is deferred (the claim-row
  `FOR UPDATE` lock + 409s + the engine's server-derived keys already make
  double-submit burn exactly one reference number).

## §9a. Un-gated action endpoints + the workflow action convention (R-4-screens, 2026-08-03)

> **The flag gates the module's surface; it never gates a decision on an
> instance already in the chain.**

This is the resolution of the §9 caveat, and it binds every module that runs on
the workflow engine.

- **Why an exemption exists at all** — `execute_action` never reads the feature
  flag (workflow-standards §9): the engine will always finish work it started.
  If the HTTP surface 404'd everything, switching a module OFF would strand
  every in-flight item at whatever gate it was sitting on. The flag must stop
  new work, not trap existing work.
- **Scope of the exemption: the action POSTs, and nothing else.** Reimbursement
  un-gates exactly `POST /claims/{id}/approve` and `POST /claims/{id}/return`.
  Reads and wizard writes stay gated so an OFF module still looks absent to a
  browser (fail-safe OFF survives intact), and `/submit` needs no exemption —
  `start_instance` already refuses a new instance flag-OFF. `/submit`'s
  *resubmit* branch stays gated too: resubmit is claimant-editing work, and it
  is meaningless without the wizard behind it. **Residual, accepted:** flag-OFF
  the approver *UI* is unreachable even though the POST answers. The guarantee
  is that the engine and its HTTP mirror never refuse an in-flight transition —
  not that the SPA stays up for a module someone deliberately switched off.
- **How to implement it** — a **second top-level router**
  (`modules/<module>/api/actions.py`, self-prefixed, no `dependencies=`),
  mounted from `main.py` alongside the gated one. It cannot be an
  `include_router` under the gated router: FastAPI applies a router's
  `dependencies` to everything included beneath it. Pinned by
  `tests/test_reimb_api_flag_gate.py` — with the flag OFF the action routes must
  answer 401/403/409, and specifically must never return the gate's bare
  `not_found`.
- **Per-action routes, not a verb envelope** — `POST …/{id}/approve` and
  `POST …/{id}/return`, matching the existing `/submit` and `/cancel`. Each
  action gets its own request schema, so a rule like "≥1 return reason" fails as
  a **field-anchored 422** (`loc: ["body","reason_ids"]`) that the FE's
  422→field mapper attaches to the control that is wrong. A single
  `POST /actions` with a `{action}` discriminator cannot do that without a
  union, and buys nothing.
- **Route permission is deliberately coarse** — a chain's gates carry
  *different* permissions (`reimb.claim.approve` / `.review` / `.fms_update`),
  so no single route dependency can express the real rule. Declare the module's
  read permission and let the engine's `resolve_authority` be the authorization
  of record (403 `workflow_not_authorized`). Same reasoning as `can_read_claim`
  above: coarse at the route, exact in the service.
- **CAS on the wire** — a read that exposes an action set also exposes
  `row_version` (from `core_workflow_instances`); the client echoes it back as
  `expected_version` and a moved claim 409s `stale_workflow_version` instead of
  acting on a stale screen (workflow-standards §4). Null before submit.
- **The action set travels with the record, not beside it** — reimbursement
  embeds `available_actions` in `ClaimDetail` rather than serving
  `GET …/available-actions`. Every mutation already returns the full record, so
  the buttons, the CAS token and the data they describe refresh in one response
  with no second query to invalidate and no window where they disagree.
  Additive within v1 (§1), so existing clients are unaffected.

## §9b. A module owns the upload endpoint for its own entity (R-3, 2026-08-03)

> **The module that owns the entity owns its upload route. It reuses
> `core.attachments` for every byte and never touches a storage driver.**

Core ships `POST /api/v1/attachments` (core-service #2) with a generic
`holder_kind`/`holder_id` pair. Reimbursement still declares its own
`POST /claims/{id}/checklist/{catalog_id}/attachments` on the gated module
router. The reasoning generalizes to DTWIS/QMS/Supply:

- **Atomicity.** Attaching evidence is upload + join row + display mirror +
  checklist status recompute in ONE transaction. Split across two HTTP calls
  there is a window in which a stored, scanned, permission-gated file exists
  with no owner — and if the second call fails, an orphan nobody can find.
- **Authorization.** The real rule is *"may this actor edit THIS claim's
  packet"* — owner, and only while the claim is claimant-held. A coarse
  `attachment.upload` permission cannot express that. Same argument §9 makes for
  read scoping, applied to writes: coarse at the route, exact in the service.
- **What stays in core, always.** Validation, magic-byte sniffing, the type
  allowlist, hashing, the content-addressed store, the ClamAV scan and the
  image re-encode. A module calls `core.attachments.upload_attachment` and keeps
  a thin join row for what only it knows (which entity, which checklist item,
  custody, retention class). Rule 10 — never a second pipeline.
- **Downloads stay on the core route.** `GET /api/v1/attachments/{id}/content`
  is the one download path; a module scopes it by registering a holder
  authorizer (`core.attachments.authz.register_holder_authorizer`), which needs
  **zero core router change**. Fail-closed: anything the hook raises denies.
- **Accepted residual** — that core route is not behind `require_feature`, so
  with a module flag OFF a permitted user can still fetch a file already
  uploaded. Consistent with §9a's doctrine (the flag gates the module's
  surface, not core services), and recorded rather than papered over.
- **Reuse the module's existing write permission** (`reimb.claim.create`) rather
  than minting one per surface: editing the packet IS editing the claim, exactly
  like `PATCH /claims/{id}`. The size cap and its deterministic 413 mirror the
  core route's, so a claimant hitting the limit gets the same answer either way.

## §9c. Generated documents: the module asks, core renders and serves (R-5, 2026-08-04)

> **A module owns the endpoint that ASKS for its paperwork. Core owns the
> rendering, the storage and the download. Nothing renders in a request path.**

Core-service #8 (`core/documents/`) turns a registered template plus a context
into PDF bytes; core-service #3 freezes each result as an immutable snapshot.
Reimbursement declares `POST /claims/{id}/documents/generate` on its **gated**
router. The conventions this establishes:

- **202, never 200.** WeasyPrint takes seconds and needs native libraries, so it
  runs in the Celery worker (master-plan §1.1 #8 is explicit that it never runs
  in the request path). The handler therefore *cannot* return the finished
  documents. It returns the packet as it stands plus a `queued` boolean, and the
  client polls the resource that will change. A generate endpoint that returned
  200 with documents would be an endpoint that had rendered inline.
- **`queued: false` is not an error.** No worker wired means the render did not
  start; that is a fact the UI shows as a non-blocking notice, not a 5xx and not
  a spinner that cannot resolve (spec §19.12 — "the claim saves anyway,
  generation queues, the user sees a notice"). Never fail a save because a
  downstream renderer is unavailable.
- **Idempotent by fingerprint, so the endpoint is safe to spam.** Generation
  compares a hash of the render context against the live snapshot's and skips
  identical work. A double-click, a retry and a beat sweep all cost nothing.
- **Gated, not exempt.** §9a's exemption is for *decisions on an in-flight
  workflow instance*. Producing paperwork is not a decision, so the generate
  route sits behind `require_feature` like every other module surface.
- **Provenance decides disposition — server-side, never a parameter.** The one
  download route (§9b) serves `Content-Disposition: inline` **only** when
  `core_attachments.origin = 'generated'` and the sniffed type is
  `application/pdf`; everything a human uploaded stays `attachment` forever.
  Preview needs `inline`, and `inline` needs a rule about what may be served
  that way: an uploaded PDF can embed JavaScript, so rendering one in the app's
  own origin is the stored-XSS pattern. Our own renderer's output carries no
  such risk. `X-Content-Type-Options: nosniff` stays on both paths, and no query
  parameter can influence the choice.
  - **This amends §9b's "zero core router change".** R-3 could scope downloads
    without touching core; R-5 could not, because *how* a blob is served is a
    property of the blob, which is core's to know. The change is one derived
    header, with the rule expressed as a pure function of the stored row
    (`core/attachments/service.py::_disposition`) rather than as a route option.
- **Generated bytes are born `clean`.** They are produced in-process from
  autoescaped templates and never leave it, so there is no untrusted input to
  scan. Leaving them `pending` would be worse than pointless: in production
  `NullScanner` returns `error`, so a tenant without ClamAV could never open a
  document the system generated for them — a missing optional dependency turned
  into a permanently broken packet by the fail-closed download gate. The type
  allowlist still applies, so a renderer bug that emitted HTML is still refused.
  - **Corollary, added R-5-packet:** a generated document may only ever contain
    bytes this platform authored. A combined packet therefore **indexes** the
    claimant's uploads (filename + SHA-256) instead of merging them. Merging one
    in would make the whole file untrusted while still carrying `origin =
    'generated'`, and the `inline` disposition above would then be serving a
    claimant's bytes in our own origin — the exact thing this rule prevents.
- **A generated document prints only facts the platform RECORDED, and names what
  it recorded rather than what it inferred** (added R-6-liq-settle). Two edges:
  - Where a workflow records the person who **entered** an external fact, the
    document may name the **recorder** — never the external signatory. GAM App
    44's certification C is cleared by the Admin Officer typing what the Head of
    the Accounting Unit signed on paper; printing that officer in box C would
    name the wrong person in a COA certification, which is worse than a blank
    box. A recorded fact ABOUT a certification goes in a note beneath the
    signature line, never on it — a name over an empty rule reads as a completed
    certification to whoever is holding the page.
  - A fact the platform does not have yet prints as a **blank rule plus a note
    saying so**, never as a zero and never as a hidden section. `₱0.00` on a
    refund line is indistinguishable from "nothing was refundable", and a hidden
    section is how a reader never learns money is owed.
  - Recording that fact later is what makes the document re-render, and that is
    free: the fingerprint check means an unchanged document costs nothing, and
    the earlier copy is **superseded, not voided** — it was reissued, not
    invalidated, and `voided` would tell an auditor something untrue.

### 9d. Two doors onto one endpoint (Stage C R-5-packet, 2026-08-04)

`POST /reimbursement/claims/{id}/documents/generate` accepts **either** the owner
while the claim is still editable **or** an actor holding a scoped
`reimb.claim.review`/`approve` grant on the claim's org unit. The pattern, for
any endpoint whose audience genuinely widens after a workflow transition:

- **The route gate stays coarse and the real rule lives in the service** (§9's
  standing doctrine). The gate relaxed from `reimb.claim.create` to
  `reimb.claim.read` because an approver is not a creator; that is a *narrowing*
  of what the route asserts, not a widening of who gets in.
- **Never widen to "anyone who may read it."** Read grants are global on the
  `staff` role, so a read-derived rule would expose the endpoint to the whole
  bureau. Name the gates that may act.
- **The second door re-raises the FIRST door's error.** A caller refused by both
  must not be able to tell from the message which door they failed, or the
  response becomes an existence-and-status oracle for records they cannot see.
- **Ask why the second door is needed before adding one.** Here it is because
  `NEXT_ACTION[admin_review]` instructs the holder to print a packet: an
  instruction the UI cannot carry out, with no way to ask, is the dead end
  §9.1 principle 4 forbids. An endpoint with no such instruction behind it does
  not need a second door.

---

## §9e. A second resource under a module router (R-6-clock, 2026-08-04)

`reimb_cash_advances` is the module's second first-class resource, and the first
one that is **not** the claim. It confirms §9's split rather than amending it,
but three things are worth stating because they were decided rather than
inherited:

- **New work sits on the GATED router.** The four cash-advance routes are behind
  `require_feature`, so flag-OFF they 404 like the rest of the module surface.
  §9a's un-gated exemption is deliberately *not* extended to them: that
  exemption exists so the flag can never refuse a decision on an instance
  already in the chain (workflow-standards §9). **Starting a clock is not
  finishing one.** The test for whether a route earns the exemption is whether
  refusing it would strand in-flight work, not whether it is important.

- **A second resource needs its own read rule; it may not borrow the first's.**
  `can_read_cash_advance` is a sibling of `can_read_claim`, not a call into it.
  The two answer different questions about different rows, and the tempting
  shortcut — "anyone who may read the claim may read its advance" — is wrong in
  both directions: the `staff` role's read grant is GLOBAL (spec §3.2), so it
  would publish every colleague's DV numbers and peso amounts, and an advance
  can exist with no claim linked at all.

- **A derived value that decides money or deadlines ships ON the record,
  computed server-side.** `days_remaining` and `deadline_state` ride every
  cash-advance response for the same reason `sla_state` does (§9a) and money
  does (§2): a browser with a wrong clock, or one running outside Manila, must
  not be able to tell a traveller they still have time to liquidate. The
  corollary is that such fields are absent from the REQUEST schema — a client
  that could post a deadline could post one the regulation never gave.

- **Copy that states a legal consequence comes from config, with no code-side
  fallback.** `liquidation.overdue_note` reaches the client only once it applies.
  A missing row renders nothing rather than a developer's paraphrase, because a
  paraphrase of a COA consequence is indistinguishable from the real thing.

## §9f. The first LIST endpoint: a list may not borrow a row's read rule (R-7-queue, 2026-08-04)

Every read path before `GET /reimbursement/claims` answered **"may this actor read
THIS record"** — one row, one `authorize_scoped`. A list asks the question
backwards, **"which records may this actor see"**, and the two are not the same
rule wearing different clothes. Four things follow, and the first is a security
rule, not a style note.

- **A list may not be keyed on a permission that is granted globally to
  everyone.** `reimb.claim.read` is held *globally* by the `staff` role, because a
  traveller must be able to read their own claim from anywhere in the org tree.
  A list gated on it therefore returns **every claim in the agency to every
  employee** — destinations, purposes, peso totals. The queue is scoped on the
  **oversight** permissions instead (`reimb.claim.review` / `.fms_update` /
  `.approve`), which only an approver or the Admin Officer holds. The route gate
  stays coarse and unchanged (§9/§9a); what is different is that the service's
  exact rule uses a *different permission set*, not a narrowing of the route's.
  **The test to apply before writing any list:** if the permission at the route
  is one an ordinary user holds so they can see their own data, it cannot also
  decide whose data they see.

- **Refuse, do not return an empty list.** An actor who oversees nobody gets
  `403`, because `200 []` says *"there is no work"* — a claim about the world that
  is false — where the truth is *"this surface is not yours"*. The refusal names
  the surface that DOES answer their question (My Work), per §9.1 principle 4.
  Note this is the one place the "same slug, no owner-vs-scope leak" rule does
  **not** apply: a list request names no record, so there is nothing to leak, and
  a borrowed `not_claim_owner` ("only the claimant may do this") would be a
  plainly wrong sentence.

- **Scope resolution for a set needs the SUBTREE, in one query.** A scoped grant
  covers its unit and everything below it. Per-row that is
  `ancestors_or_self` (walk up from the record); for a list it is
  `core.org_units.descendants_or_self` (the grants' closure, one recursive CTE),
  added in core beside its sibling — a module growing its own org-tree SQL is
  the duplication rule 10 exists to stop. Rows whose org unit cannot be
  determined are visible to a **global** holder only: "I could not place this" is
  not a reason to show it to someone scoped.

- **State what the page is hiding.** A list that caps or pages says so on the
  wire (`total` is the count *before* `limit`/`offset`; the queue also returns
  the follow-up threshold it applied). A short list that looks complete is worse
  than a number — and where a filter must bound its own scan, the bound is
  chosen so truncation can only drop rows the filter would have excluded anyway,
  and it logs when the cap is actually reached.

**Deferred, deliberately:** the pagination *envelope* is still a Stage-D item;
until then lists are `?limit=&offset=` with a server-side ceiling, following
`core/api/directory.py`.

## §9g. A collection VIEW is a sibling path, and an aggregate is still money (R-7-board, 2026-08-05)

`GET /reimbursement/board` is the first endpoint that is neither a row nor a
list, but a **view over a set** — three columns, each with a count, a peso total
and a short page of rows. Four things came out of building it, and the first is
the one that would have cost an afternoon.

- **A literal segment under a sibling router's `{id}` route is decided by
  include order, which is not a contract.** `GET /claims/board` looks obviously
  right and does not work: `claims.router` is included before `queue.router` and
  declares `GET /claims/{claim_id}`, FastAPI matches routes in registration
  order, and the path parameter carries no convertor — so the request is read as
  a claim whose id is `"board"` and 422s on validation. Making it work means
  either reordering `include_router` calls or typing every `{claim_id:int}` in
  six files; the first makes correctness depend on a line order nothing declares
  and a future alphabetization would silently break, and the second changes the
  declared path strings that feed OpenAPI. **Give the view its own segment.**
  `GET /board` is order-independent by construction, and it is honest: the board
  is its own read resource (§9e), not a claim. Pin BOTH halves in a test — the
  new path answers, and the tempting one 422s — so the reason outlives the
  decision.

- **A board is a LIST with headers, so §9f applies unchanged.** It is scoped on
  the OVERSIGHT permission set, never on the route's globally-granted
  `reimb.claim.read`, and an actor who oversees nobody is refused with the same
  403 and the same sentence rather than a second one. The rule matters *more*
  here than on a list: a leaked list gives up rows one page at a time, a leaked
  board gives up a division's whole budget in a single integer. So the scope
  clause must be asserted on the **aggregate**, not merely on the rows — cards
  filtered correctly under a header that counted the whole agency is a defect
  that looks exactly like working software.

- **A server-computed aggregate is money and crosses like money.** Same 2-dp
  string as every row-level value (§2), `"0.00"` on an empty set — never null,
  never a JSON number. And it is computed in SQL over the whole set, never in
  Python over the page that was fetched: a total summed from the visible rows
  under-reports by exactly what did not fit on screen, while looking entirely
  correct. The corollary binds the client too — a page given both `total` and
  `items` must render the server's `total` and never re-derive it, and that is
  worth a test whose fixture deliberately disagrees with itself.

- **§9f's "state what the page is hiding", second instance — and the bound rides
  the envelope.** `count` describes the whole column; `items` is capped; the cap
  itself (`card_limit`) is in the response so the "showing 20 of 137" line quotes
  the server's number rather than a literal the browser has to keep in step. The
  same applies to any window a view applies on its own initiative: this board's
  Done column covers a recent period, so `done_window_days` crosses too and the
  header qualifier is composed from it. A bound the client cannot see is a bound
  the client will eventually contradict.

**Not a filter surface.** The board takes no query parameters at all — no
`?limit=`, no status, no kind. A client-tunable cap on a board is a request to
page a board, and paging is what the list endpoint next door is for.

## §9h. An aggregate over other people's work: the scope IS the privacy boundary (R-8, 2026-08-06)

`GET /reimbursement/insights/return-reasons` is the first endpoint whose entire
purpose is **summarising other people's failures**. The board aggregates money
(§9g); this aggregates mistakes, and the difference is not one of degree — a
peso total is a fact about work, a ranked list of why packets came back is a
fact about how people perform. Build spec §11 says *"aggregates only, mirroring
the §14.7 pattern; per-person return counts are visible only to the person
themselves"*, and §14.7 is the privacy-preserving query log: ids and parameter
names, never values.

Four rules, and the first is the one that makes the rest enforceable.

- **An aggregate may span only rows the actor could already read one at a
  time.** The ranking is computed over `queue.oversight_scope`'s subtree, using
  the same `base_query` the queue and the board use — not a second predicate
  that happens to agree today. That makes the privacy claim *structural*: the
  surface cannot reveal anything the actor could not have assembled by opening
  claims by hand, so there is no new disclosure to reason about and **no
  minimum-cell suppression is applied**. (A small division's counts are indeed
  about few people; the actor already oversees exactly those people. Suppression
  would protect nobody from anybody, while making the numbers wrong.)

- **The response carries no person dimension, and there is nowhere to add
  one.** No claimant, no org unit, no claim id, no drill-down from a reason to
  the claims that cited it. The rule is about the SHAPE, not the UI: a field
  nobody renders today is a field somebody renders next quarter. Where a
  per-person figure is genuinely wanted, it belongs on that person's own
  surface — spec §11's "visible only to the person themselves" — which here is
  the claim tracker they already have.

- **The write rule may be narrower than the read rule, and must be when a write
  is tenant-wide.** Reading the ranking needs oversight of somebody; *promoting*
  a reason shows a warning to every claimant in the tenant, so it needs an
  **agency-wide** grant (`org_unit IS NULL`), not merely the permission. A
  scoped grant producing a tenant-wide effect is a scope escalation that looks
  exactly like the button working. The corollary is the R-4-screens doctrine
  unchanged: the envelope carries `can_promote` so the UI never offers a control
  certain to be refused, and the refusal names the missing grant.

- **A refusal must be true of the surface that refused.** §9f established
  "refuse, do not return an empty list"; the second half is that the sentence
  has to fit. Insights does NOT reuse the queue's `reimb_queue_not_permitted`
  ("your own claims are on My Work") — My Work answers no part of "why do
  packets come back". It gets its own slug and names the surface that *does*
  answer what this actor can legitimately ask: their own returns, with reasons,
  on their own claim tracker.

**Also settled here:** a count is never quietly a rate. `total_returns` rides
the envelope as the header's context and is documented as such; a return *rate*
needs a submissions denominator this surface does not compute (spec §13 →
Stage H). Shipping half a rate is worse than shipping none, because a
plausible-looking percentage is the number people quote.

## §9i. A cohort is a grant list, and authorization precedes state (R-9, 2026-08-05)

Two rules came out of the Stage C hardening pass. The first settles what a
"pilot" *is*; the second is a defect class the security suite found on its first
run, in code that had passed every test written for it.

### The flag says whether; the grants say for whom

Build spec §14's R-9 row asks for *"flag ON for pilot cohort only"*, and
`core_feature_flags` holds a tenant-wide boolean. The temptation is to give the
flag an org-unit dimension. **Don't.** Those are two different questions and the
platform already answers both:

- **The feature flag answers "is this module on."** One boolean, tenant-wide,
  fail-safe OFF, read before auth (§9). It is a *deployment* switch — it decides
  whether a surface exists at all, and it must stay cheap enough to evaluate on
  every request and simple enough that `/api/v1/config` can never 500 on it.
- **RBAC grants answer "for whom."** Nothing in this codebase auto-assigns a
  role — there is no default-grant path anywhere, so a user can reach a module
  only because an administrator explicitly granted them one. **The cohort is
  therefore already exactly the grant list**, scoped per org unit, time-bounded,
  revocable, and audited. A per-cohort flag column would be a second, weaker
  copy of that, and the two would drift.

The honest risk in this posture, stated so it is not discovered later: **a
cohort you cannot enumerate is a cohort you cannot verify.** One global `staff`
grant to somebody outside the pilot admits them, and nothing about that looks
wrong. So the posture ships with its control: **`ops/bootstrap.py pilot-roster`**
prints every live holder of any `reimb.*` permission with their role, scope
(`AGENCY-WIDE` spelled out, because §9h's tenant-wide write rides it) and
validity window. Run it before go-live and after any grant change. Expired
grants are excluded — the roster must match what the app would actually
authorize, not what the table records.

Pinned by `tests/test_reimb_authz_census.py`, which drives all 32 module routes
with an authenticated, grant-less user and requires 403 on every one.

### Authorization precedes state, and the reason is an oracle

**A caller must be proven entitled to a record before any message describing
that record's condition is composed.** Not "before the response" — before the
*error*.

R-9's security suite asked, for the first time, what a **stranger** gets back
from `POST /claims/{id}/submit`. The answer was
`409 reimb_claim_already_submitted` — a true, useful, correctly-worded sentence
about someone else's claim, delivered to anyone with an ordinary `staff` login.
The endpoint checked the claim's *state* before its *ownership*, which made it
an enumeration oracle over the whole agency: probe an id and learn
`404` (never issued) / `403` (yours to see, not yours to submit) /
`409` (exists, already filed). Filing volume and pipeline state, one request at
a time, from a valid login with no privilege at all.

Three things about this are worth carrying:

- **Every test passed.** All of them submitted the caller's *own* claim, which
  is the only path anyone thinks to write. The defect lives exclusively in the
  wrong-actor path, which is precisely why R-9 tests by attacker rather than by
  endpoint.
- **The rule already existed in the codebase, one file over.**
  `services/drafts.py::owned_editable_claim` orders the checks correctly and
  says why in a comment ("the 409-vs-403 distinction would otherwise hand any
  staff user an existence-plus-status oracle"). Two functions in
  `services/lifecycle.py` did not follow it. A doctrine written in one module's
  comment is not a standard — hence this section.
- **The engine cannot cover the no-instance branch.** Everything past
  `claim_action`'s guard is the workflow engine's to authorize, but the engine
  needs an *instance* to authorize against. So the one branch it can never
  reach is the one that says "there is no instance" — and that branch has to
  authorize for itself. `lifecycle.may_see_claim` is the service-layer twin of
  `api/deps.can_read_claim` that exists for exactly that (a separate function,
  not an import: `api` imports `services`, so the reverse edge would be a cycle).

**Corollary — same refusal, same slug.** A record the caller may not see must
refuse identically whether it exists in one state, another state, or not at all.
Reimbursement raises the owner-path `reimb_not_claim_owner` from every such
path, and `test_the_write_paths_reveal_nothing_about_a_claims_state` asserts a
draft, a submitted claim and a never-issued id are indistinguishable to a
stranger. `404` for a genuinely absent row is fine and leaks nothing: it says an
id was never issued, not anything about a claim somebody filed.

## §9j. Telling a client what it may do is not authorizing it (Stage D Increment 1, 2026-08-06)

`GET /auth/me` now carries a sorted `permissions: list[str]` — the caller's own
effective permission codes. That is a new *category* of payload, not just a new
field: **a response whose content is the caller's authorization state**, served so
a UI can show a person what they can actually open rather than guessing. The
landing shell is the first consumer; every future "what can I do here" surface is
the next. Four rules, and the first is a security rule.

- **A per-user payload never rides a shared-key cache.** The trap is already in
  this repository: `/api/v1/config` is Redis-cached under **one global key**
  (`oc:config:v1`, §9-era), and it is also the endpoint the UI already fetches at
  boot for flags and branding — so it is exactly where the next person will reach
  to put "one more thing the UI needs". One user's entitlements served from a
  tenant-wide cache entry is a cross-user leak that no test asking "does the field
  work?" would ever catch. Entitlements ride an **authenticated, per-user**
  response, cached only under a per-user key.

- **A "what may I do" payload is read through the SAME resolver the gate reads.**
  `/auth/me` and `require_permission` both call
  `core/auth/dependencies.py::effective_permission_codes`, which is the version-keyed
  cache path and nothing else. Two readers of one set eventually disagree, and the
  visible form of that disagreement is a UI offering a destination the server
  refuses — §9f's failure mode arriving through the front door instead of a list
  endpoint. Corollary: **the payload is composed from permission codes, never role
  names.** A role name in a client re-encodes a role→permission mapping that lives
  in the database and that an administrator can change with no code change (§7).

- **It is discoverability, never authorization.** No server code may branch on it,
  and **no request path may accept one**. The set travels outward only. Every route
  re-checks entitlement on every request regardless of what the client was told,
  and hiding a link remains what ui-standards §4 says it is: discoverability, with
  the server as the boundary. A client that lies about its permissions changes what
  its own screen looks like and nothing else.

- **Sort it, and the reason is not tidiness.** `PermissionCache.get_or_load`
  returns `set(json.loads(...))` on a hit and the loader's raw `set` on a miss —
  both unordered. Emitting either directly makes the response **non-deterministic
  as a function of cache warmth**: stable on a warm dev box, arbitrary in
  production, and impossible to snapshot-test. `sorted()` at the boundary.

**On reachability while a session is pending.** `/auth/me` answers under
`require_session_pending_ok`, so a user mid-password-change or mid-MFA-setup gets
this field. That is correct and deliberately not special-cased: the field describes
the caller *to* the caller, and every real action is still gated by
`require_permission`, which sits on `require_session` and refuses a pending session
outright. **Do not return `[]` while pending** — `[]` is the wire value meaning
"this person holds nothing", it drives a UI's no-access state, and returning it for
a pending session would tell the freshly-bootstrapped administrator they have no
access on their first login.

**On degradation.** The field's resolver can fail (a cold cache plus an
unreachable database). It must fail as a **503 with the standard envelope**, never
as an empty list: `[]` is a claim about the world, and a claim about somebody's
entitlements is the last one worth guessing at. Note the consequence for clients,
recorded rather than discovered: an auth surface that can now fail on a database
blip is one a client may render as "signed out" unless it distinguishes the two.

## §9k. A surface composed of sources that cannot see each other (Stage D Increment 2, 2026-08-09)

`GET /api/v1/calendar` is the first endpoint whose content comes from **more than
one module**, and the first that could not be written the obvious way. The Calendar
of Activities reads `core_activities` (core), travel claims and liquidation clocks
(reimbursement), and — as later stages ship — room bookings, document deadlines and
SPMS dates. But `oversight_scope` lives in
`modules/reimbursement/services/queue.py`, and the import-linter contracts forbid
**both** `core → modules` and `module ↔ module`. There is no import that reaches the
rule, and there was never meant to be.

So the calendar **inverts**: `core/calendar/sources.py` owns a `CalendarSource`
value type and a `register_source()` registry; each module implements its own source
(where its own scope rule is a local import); and `main.py` — the composition root
that already mounts module routers for exactly this reason — registers them. The
precedent is `core/notifications/outbox.py::register_enqueuer`, whose docstring says
the same sentence about the worker.

**This is not a workaround for the contracts. It is the shape the contracts were
protecting.** A join written in core would have hard-coded one module's placement
rule into the platform floor, and the second contributor would have had to match it
or fork it. Five rules follow.

- **Each source applies its OWN scope rule, and the rule's NAME is a required
  field.** `CalendarSource.scope_rule` is a string naming the exact predicate the
  source applies, and `register_source` **raises** on an empty one. That makes the
  §9h guarantee structural per contributor — a source can only ever return rows its
  own module already lets this actor read one at a time — and it makes the registry
  a census substrate. R-9's lesson in a third place: *absence never fails a test
  unless you make it.*

- **A source that narrows to empty is not §9f's lie; a SURFACE that does, is.** §9f
  says refuse rather than return `200 []`, because an empty list claims *"there is no
  work"*. That still binds the endpoint: no `activity.calendar.read` → 403. It does
  **not** bind a *layer*. An actor who oversees nobody legitimately owns this
  calendar — activities are tenant-wide — so their travel layer is genuinely empty,
  and the response says so in words (`bounded_note`) rather than by omission. The
  test to apply: **does the surface as a whole belong to this actor?** If yes, a
  narrowed layer is a fact about them; if no, it is a refusal wearing a list's
  clothes.

- **The feature flag moves from the route onto the source.** A core route cannot
  carry `require_feature("module.reimbursement")` — core may not know the module
  exists. So `CalendarSource.feature_flag` is checked by the dispatcher through the
  same reader `require_feature` uses, and a flag-OFF source is **absent from
  `sources[]`**, not present-and-empty. §9's "a module with its flag off is
  indistinguishable from a module that was never built", preserved at row
  granularity instead of route granularity. An empty `reimb.travel` block would
  announce a module the tenant has not bought.

- **A failing source fails the request.** No silent partial calendar, no
  "unavailable" placeholder that the page renders as a normal empty section. §9f's
  own words: a short list that looks complete is worse than a number. Loud beats
  plausible, and a calendar is a surface people plan against.

- **The window is the paging control; there is no `limit`/`offset`.** §9g already
  ruled that *"a client-tunable cap on a board is a request to page a board"*. It
  binds harder here for a reason worth stating: with per-source caps, an offset deep
  enough to pass one source's cap drops rows from the **middle** of the merged
  chronology while `total` still looks right. Move the dates, not an offset. Each
  source is capped and ordered `(date_start, ref)` so truncation can only ever drop
  the *latest* rows in the window, and the cap rides the envelope (§9g) so the page
  quotes the server's number.

**Also settled here:** `total` is the sum of the sources' pre-cap counts, and a
source's `bounded_note` is a **sentence, never a count of hidden rows**. "3 more you
cannot see" is a disclosure the actor could not have assembled by hand — it tells a
division chief how much travel a sibling division booked — and §9h is explicit that
for an aggregate the scope IS the privacy boundary. State the rule; never the
residue.

---

## §10. Security headers (Stage D closeout, 2026-08-09)

**Until this section existed the app set none.** A repo-wide search for
`Content-Security-Policy`, `X-Frame-Options`, `frame-ancestors`, `Referrer-Policy`
or HSTS returned zero hits; the only security header anywhere was
`X-Content-Type-Options: nosniff`, on the attachment download route alone. The
belief that the reverse proxy supplied the rest was unwritten, untested, and had
no config file in this repo to inspect (tech-stack §7a). Shipped as
`core/api/security_headers.py` with `tests/test_security_headers.py`, because the
app is the part the suite can pin — the proxy is deployment-time and
post-development.

### 10.1 The app's headers

Set by `SecurityHeadersMiddleware` on **every** response. It is registered outside
`CSRFMiddleware` (nesting: `request_id → security-headers → CSRF → auth-principal →
query-log → route`), so a 403 from CSRF and a 401 from a protected route carry the
same headers a 200 does. A header present only on the happy path is one a scanner
reports as passing and an attacker reports as absent.

| Header | Value |
|---|---|
| `Content-Security-Policy` | the API policy, or the HTML policy on the paths in 10.2 |
| `X-Frame-Options` | `SAMEORIGIN` — **never `DENY`** (10.3) |
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | every unused feature denied; `fullscreen=(self)` |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains`, only when enabled |

**Only HSTS is configurable**, and only because it is the one header that breaks
local http dev — a browser that sees it once refuses plain http to that host for a
year, and `localhost` is shared with every other project on the machine.
`HSTS_ENABLED` unset resolves from `app_env` exactly as `SESSION_COOKIE_SECURE`
does, and a test asserts the two agree: both answer the same question (*is this
deployment reachable over https?*), so they must never disagree. Everything else
is a module constant with no knob, on purpose.

### 10.2 Two policies, because the app serves two kinds of thing

**The API policy** — almost every response, and correct rather than merely safe
for JSON and streamed PDFs: they should load nothing, frame nothing, submit nowhere.

```
default-src 'none'; frame-ancestors 'self'; base-uri 'none'; form-action 'none'
```

**The HTML policy** — the *only* three HTML surfaces this app serves: `/docs`,
`/redoc` and `GET /api/v1/audit/verify`. Swagger UI and ReDoc boot from an inline
`<script>` and fetch assets from jsDelivr; the audit report renders an inline
`<style>` block. Matched on **exact path**, never a prefix, so `/docs` cannot
relax a `/docs-*` route a later stage adds.

```
default-src 'none'; frame-ancestors 'self'; base-uri 'none'; form-action 'none';
script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net;
style-src  'self' 'unsafe-inline' https://cdn.jsdelivr.net;
img-src 'self' data: https://fastapi.tiangolo.com; font-src 'self' data:
```

Naming the loose policy and scoping it beats weakening one policy until it fits
the loosest surface: the cost stays visible and stays small. A nonce is not an
option for either — the inline script is FastAPI's own, emitted inside
`get_swagger_ui_html` where no per-request value can be threaded.

### 10.3 ⚠ `frame-ancestors` is `'self'`, and that is not a compromise

`X-Frame-Options: DENY` and `frame-ancestors 'none'` both look like the stricter
answer, and both blank the claim-packet preview in production while every test
still passes. `PacketPreview.tsx` embeds the generated packet in an `<iframe>`
served from **this origin** by `/api/v1/attachments/{id}/content`.

tech-stack §7a named `frame-src 'self'` as the fix. That is only half of it, and
the wrong half for this layer: **`frame-src` binds the *embedding* document** —
the SPA, which FastAPI does not serve — while **`frame-ancestors` binds the
*embedded* PDF**, which it does. Only the second was ever in this middleware's
power to get wrong. Pinned on the real response in `test_reimb_packet_api.py`,
not just in the header module's own tests.

### 10.4 The policy the reverse proxy owes, written down

**FastAPI never serves the SPA document** — Vite does in dev, the reverse proxy
does in production (§6). So `script-src` and `style-src` above govern only the
three surfaces in 10.2, and the SPA's own policy is a **deployment obligation this
repo cannot test**. It is recorded here so it stops being folklore; the proxy
config itself lands with the Stage I hardening work.

The proxy must serve, with `index.html`:

```
default-src 'self'; frame-ancestors 'self'; base-uri 'none'; object-src 'none';
form-action 'self'; img-src 'self' data:; font-src 'self' data:;
script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'
```

Two clauses are load-bearing and must not be tightened without reading this:

- **`style-src 'unsafe-inline'` is required by tenant theming, and a nonce cannot
  replace it.** `injectTokens()` writes the `--oc-*` custom properties via
  `document.documentElement.style.setProperty` (ui-standards §7) — an inline style
  **attribute**, governed by `style-src-attr`, and nonces only ever apply to
  `<style>` *elements*. The narrower alternative, if the cost is ever judged too
  high, is `style-src-elem 'self'` + `style-src-attr 'unsafe-inline'`.
- **`frame-src 'self'`** (inherited here from `default-src 'self'`) is what lets
  the SPA embed the packet PDF — the embedding half of 10.3.

`script-src` needs no `'unsafe-inline'`: `web/index.html` carries exactly one
external module script and zero inline script or style. Vite's dev server injects
`<style>` elements and eval-flavoured transforms, but it serves its own document
and is never the production path — do not widen the production policy to match dev.
