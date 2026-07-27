# Office-Connect — Progress Tracker

## ▶ RESUME *(copy this one line to start the next session)*

> **Resume Office-Connect — Stage C: Reimbursement vertical + the shared core workflow engine + the first React/Vite/Tailwind shell (the first user-facing module on the Stage A/B foundation floor).**

That one line is all you paste. Per the start-of-session ritual I read the
*Current Status* + *Next Session Prompt* below (and the cited module docs) to
expand it into the full task and confirm with you before starting.

## ▶ CURRENT STATUS *(overwrite each session)*

- **Phase:** **Stage B (Phase 2) COMPLETE** — Increments **B1 ✅ + B2 ✅ + B3 ✅ +
  B4 ✅**; **phase-2 QA gate PASSED** (pytest 286/286, lint-imports 3/3, migration
  chain `0001→0011` idempotent + reversible). Phase 0 / Stage A remains complete +
  pushed (tag `phase-0-complete`). **Migration head now `0011`** (B4's one migration:
  `core_notification_preferences` + the `suppressed` status). **PUSHED** — the first
  Stage B push landed: `origin/master` = `b3d150c` (B1–B4) + annotated tag
  `phase-2-complete` (credential `avincentpatrick` confirmed). **Next: Stage C —
  Reimbursement vertical + core workflow engine + first React shell.** Master Plan
  v1 in force.
- **Last session:** #10 — 2026-07-27 — **Stage B Increment 4 (wire seams + directory
  + compliance + phase-2 gate)**. Closed the three deferred shared-service seams +
  the two Stage-B compliance gates. **Authed attachments router** (`/api/v1/attachments`,
  `attachment.*` gates, per-upload scan enqueue after commit + holder-auth seam,
  streaming EXIF-stripped download). **Notification recipient/prefs** —
  `recipient_user_id → email` resolution + `core_notification_preferences` opt-out
  (security-class bypass; `suppressed` status). **CSS-IS directory ingestion** — pure
  atomic idempotent CSV upsert (`core/directory/ingest.py`) via `POST
  /directory/import` + `bootstrap ingest-directory`, now the single path
  `load-fixtures` uses. **Admin provisioning** (`/api/v1/users`) — create-from-staff
  (temp password, no self-registration) + deactivate (revokes all sessions) /
  reactivate, all audited. **Query-log middleware** — one `core_query_logs` row per
  `/api/v1` request (ids/param-names only, no SPI). **Person-field SPI redaction** —
  `core_staff` names/email + notification recipient/body/payload withheld from the
  chain. **Stage-B PIA** + processing-register row. Adds `python-multipart`.
  **Verified: pytest 286/286 (+48), lint-imports 3/3, migration `0011`.**
- **Decisions this session (user-confirmed at kickoff):** notification prefs = a
  dedicated `core_notification_preferences` table (migration `0011`) + `suppressed`
  status, security/transactional bypass; person-field SPI = direct identifiers only
  (`core_staff` names/email + notification values; **keep** `core_users.email`,
  `employee_no`, position/plantilla/status); query-log scope = all `/api/v1` requests
  (reads + writes, incl. anonymous) minus `/config` + OPTIONS; phase-2 push = prepare
  then **pause** before `git push`/tag (D4); CSS-IS ingestion = build the mechanism,
  run on synthetic fixtures (real feed not in workspace); attachments = coarse RBAC +
  a Stage-C holder-scoping seam. See `docs/modules/foundation.md` §7 (B4).
- **Blockers / waiting on user:** none — Stage B is complete + pushed. *(Dev note: B4
  added `python-multipart` → the app/worker image was rebuilt; migration head is now
  `0011`.)*

## ▶ NEXT SESSION PROMPT *(rule 3 — the full brief I expand the RESUME line into)*

```text
Context: Stage A (Phase 0) + Stage B (Phase 2) are COMPLETE and the foundation floor
is finished. Available to build on: identity split (core_staff directory + core_users
logins) + admin provisioning (/api/v1/users, no self-registration); auth (cookie Redis
sessions db 4, Argon2id, NIST policy, throttle, two-step TOTP MFA, break-glass, CSRF);
RBAC on permission STRINGS — require_permission(perm, scope=GLOBAL|REQUESTER) with
org-unit scoping (core/org_units.py ancestry) + delegation windows + the reusable
maker-checker helper (core/maker_checker.py, 409 segregation_of_duties; DB-level
constraint deferred to here); hash-chained audit + read-only auditor report + query
log + person-field SPI redaction; the shared services — attachments (core/attachments,
HTTP router at /api/v1/attachments with a holder-scoping seam register_holder_authorizer
keyed on holder_kind), notifications (send_notification + prefs + recipient resolution),
directory ingest, storage/email drivers, notification outbox; reference data (UACS/PAP
+ object codes, activity tags, holidays + the pure workdays engine, compliance
deadlines), the seed framework, and the design-token contract served at /api/v1/config
(tokens present even under the DB fail-safe). reimb.claim.create/read/submit/approve
permission strings are already seeded (placeholder, unwired). Migration head 0011.
pytest 286/286, lint-imports 3/3. Phase-2 pushed at tag phase-2-complete.
Read CLAUDE.md, then docs/modules/reimbursement.md (full plan + delta register: EO 77
3-cluster DTE, COA 2023-004, GAM form numbers, CA hard-block), master-plan.md §1
(core-services registry + connectedness contract — the ONE shared core workflow engine
is built here at R-4 and supersedes any module-internal approach; Rule 10) + §2 Stage C
(R-0…R-9) + §3 (statutory calendar), docs/standards/ui-standards.md (component inventory
+ layout templates + GOV.UK task-list + tokens) and workflow/database standards, and
the cited docs/research digests.
Task: Begin Stage C — the Local Travel Reimbursement vertical, the shared core workflow
engine, and the FIRST React/Vite/Tailwind shell + component library (the first
user-facing module). This is a multi-increment stage (R-0…R-9): confirm the increment
sequencing at kickoff. Likely first increments: (R-0) the React/Vite/Tailwind shell +
component library wired to /api/v1/config tokens + the auth/session flow; (R-4 core)
the shared workflow engine (states, transitions, approval routing via RBAC org-scope +
maker-checker) as a core service other modules consume — NOT module-internal; then the
reimbursement claim schema + forms + DV/attachment/workflow wiring on top. Consume the
existing shared services (Rule 10 — check the registry before adding a table/service);
wire the attachments holder authorizer for reimb_claim; emit notification events (don't
build delivery). Everything auditable + soft-deleted + connected (master-plan §1
"everything is connected"). Money server-computed, UI displays.
Acceptance (per-increment, confirm at kickoff): the React shell runs against the live
API with the token/component/layout system (Rule 1); the shared workflow engine drives
a claim through submit → review → approve with maker-checker + org-scoped routing and a
full audit trail; a reimbursement claim can be created/submitted/approved end-to-end
with attachments + notifications; pytest green; lint-imports 3/3 (modules import core,
never each other); per-increment docs + PROGRESS + CHANGELOG updated; commit per session.
Open questions for the user (confirm at kickoff): (a) the R-0…R-9 increment sequencing
+ where the React shell lands vs the workflow engine first; (b) frontend tooling/pins
(React 18 + Vite + Tailwind + the component-library choice) since this is the first FE
code; (c) scope of the first vertical slice (which reimbursement path/forms to wire
first — the EO 77 3-cluster DTE local-travel path).
```

