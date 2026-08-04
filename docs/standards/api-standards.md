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