---

## Stage tracker *(rule 4 — commit per session, push per phase/stage gate)*

Stages per `docs/master-plan.md` §2 (old phase numbers kept for traceability).

| Stage | Old # | Scope | Status | Sessions | QA gate | Pushed (tag / date) |
|---|---|---|---|---|---|---|
| A | 0 (inc 1–4) | Foundation: spine ✅, ops ✅, integrations ✅, spine amendments ✅ | complete (pushed) | 1–6 | ✅ passed | `phase-0-complete` / 2026-07-23 |
| B | 2 | Identity & access: auth / RBAC / directory / delegation | complete (pushed) | 7–10 | ✅ passed | `phase-2-complete` / 2026-07-27 |
| C | R-0…R-9 | Reimbursement vertical + core workflow engine + first React shell | not started | — | — | — |
| D | 3 | Landing shell / query bar / Calendar surface / AI service | not started | — | — | — |
| E | 4–7 | DTWIS (Document Tracking & Workflow IS) | not started | — | — | — |
| F | new | QMS: controlled docs · risk registry · management review | not started | — | — | — |
| G | 1/8 | CSS-IS convergence (PG migration + React + ARTA v2023) | not started | — | — | — |
| H | 9 | Admin + Reports + Government Outputs | not started | — | — | — |
| I | 10 | Hardening / SIT / pilot gate | not started | — | — | — |
| W2-A | new | Planning & Budget (WFP/BED/BAR + PPMP/APP) | not started | — | — | — |
| W2-B | new | Supply Management | not started | — | — | — |
| W2-C | new | Performance & Deliverables (SPMS + COA findings) | not started | — | — | — |

Status values: `not started → in progress → QA → complete (pushed)`.
A stage's **Pushed** cell is filled only when its QA gate passed and the tag is
on the remote — that cell enforces the push-per-phase rule.
Governance gate (DOH / Data Privacy Act) blocks loading **real** data, not the
build; the PIA-per-module gate applies before real data in ANY environment
(master plan §3.1).

---

## Session log *(newest first)*

### Session 10 — 2026-07-27 — Stage B Increment 4 (wire seams + directory + compliance) + phase-2 gate

- **Phase(s):** 2 / Stage B (B4) — **closes Stage B** · **Commit:** `session(2026-07-27)`
  (`b3d150c`) — **pushed** to `origin/master` + annotated tag `phase-2-complete`
  (Stage B's first push; credential `avincentpatrick`).
- **Kickoff decisions (user-confirmed):** notification prefs = dedicated
  `core_notification_preferences` table (migration `0011`) + `suppressed` status,
  security/transactional bypass; person-field SPI = **direct identifiers only**
  (`core_staff` names/email + notification recipient/body/payload; **keep**
  `core_users.email` + `employee_no`/position/plantilla/status); query-log scope = all
  `/api/v1` (reads + writes, incl. anonymous) minus `/config` + OPTIONS; phase-2 push =
  **prepare then pause** (D4); CSS-IS ingestion = build the mechanism, run on synthetic
  fixtures; attachments = coarse RBAC + a Stage-C holder-scoping seam.
- **Done (one migration `0011`; the rest app-layer):**
  - **Attachments HTTP router** (`core/api/attachments.py`) — `POST /attachments`
    (multipart, size-capped chunked read → 413, magic-byte validated → 422, `pending`),
    `GET /{id}` metadata, `GET /{id}/content` (streaming, EXIF-stripped derivative,
    `nosniff`), `DELETE /{id}` (soft delete), `GET /disposal-report`; `attachment.*`
    gates seeded (staff upload/read/download · approver read/download · auditor
    read+dispose). **Per-upload scan enqueue** (`core/attachments/scan_queue.py`,
    after-commit drain; ops registers the Celery `send_task` — core stays pure; beat
    sweeper backstops). **Holder-auth seam** (`core/attachments/authz.py`,
    `register_holder_authorizer`, empty in B4). `DownloadNotReady→409`.
  - **Notification recipient/prefs** — `core/notifications/recipients.py`
    (`resolve_recipient`: `user_id→core_users.email`, staff-email fallback; opt-out via
    `core_notification_preferences`; security/transactional bypass; unresolvable →
    `suppressed`), called inside `persist_notification` (signature unchanged); `dispatch`
    treats `suppressed` as terminal. New model + migration `0011` (+ `suppressed` enum).
  - **CSS-IS directory ingestion** — pure `core/directory/ingest.py` (atomic upfront
    validation, Kahn topological org insert, tombstone restore, leave-alone absence
    policy + guarded prune shipped OFF); `POST /api/v1/directory/import` + read
    endpoints (`core/api/directory.py`); `bootstrap ingest-directory` CLI; `load-fixtures`
    refactored onto the same service (one code path).
  - **Admin provisioning** — `core/api/users.py`: `POST /users` (create-from-staff,
    temp password + forced change, no self-registration), `GET` list/`{id}`,
    `POST /{id}/deactivate` (`SessionStore.destroy_all_for_user` + `user.deactivated`
    event; self + break-glass `409`-protected), `POST /{id}/reactivate`.
  - **Query-log middleware** — `core/api/query_log_middleware.py` (innermost; own pooled
    `SessionLocal`; ids/param-names/status only, never bodies/values; `query_log_enabled`
    flag; log-and-continue on failure) wired in `main.py`.
  - **Person-field SPI redaction** — `__audit_exclude__` on `core_staff`
    (names + email) and `NotificationOutbox` (`recipient_email`/`body_text`/`payload`);
    `core_users.email` kept (login handle). No endpoint change (auditor timeline shows
    `[redacted]` by design).
  - **Stage-B PIA** (`docs/compliance/pia-stage-b-identity.md`) + processing-register
    row (NPC Advisory 2017-03). **Dep** `python-multipart==0.0.20` (image rebuilt).
- **Verified:** **pytest 286/286** (+48 across attachments-API/notification-recipients/
  directory-ingest/provisioning/query-log/spi-redaction + a bootstrap CSV-parse test),
  **lint-imports 3/3** (core never imports ops/worker/modules — the ops→core scan
  enqueuer injection is the only cross-boundary edge, and it lives in ops), migration
  chain `0001→0011` reaches head, idempotent + reversible (downgrade 0011→0010 →
  re-upgrade clean; `ADD VALUE IF NOT EXISTS 'suppressed'` is add-only). ASGI client
  tests exercise the full live stack (login + MFA + CSRF, real Postgres + Redis db 4):
  upload→scan→download with EXIF stripped, 403/422/413/409 mappings, opt-out
  suppression, deactivate revoking sessions, query-log rows with no values, and the
  redacted-yet-verifying audit chain.
- **Decisions:** see `docs/modules/foundation.md` §7 (Stage B Increment 4).
- **Docs updated:** foundation.md (§5 B4 done + §7 B4 record), api-standards.md (§5 +
  new §8), tech-stack.md (`python-multipart`), CHANGELOG.md (promoted to `0.2.0`),
  `office_connect/__init__.py` (`APP_VERSION 0.2.0`), docs/compliance/ (PIA + register),
  this file.
- **Next:** Stage C — Reimbursement vertical + core workflow engine + first React
  shell (see the Next Session Prompt).

### Session 9 — 2026-07-23 — Stage B Increment 3 (RBAC enforcement)

- **Phase(s):** 2 / Stage B (B3) · **Commit:** `session(2026-07-23)` — **local
  only** (Stage B pushes at its QA gate, tag `phase-2-complete`, after B4).
- **Kickoff decisions (user-confirmed):** delegation/OIC via
  `core_user_roles.valid_from/to` **only, no table** (resolves master-plan §2 vs
  foundation §5); maker-checker = **reusable core helper + tests now**, DB-level
  constraint deferred to Stage C (approval table doesn't exist yet); auditor report
  = **printable HTML + JSON**; permission cache = **version-keyed + boundary-aware
  TTL + in-place live-session bump, no pub/sub**. Engineering call: unscoped
  `require_permission` semantics kept unchanged (any active grant confers) — the
  global-only tightening defers to Stage C.
- **Done (no migration — identity schema complete since B1):**
  - **`core/auth/permission_cache.py`** — `PermissionCache` (injected db-4 Redis),
    key `authz:perm:{uid}:v{permissions_version}`, JSON code-set, `get_or_load`
    (loader runs only on a miss → cache hit = no DB hit), TTL capped at the next
    valid-window edge, `invalidate`.
  - **`core/auth/dependencies.py`** — `require_permission(perm, scope=GLOBAL)`
    rewired behind its frozen signature: GLOBAL = cached membership; REQUESTER =
    uncached `authorize_scoped`. New `get_permission_cache`, `load_permission_entry`
    (codes + next boundary). `effective_permissions` kept.
  - **`core/org_units.py`** — `ancestors_or_self` recursive `parent_org_unit_id`
    CTE (depth-guarded, first ancestry walker), `scoped_org_units`, `authorize_scoped`
    (global grant, or a scoped unit covering the request's subtree); `OrgUnitScope`.
  - **`core/maker_checker.py`** — `assert_segregation` (no self-approval / distinct
    DV-Box A/B/C approvers, `409 segregation_of_duties`).
  - **`core/rbac.py`** — `grant_role`/`revoke_role`: upsert/restore or soft-delete
    `core_user_roles`, bump `permissions_version`, `set_permissions_version` on live
    sessions (post-commit), emit `rbac.role.granted/revoked` chain events.
  - **`core/api/rbac.py` + `core/api/audit.py` + schemas** — RBAC admin (grant/
    revoke + role/permission/user-role reads) and auditor (`/audit/verify` printable
    HTML+JSON PASS/FAIL, `/audit/records/{table}/{pk}` timeline); routers mounted.
  - **Seams touched** — `session_store.set_permissions_version` (Lua-guarded HSET),
    `audit.append_auth_event` (+ optional `table_name`/`row_pk`), `config.py`
    (`authz_cache_backstop_seconds`), `main.py` (cache on `app.state`).
- **Verified:** **pytest 238/238** (+25 across permission-cache/org-scope/maker-
  checker/rbac-enforcement/audit-report), **lint-imports 3/3** (all new code in
  `core`, boundary held). No new dependency, no migration. The ASGI client tests
  exercise the full live stack (real middleware, Redis db 4, Postgres) — grant/
  revoke landing on the next request, org-subtree denial, auditor read-only, and a
  printable PASS report are all covered end-to-end.
- **Decisions:** see `docs/modules/foundation.md` §7 (Stage B Increment 3).
- **Docs updated:** api-standards.md (§5 + new §7 AuthZ contract), foundation.md
  (§1/§5/§7), CHANGELOG.md, this file.
- **Next:** Increment B4 — wire seams + directory + compliance + phase-2 QA gate
  (see the Next Session Prompt).

### Session 8 — 2026-07-23 — Stage B Increment 2 (authentication)

- **Phase(s):** 2 / Stage B (B2) · **Commit:** `session(2026-07-23)` — **local
  only** (Stage B pushes at its QA gate, tag `phase-2-complete`, after B4).
- **Kickoff decisions (user-confirmed):** single-tenant auth (no `tenant_id`) —
  B1 revisit note resolved; logout/session-revoke recorded as **hash-chained
  semantic rows** (`append_auth_event`) not log-only; sessions on **Redis db 4**
  (the briefed db 3 collides with GlitchTip); **researched session defaults**
  (12h absolute / 30-60min idle / cap 3). Engineering calls: force-MFA-enrollment
  (not hard block), two-step MFA, minimal DB-backed `require_permission` now,
  committed gzipped top-100k blocklist.
- **Done (no migration — identity schema complete):**
  - **`core/auth/` package** — `session_store` (Redis Hash `session:{id}` +
    per-user ZSET, opaque 256-bit id, absolute/idle TTL, cap eviction, lazy index
    prune, rotate), `policy` (pure timeout/tier math), `principal` (DB-free
    request principal), `password_policy` (NIST 12+/no-composition/no-rotation +
    NFKC + blocklist + context-word checks; recorded deviation), `throttle`
    (per-account + per-IP backoff, enumeration-parity), `mfa` (pyotp TOTP, skew,
    single-use replay guard), `verifiers` (break-glass-above-LDAP branch),
    `service` (login/MFA/logout/change-password state machine with dummy-hash
    timing parity), `middleware` (CSRF + auth-principal), `dependencies`
    (`require_session`/gates/`require_permission`/`require_reauth`).
  - **`core/api/`** — `auth.py` (login/logout/me/password.change/mfa.enroll/
    confirm/verify/own+admin session mgmt/admin reset; cookie set/clear),
    `errors.py` (first structured error-envelope handlers + `APIError`),
    `schemas/auth.py` (first Pydantic wire models); router mounts `auth`.
  - **Wiring** — `config.py` (core-local `redis_db_url` twin + session/cookie/
    throttle/MFA settings + resolver properties), `main.py` (session-Redis client +
    `SessionStore` on `app.state`, CSRF + auth middleware, `register_error_handlers`),
    `db.py` (`get_session` injects `actor_id` from `request.state.user`),
    `audit.py` (`append_auth_event` — hash-chained `action=insert` `core_sessions`
    row within the CHECK, forbidden-key guard). `.env.example` auth block.
  - **Blocklist** — vendored SecLists `Pwdb_top-100000.txt` gzipped
    (`core/security/blocklists/`, ~432 KB, provenance README, `.gitattributes`
    binary+vendored), lazy `frozenset`. **Dep**: `pyotp==2.9.0`.
- **Verified:** **pytest 213/213** (was 155; +58 across policy/blocklist/mfa/
  throttle/session-store/login-flow/mfa-flow/password-change/audit-events/csrf/
  redis-config), **lint-imports 3/3** (the `core ↛ ops` boundary held via the
  core-local URL helper); live curl walkthrough — login sets an HttpOnly cookie,
  wrong-vs-unknown are byte-identical 401s, 5 fails → 429, logout destroys the
  server record, MFA two-step, password-change revokes other sessions; the login
  `last_login_at` UPDATE carries the real `actor_id`, logout/revoke append valid
  chain rows with no credential, `verify_chain` intact.
- **Decisions:** see `docs/modules/foundation.md` §7 (Stage B Increment 2).
- **Docs updated:** foundation.md (§1/§5/§7/§8a), api-standards.md (§2/§5 + new
  §6 session/CSRF contract), tech-stack.md (pyotp + db-4 map + vendored blocklist),
  requirements.txt, CHANGELOG.md, `.env.example`, this file.
- **Next:** Increment B3 — RBAC enforcement (see the Next Session Prompt).

### Session 7 — 2026-07-23 — Stage B Increment 1 (identity schema + deferred-FK closure)

- **Phase(s):** 2 / Stage B (B1) · **Commit:** `session(2026-07-23)` — **local
  only** (Stage B pushes at its QA gate, tag `phase-2-complete`, after B4).
- **Kickoff decisions (user-confirmed):** identity = **split** (`core_staff`
  directory + `core_users` auth); directory seed **decoupled from CSS-IS**
  (separate system, inbound feed later; synthetic dev fixtures now); audit-payload
  SPI = **IDs + field names only** (credential subset executed now); scope =
  detail B1, roadmap B2–B4.
- **Done (migrations 0009–0010):**
  - **Identity tables** — self-ref `core_org_units` (office/division/section/unit);
    `core_staff` (plantilla directory, superset); `core_users` (auth,
    nullable `staff_id` FK, MFA columns pre-built for B2); `core_roles`,
    `core_permissions`, `core_role_permissions`; org-scoped `core_user_roles`
    (**PG16 `NULLS NOT DISTINCT`** grant uniqueness + `valid_from/to` for B3);
    append-only `core_login_attempts` (anti-enumeration, REVOKE UPDATE).
  - **Deferred-FK closure (`0010`)** — the single "core_users referential
    closure": `created_by`/`updated_by`/`deleted_by` (mixin, all 18 business/
    lookup tables) + bespoke `actor_id`/`recipient_user_id`/`disposed_by`/
    `generated_by`/log `created_by` → `core_users`; `division_id`/`section_id` →
    `core_org_units`; `tenant_id` → `core_tenant_configs`. Sanctioned no-FK
    (`core_attachments.holder_*`, `core_audit_logs.row_pk`) left alone. All
    pre-existing `*_by` are NULL → validated with no backfill.
  - **Credential redaction** (pulled forward from B4) — `core_users.__audit_exclude__
    = {password_hash, mfa_secret}`; the audit listeners write `[redacted]` (field
    name kept, value withheld) on INSERT + UPDATE, so a secret never seals into
    the immutable chain (database-standards §7).
  - **Argon2id hasher** (`core/security/password.py`, `argon2-cffi`; params in
    tech-stack.md). **RBAC seeds** — permission (27) + role (4) `SeedDataset`s in
    `REGISTRY` + a bespoke grant resolver (`core/seeds/rbac.py`, 41 grants,
    tombstoned revocations). **Bootstrap** — new `seed-rbac` + `promote-admin`
    (break-glass login from `settings.bootstrap_admin`, temp password once);
    `load-fixtures` now also seeds a synthetic org tree + staff.
- **Verified:** **pytest 155/155** (was 132; +23), **lint-imports 3/3**; full
  chain `0001→0010` idempotent (×2) + downgrade-to-base → re-upgrade clean; FK
  closure asserted (`test_identity_schema`); `oc_app` denied UPDATE/DELETE on
  `core_login_attempts` + no DELETE on any identity table; RBAC seed idempotent +
  every-permission-exists gate; break-glass promotion idempotent + temp password
  verifies; `password_hash`/`mfa_secret` `[redacted]` in the chain (INSERT +
  UPDATE) with `verify_chain` intact.
- **Decisions:** see `docs/modules/foundation.md` §7 (Stage B Increment 1).
- **Next:** Increment B2 — Authentication (see the Next Session Prompt).

### Session 6 — 2026-07-23 — Stage A Increment 4 (spine amendments) + Phase 0 gate ✅

- **Phase(s):** 0 / Stage A (closes Phase 0) · **Commit:** `session(2026-07-23)`
  (`74a9a7a`) + docs commits; tag `phase-0-complete` — **pushed to `origin`**
  (first push, after re-auth as `avincentpatrick`)
- **Done (migrations 0003–0008, built in independently-committable groups):**
  - **Activity taxonomies** — `core_activity_tags` (configurable GAD/CCET/DRR/UHC
    vocabulary, never boolean cols) + `core_activity_tag_assignments` (multi-tag
    link).
  - **UACS/PREXC** — `core_pap_codes` (per-FY tree, self-ref parent,
    effective-dated) + `core_object_codes` (travel = 5-02-01-010-00); UACS
    never-reuse (deactivate, effective-date a revision).
  - **Holiday + working-day engine** — `core_holidays` + pure `core/workdays.py`
    (weekend/holiday/suspension math, unit-tested) + DB loader.
  - **Compliance calendar** — `core_compliance_deadlines`, the 22 §3.4 statutory
    deadlines as effective-dated, tenant-overridable data (two partial-unique
    indexes: platform default vs tenant override).
  - **Attachments service** (`core_attachments` + `core/attachments/`) — magic-byte
    allowlist (JPEG/PNG/WebP/PDF; SVG rejected) → SHA-256 content-address →
    **injectable fail-closed scanner** (NullScanner deny-in-prod/clean-in-dev +
    ClamAVScanner) → Pillow re-encode + EXIF/XMP strip + HEIC→JPEG; dual SHA
    (original evidence + sanitized derivative served for images); retention
    (`retention_class`/`legal_hold`, no auto-purge, disposal report); deferred
    Celery scan task (`ops/`) + beat sweeper; **auth-checked download = a service
    method with an `authorize` hook** (HTTP router defers to Stage B).
  - **Notification outbox** — replaced the Inc-3 stub body: `core_notifications`
    (outbox + in-app center via a channel discriminator) + append-only
    `core_notification_deliveries` (dead-letter/failed-jobs); `send_notification`
    persists + dispatches (inline default; app enqueues to the worker in celery
    mode after commit, via an injected enqueuer — core stays Celery-free); dedup;
    Celery retry/back-off → dead. Signatures unchanged.
  - **Report lineage** — `core_report_lineages` (append-only, unaudited) +
    `record_lineage` helper (Blueprint #17).
  - **Seed framework** — `core/seeds/` datasets (owner + cadence) + `ops`
    `load-reference`: idempotent, environment-aware upsert; loaded tags/codes/
    holidays/deadlines (re-run = 0 changes; loads under production).
  - **Observability** — stdlib JSON logs + request-id contextvar (uvicorn routed
    through it) + fail-safe optional error tracker (`sentry-sdk`/GlitchTip);
    `docs/standards/api-standards.md`; `docs/compliance/` (PIA, register, breach
    runbook, retention) + expanded `docs/operations/` runbooks.
  - Compose: `clamav` (profile `clamav`) + GlitchTip (profile `observability`) —
    neither in default `up`/CI. Deps: Pillow, pillow-heif, clamd, sentry-sdk.
- **Verified:** **pytest 132/132** (was 68; +64), **lint-imports 3/3**; full chain
  `0001→0008` idempotent (×2) + downgrade-to-base → re-upgrade clean; attachment
  upload→scan→download round-trip with EXIF stripped on the served copy, and
  fail-closed rejects (infected/oversized/SVG/bad-magic/pending); notification
  dispatch inline **and** celery→worker end-to-end (`ops.dispatch_notification`
  registered, row → `sent`); `oc_app` denied UPDATE/DELETE on both new append-only
  tables; `load-reference` idempotent + prod-safe; `/health` healthy;
  `/api/v1/config` fail-safe OFF; JSON logs carry the request id; Laragon
  untouched.
- **Decisions:** see `docs/modules/foundation.md` §7 (attachments full-pipeline +
  ClamAV-opt-in; retention ≠ soft delete; outbox signature-stable; effective-dated
  never-boolean data; pure WD engine; report lineage append-only+unaudited;
  seed-framework cadences; observability logs-now/tracker-profile).
- **Phase 0 QA gate:** manual test guide added (foundation.md §8); CHANGELOG
  promoted to **0.1.0**; `APP_VERSION` bumped `0.1.0.dev1 → 0.1.0`; tagged
  **`phase-0-complete`**; **first push** of `master` + tags to `origin` landed
  (the cached credential was the wrong account — `icvpitahc`, 403 — so it was
  cleared and re-authenticated as `avincentpatrick`; `git ls-remote` confirms
  `origin/master` = `5eb19a4` + the tag).
- **Docs updated:** foundation.md (§1/§4/§6/§7/§8), tech-stack.md (deps/services/
  CLI/external), database-standards.md (§8 effective-dated + tenant-override),
  api-standards.md (new), docs/compliance/ (new, 5 files), docs/operations/
  (4 new runbooks), CHANGELOG.md, this file.
- **Next Session Prompt (archived):** Stage B (Phase 2) — Identity & Access —
  full text in the top block as of this session.

### Session 5 — 2026-07-23 — Stage A Increment 3 (integrations + bootstrap) ✅

- **Phase(s):** 0 / Stage A · **Commit:** `session(2026-07-23)` — local
- **Done:**
  - **Storage driver abstraction** (`office_connect/core/storage/`):
    `StorageDriver` ABC (content-addressed by SHA-256; `save`/`open`/`read`/
    `exists`/`delete`), **`LocalVolumeStorageDriver`** (the prod default —
    sharded `ab/cd/<sha256>` store, atomic `.partial`→`replace` + fsync,
    dedup; bind-mounted `./storage`→`/app/storage`), **`GoogleDriveStorageDriver`**
    (lazy client, **Shared-Drive verification** — refuses My Drive folders),
    `get_storage_driver()` factory on `STORAGE_DRIVER`.
  - **Email drivers** (`core/email/`): `EmailDriver` ABC + shared MIME builder;
    **SMTP** (stdlib `smtplib`, STARTTLS, the default transport), **Gmail API**
    (lazy client, domain-wide delegation, base64url send), **log** (dev
    fail-safe — records, doesn't send); `get_email_driver()` auto-selects
    `smtp` if `SMTP_HOST` set else `log`.
  - **Notification outbox stub** (`core/notifications/`, core-service #4 seam):
    `send_notification()` routes email events through the selected driver now;
    `send_test_email()` is the Increment-3 test-email path. Durable outbox
    table + retry + notification center flagged for Increment 4 (signature
    stable — Rule 10, no duplication).
  - **Design-token contract** (`core/ui/tokens.py`): `NEUTRAL_TOKENS` (WCAG-AA
    palette + 4-px spacing + type scale + shape) as the single source of truth,
    `build_tokens(branding)` deep-merges `branding.tokens` overrides (unknown
    keys ignored), `to_css_variables()` → `--oc-*`. Served under `tokens` in
    `GET /api/v1/config` — always present (neutral even under the DB fail-safe).
  - **Bootstrap CLI** (`office_connect/ops/bootstrap.py`): `init` (idempotent
    tenant + module flags), `create-admin` (records admin into the non-public
    `core_tenant_configs.settings` bag for Stage B; not a login), `load-fixtures`
    (synthetic activities, **refused in production**), `send-test-email`. DB
    writes via `oc_app`/`OCSession` (audited); async-from-sync per restore_drill.
  - **Migration 0002**: non-public `core_tenant_configs.settings` JSONB (never
    served by `/api/v1/config`); `settings` mapped on `TenantConfig`.
  - Deps: `google-api-python-client` 2.156.0 + `google-auth` 2.37.0 +
    `google-auth-httplib2` 0.2.0 (pure-Python, lazy-imported); storage bind
    mount + `STORAGE_DRIVER`/`STORAGE_DIR` env on app+worker; `.gitignore`
    `storage/`; `.env.example` driver settings.
- **Verified:** **pytest 68/68** (was 31; +37 across storage/email/notifications/
  tokens/config/bootstrap); **lint-imports 3/3**; migration 0002 idempotent (x2)
  + downgrade→re-upgrade clean; bootstrap CLI init/create-admin/load-fixtures/
  send-test-email all work end-to-end; `load-fixtures` refuses `APP_ENV=production`;
  local storage round-trips a real file (host `./storage` + container);
  `/api/v1/config` serves `tokens` and does **not** leak `bootstrap_admin`/the
  admin email; `/health` healthy; Laragon `dev_pims` untouched.
- **Decisions:** see `docs/modules/foundation.md` §7 (local-volume storage
  default; Google drivers fully built + lazy; create-admin deferred to Stage B
  via non-public `settings`; tokens = neutral defaults + branding merge).
- **Docs updated:** foundation.md (§1 status, §6 gates, §7 decisions), ui-standards.md
  (§2 note + §9 partial-fill), tech-stack.md (google deps + drivers + bootstrap
  CLI), database-standards.md (§11 `settings` bag), master-plan.md (§4 #3
  resolved), CHANGELOG.md, this file.
- **Git remote:** unchanged — provisioned, **still no push**; first push fires
  when Increment 4 passes the Phase 0 QA gate (push-per-phase).
- **Next Session Prompt (archived):** Stage A Increment 4 (spine amendments) —
  full text in the top block as of this session.

### Session 4 — 2026-07-23 — Stage A Increment 2 (ops) ✅

- **Phase(s):** 0 / Stage A · **Commit:** `session(2026-07-23)` — local
- **Done:**
  - **Backup + proven-restore drill** (`office_connect/ops/`): `pg_dump -Fc` as
    the owner role → `office_connect/backups`; restore-drill creates a scratch
    DB, `pg_restore`s, and re-runs `verify_chain()` — seeding a real ≥3-link
    audited chain first so the check is never vacuously green; hard scratch-name
    guard; `--force` cleanup. CLI: `python -m office_connect.ops
    {backup,restore-drill,backup-and-drill}`.
  - **Celery worker + single beat** (`office_connect/worker.py`, compose
    `worker`+`beat`): Redis transport (broker db 1 / results db 2), nightly
    backup task; verified running end-to-end via the broker.
  - **Explicit-step migrations**: `alembic upgrade head` as a deploy step;
    migration-on-boot demoted to a dev-only, env-gated (`OC_MIGRATE_ON_BOOT`),
    **advisory-locked** convenience in a container entrypoint (once per
    container; refused when `APP_ENV=production`). New `core/migrate.py`.
  - **Deploy guard** (`office_connect/ops/deploy_guard.py`, `--mode dev|release`)
    + `scripts/deploy.ps1` dev wrapper + `docs/operations/{deploy,backup-restore}.md`
    POSIX-sh runbooks.
  - Image: `postgresql-client-16` (PGDG, base-codename-derived) + `ENTRYPOINT`;
    `.gitignore` (backups/dumps/pgpass), `.gitattributes` (LF for `*.sh`),
    `.dockerignore` (entrypoint allowed through); new import-linter contract
    "core never imports ops or worker".
  - **Bugs caught & fixed during verification:** base image moved to Debian
    trixie (dropped the bad `bookworm-pgdg` repo); pg client 17-vs-server-16
    `transaction_timeout` restore failure (pinned client to 16); `str(URL)`
    password masking broke asyncpg scratch-DB auth (`render_as_string(
    hide_password=False)`); `scripts` excluded by `.dockerignore`.
- **Verified:** wiped-volume deploy both ways (explicit step + dev-convenience
  boot migration) → healthy, read-write, schema at 0001; `backup-and-drill` →
  audit_rows=3, verify=ok, scratch dropped, dump on host; backup task via broker
  → succeeded; **pytest 31/31**; **lint-imports 3/3**; deploy guard passes
  `--mode dev`, blocks `--mode release` on the `.dev1` version.
- **Decisions:** see `docs/modules/foundation.md` §7 (pg-client major match,
  owner-role backups, seed-before-drill, hide_password, Redis db separation,
  single beat, entrypoint boot-migrate, GitHub-private remote / second-disk
  backup target).
- **Docs updated:** foundation.md, tech-stack.md, CHANGELOG.md, this file; new
  `docs/operations/deploy.md` + `backup-restore.md`.
- **Git remote:** provisioned post-commit — `origin` →
  `github.com/avincentpatrick/office_connect` (`git ls-remote` verified, **no
  push**); first push fires at the Phase 0 / Increment-4 gate (push-per-phase).
- **Next Session Prompt (archived):** Stage A Increment 3 (integrations +
  bootstrap) — full text in the top block as of this session.

### Session 3 — 2026-07-23 — Comprehensive Master Plan v1 ✅

- **Phase(s):** planning (all stages) · **Commit:** `session(2026-07-23)` — local
- **Done:**
  - Two deep-research rounds (18 structured digests, archived in
    `docs/research/` with index): round 1 = engineering/platform practices
    (EO 77/COA rules, workflow engines, auth/NIST, modular monolith,
    attachments, gov UI, on-prem ops, DPA/retention, gap critic); round 2 =
    PH government standards for the new modules (CSC SPMS, DBM WFP/BED/BAR/FAR,
    RA 12009 PPMP/APP, GAM supply/property, ISO 9001 §7.5/§9.3, UACS/PREXC,
    ARTA CSM/FOI/NAP corrections, gap critic).
  - **`docs/master-plan.md` v1**: connectedness contract + core-services
    registry + connection matrix; stages A–I + Wave 2 with old-phase mapping;
    compliance/ops/training tracks; consolidated statutory calendar; open
    decisions register; reference-corrections ledger.
  - **Owner scope additions**: Calendar of Activities (connected surface),
    Controlled Document Management, Supply Management, WFP+PPMP, Performance &
    Deliverables; **DMWIS renamed → DTWIS** (`dtwis_` prefix registered).
  - New module docs: `qms.md`, `supply.md`, `planning-budget.md`,
    `performance.md`; `dmwis.md` → `document-tracking.md`; research-driven
    updates to reimbursement (delta register: EO 77 3-cluster DTE, COA
    2023-004, GAM form numbers, CA hard-block…), foundation (Inc 2 revised:
    explicit-step migrations, 3-2-1 backups; Inc 4 spine amendments added),
    landing (R-2 shell decision resolved; Calendar surface), css-is (ARTA
    v2023 scoring/deadline corrections), admin, reports.
  - Standards: prefix registry extended (`dtwis_`, `qms_`, `supply_`,
    `plan_`, `perf_`); **Rule 10 "shared service first"** added to
    development-workflow.md; soft-delete ≠ records-disposition + audit-payload
    SPI policy notes in database-standards.md; tech-stack production substrate
    corrected to Hyper-V Ubuntu VM + Docker Engine.
- **Decisions:** all 4 research addition packs adopted (compliance, ops/
  quality, training/rollout, platform services); **one shared core workflow
  engine** (built at R-4, supersedes module-internal approach); React shell +
  component library land with R-2; Wave-2 order A→B→C (swappable); Risk
  Registry + Management Review grouped into QMS module; remaining open
  decisions in master plan §4.
- **Docs updated:** master-plan.md (new), docs/research/ (new, 19 files),
  4 new + 7 updated module docs, 3 standards docs, docs/README.md, CLAUDE.md,
  CHANGELOG.md, this file.
- **Next Session Prompt (archived):** Stage A Increment 2 (ops, revised) —
  full text in the top block as of this session.

### Session 2 — 2026-07-22 — Standards codified + Phase 0 Increment 1 ✅

- **Phase(s):** 0 · **Commits:** `0d5a18c` (baseline) → `f0b39ac` (docs) →
  `b6e689b` (Increment 1) → `f76dd9b` (review hardening) — all **local**
  (push waits for the Phase 0 gate; no remote yet)
- **Done:**
  - 9 standing dev rules codified: `CLAUDE.md` session contract,
    `docs/standards/` (development-workflow, database-standards, ui-standards,
    tech-stack), `docs/modules/` (foundation + reimbursement real content,
    5 scaffolds), PROGRESS restructure, CHANGELOG, docs index.
  - Phase 0 Increment 1: `app/` → `office_connect/` restructure;
    Base + naming convention + Audit/SoftDelete/Lookup mixins; `core/time.py`;
    Alembic async chain + migration 0001 (5 spine tables, `oc_app`
    least-privilege role, seeds); automatic hash-chained audit trail;
    global soft-delete filter; `GET /api/v1/config` fail-safe OFF;
    31 QA-gate tests; import-linter contracts.
  - 34-agent adversarial review → 23 confirmed findings fixed (float/jsonb
    hash asymmetry, cascade/bulk-DML audit bypasses, cache poisoning,
    password dollar-quoting, test isolation, and more).
- **Verified:** from a **wiped volume**: `alembic upgrade head` ×2 idempotent,
  downgrade→re-upgrade clean, **pytest 31/31**, `lint-imports` 2/2 kept,
  `/health` healthy, `/api/v1/config` all flags OFF, Laragon untouched.
- **Decisions:** see `docs/modules/foundation.md` §7 (naming plural, BIGINT
  PKs, app-level audit listeners, no delete-orphan/bulk DML, `.devN`
  versioning, accepted limits).
- **Docs updated:** CLAUDE.md, all 4 standards docs, all 7 module docs,
  docs/README.md, README.md, CHANGELOG.md, this file.
- **Next Session Prompt (archived):** Phase 0 Increment 2 (ops: deploy guard
  script, backup + proven restore, Celery worker, migration-on-boot, git
  remote provisioning) — full text in the top block as of this session.

### Session 1 — 2026-07-22 — Dev environment set up & verified ✅

**Milestone: local development environment running and proven to coexist with
the existing Laragon `dev_pims` app on the same machine.**

- **Phase(s):** 0 (pre-work) · **Commit:** `0d5a18c` (local — committed at start of session 2)
- **Done:**
  - Project scaffold: `docker-compose.yml` (`postgres:16` + `redis:7` + FastAPI
    `app`), `Dockerfile` (python:3.12), `requirements.txt`, `app/main.py`
    (`/` + `/health` pinging Postgres & Redis), `app/core/config.py`,
    `app/core/db.py` (async SQLAlchemy pool 10/20), `.env`/`.env.example`,
    `scripts/setup-windows.ps1`, `scripts/smoke-test.ps1`, `README.md`, git init.
  - Docker Desktop + WSL2 installed (elevated), engine running (server 29.6.2).
- **Verified:**
  - Stack builds and starts: `db` healthy, `redis` healthy, `app` up.
  - `http://localhost:8001/health` → **200**
    `{"status":"healthy","checks":{"postgres":"ok","redis":"ok"}}`
  - Runs simultaneously with Laragon `dev_pims`, zero conflict — Laragon owns
    80/3306/8000, Office-Connect owns 8001/5432/6380.
- **Decisions:**
  - Production host = **on-prem Windows Server** (after development), NOT
    Hugging Face; CSS-IS stays on HF and is migrated in
    (`references/Hosting_Target_Clarification.md`, overrides plan C-4).
  - First user-facing module = **Local Travel Reimbursement**
    (`references/Phased_Rollout_Assessment.md` §0.1).
- **Next Session Prompt (archived):** *"planning and creating skills continue
  next session"* — Phase 0 foundation build (Alembic chain, `core_*` spine,
  hash-chained audit, `/api/v1/config` fail-safe OFF, package restructure,
  pytest QA gates).

---

## How to run

```powershell
docker compose up -d        # start (add --build after changing deps/Dockerfile)
docker compose ps           # status
docker compose logs -f app  # API log
docker compose down         # stop (Laragon unaffected)
```
Open: http://localhost:8001/health · http://localhost:8001/docs
