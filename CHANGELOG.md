# Changelog

All notable, user-visible changes to Office-Connect. Format follows
[Keep a Changelog](https://keepachangelog.com/); versions align to **phase
completions** (e.g. `0.1.0` = Phase 0 complete) and match the `APP_VERSION`
constant in `office_connect/__init__.py`.

`[Unreleased]` accrues session by session and is promoted to a version at each
phase QA gate (see `docs/standards/development-workflow.md` §6) — this is what
makes the push-per-phase rule auditable.

## [Unreleased]

### Added
- **Stage C — the shared core workflow engine** (`core_workflow_*`, 2026-07-27): the
  ONE approval/routing engine every module will consume (Rule 10 + master-plan §1.1 #1),
  built as a pure core service ahead of its first consumer (reimbursement R-4). A workflow
  is authored as versioned, **immutable-once-published** definitions (states + transitions
  with **typed** amount/permission guards — no DSL), started as an instance pinned to its
  version, and driven by an atomic, idempotent, compare-and-swap `execute_action`
  (409 on a stale version or a lost race). Approval gates route by org scope
  (`authorize_scoped`) + segregation-of-duties (no self-approval, distinct four-eyes
  approvers), with **delegation / OIC** recorded as "acted on behalf of". The
  append-only, **audited** event log is the authoritative history — the instance's current
  state is a derived read-model proven by an event-fold consistency check. Return loops
  back (resubmit restarts, revision-tracked); reject is terminal. An idempotent,
  non-interrupting SLA sweep (`ops.sweep_workflow_sla`, beat every 5 min) escalates overdue
  steps to the holder only. A module's feature flag blocks **new** instances while in-flight
  ones always finish. New permission strings `workflow.definition.read/manage/publish`,
  `workflow.instance.read`, `workflow.delegation.manage` (auditor gets the reads). Contract:
  `docs/standards/workflow-standards.md`. Verified: **pytest 320 (+34), lint-imports 3/3**,
  migration `0012` (8 tables + 6 enums; `core_workflow_events` append-only + REVOKE UPDATE;
  idempotent + reversible). No new dependency.

## [0.2.0] — 2026-07-27 — Phase 2 (Stage B) complete

### Added
- **Stage B (Phase 2) Increment 4 — wire seams + directory + compliance**
  (2026-07-27): closed the deferred shared-service seams and the Stage-B compliance
  gates. **Authed attachments HTTP router** (`/api/v1/attachments`) — upload
  (magic-byte validated, size-capped, `pending`), streaming auth-checked download
  (serves the EXIF-stripped derivative), metadata, soft-delete, disposal report —
  each gated by an `attachment.*` permission string, with a **per-upload malware-scan
  enqueue after commit** (the beat sweeper remains the backstop) and a holder-scoping
  authorize seam ready for Stage C. **Notification recipient/preference resolution** —
  a `recipient_user_id` now resolves to the login's email (staff-email fallback), and
  a new `core_notification_preferences` opt-out table suppresses opted-out
  channel/module deliveries (persisted as `suppressed`, never dispatched) while
  **security/transactional** notifications always send. **CSS-IS directory
  ingestion** — a pure, idempotent, atomically-validated upsert of a CSV org/staff
  feed into `core_org_units`/`core_staff` (topological tree insert, tombstone restore,
  leave-alone by default), exposed as `POST /api/v1/directory/import` and a
  `bootstrap ingest-directory` CLI, now the single code path `load-fixtures` uses.
  **Admin user provisioning** (`/api/v1/users`) — create a login from a staff record
  (temporary password, forced change; **no self-registration**), deactivate (revokes
  every Redis session immediately) / reactivate, all hash-chained; role grants and
  password reset reuse the existing RBAC/auth endpoints. **Query-log middleware** —
  one append-only `core_query_logs` row per `/api/v1` request (ids + param names +
  status only, never bodies/values/SPI), the COA read-access posture. **Full
  person-field SPI redaction** — `core_staff` name/email and notification
  recipient/body/payload VALUES are withheld from the immutable audit chain (field
  names kept; the live row is the source of truth), extending the B1 credential
  subset. **Stage-B PIA** + processing-register row (NPC Advisory 2017-03). Adds
  `python-multipart`. Verified: **pytest 286 (+48), lint-imports 3/3**, migration
  `0011` (notification preferences + `suppressed` status; idempotent + reversible).
- **Stage B (Phase 2) Increment 3 — RBAC enforcement** (2026-07-23): real
  authorization on the B2 auth runtime (**no migration**). **Permission-gated
  routes** — every protected endpoint declares a permission *string* (never a role
  name); `require_permission(perm, scope=)` resolves the actor's effective set from
  a **Redis cache** (db 4) keyed by `core_users.permissions_version`, so a cache hit
  takes no DB hit. **Grant/revoke lands on the next request** — an admin grant/revoke
  bumps the version and stamps it onto the target's live sessions, taking effect
  immediately without a re-login; no pub/sub. **Org-unit-scoped authorization** —
  `scope=REQUESTER` checks the actor's grant against the request's org unit by
  walking the `core_org_units` ancestry (a scoped `org_unit_id` covers its subtree;
  a global grant covers everywhere). **Delegation / OIC** — time-boxed grants via
  `core_user_roles.valid_from`/`valid_to`, with the cache TTL capped at the next
  window edge so an expiring delegation drops precisely. **Maker-checker** — a
  reusable no-self-approval / distinct-approver segregation-of-duties check (COA
  92-389, NGICS). **RBAC admin API** (`/api/v1/rbac/*`) — grant/revoke roles
  (org-scoped and/or time-bounded) + read the role/permission catalog, emitting
  `rbac.role.granted`/`revoked` hash-chain events. **Read-only auditor** (COA Res.
  2020-034) — `GET /api/v1/audit/verify` renders a printable HTML chain-verification
  report (PASS/FAIL, JSON via `Accept`) and `GET /api/v1/audit/records/{table}/{pk}`
  the per-record timeline; the `auditor` role is read-only everywhere by permission
  gating alone. New error slugs `forbidden` (403) and `segregation_of_duties` (409).
  Verified: **pytest 238 (+25), lint-imports 3/3**, no schema change.
- **Stage B (Phase 2) Increment 2 — authentication** (2026-07-23): the login
  runtime on the B1 identity floor (**no migration**). **Cookie-based server-side
  sessions** on Redis (logical db 4) — an opaque HttpOnly/`SameSite=Lax`/`Path=/api`
  session id, fresh at login and rotated on privilege change; logout destroys the
  server-side record; server-enforced timeouts (12 h absolute; 30 min idle for
  privileged roles / 60 min staff); a concurrent-session cap (3, oldest evicted);
  revoke-all on password change / deactivation; "active sessions" listing + remote
  revoke. **Argon2id login** reusing the B1 hasher, with transparent re-hash on
  cost upgrade. **NIST 800-63B-4 password policy** — min 12, no composition, no
  rotation, and a vendored **top-100k blocklist** (no runtime cloud call).
  **Throttle-not-lockout** — per-account + per-IP backoff after 5 failures with a
  generic, non-enumerating failure. **TOTP MFA** (approver/admin; NPC 2023-06) —
  two-step challenge with enrollment, replay-protected, force-enrollment for
  privileged accounts. **Break-glass** local login (bypasses the future LDAP
  backend). **Custom-header CSRF** on every non-GET. **Auth + CSRF middleware** put
  the real principal on the request so audited writes carry the true `actor_id`;
  logout/session-revoke ride the hash chain via a new `append_auth_event` (no
  secret ever logged). Endpoints under `/api/v1/auth/*` (login, logout, me,
  password change, MFA enroll/confirm/verify, own + admin session management,
  admin password reset) plus the first structured **error envelope**. Adds `pyotp`.
  Verified: **pytest 213 (+58), lint-imports 3/3**, no schema change.
- **Stage B (Phase 2) Increment 1 — identity schema + deferred-FK closure**
  (2026-07-23): the identity floor for "one login". **Split identity model** —
  `core_staff` (plantilla person directory, a superset) + `core_users` (auth
  accounts with a nullable `staff_id` FK). **Org units** — the self-referencing
  `core_org_units` tree (office/division/section/unit) that scopes every approval
  role. **RBAC tables** — `core_roles`, `core_permissions`,
  `core_role_permissions`, and org-unit-scoped `core_user_roles` (grant uniqueness
  uses PG16 `NULLS NOT DISTINCT`; `valid_from`/`valid_to` reserved for B3
  delegation). **Login-attempt log** — append-only `core_login_attempts`
  (anti-enumeration, never stores the password). **Deferred-FK closure** —
  migration `0010` constrains every ownership/actor/org column deferred since
  Phase 0 (`created_by`/`updated_by`/`deleted_by`/`actor_id`/`recipient_user_id`/
  `disposed_by`/`generated_by` → `core_users`, `division_id`/`section_id` →
  `core_org_units`, `tenant_id` → `core_tenant_configs`); the sanctioned
  polymorphic/generic-pointer columns stay unconstrained. **Credential
  redaction** — `password_hash`/`mfa_secret` values never enter the immutable
  audit chain (a `[redacted]` marker keeps the field name; INSERT + UPDATE).
  **Argon2id** password hashing (`core/security/password.py`). **RBAC seeds** —
  idempotent permission (27) + role (4) catalogs and a grant resolver (41 default
  grants) with tombstoned revocations; new `bootstrap seed-rbac` +
  `promote-admin` (break-glass login from the recorded bootstrap admin, temp
  password printed once). Synthetic org-unit + staff dev fixtures (CSS-IS
  decoupled). Migrations `0009`–`0010`. Verified: **pytest 155/155, lint-imports
  3/3**, full chain `0001→0010` idempotent + reversible, FK closure asserted,
  redaction proven, `verify_chain` intact.

## [0.1.0] — 2026-07-23 — Phase 0 (Stage A) complete

### Added
- **Phase 0 Increment 4 — spine amendments** (2026-07-23): the shared "day-1"
  tables and services every later module builds on (Rule 10). **Activity
  taxonomies** — configurable GAD/CCET/DRR/UHC tags as rows (`core_activity_tags`
  + assignments), never boolean columns. **UACS/PREXC codes** — per-FY PAP tree
  (`core_pap_codes`) + 10-digit object codes (`core_object_codes`, travel =
  5-02-01-010-00), effective-dated with UACS never-reuse. **Holiday &
  working-day engine** — `core_holidays` + `core/workdays.py`, the single
  deadline-math engine (weekends + PH holidays/suspensions). **Statutory
  compliance calendar** — the 22 §3.4 deadlines as effective-dated,
  tenant-overridable data (`core_compliance_deadlines`). **Attachments service**
  (`core_attachments`) — magic-byte allowlist → SHA-256 content-addressed store →
  fail-closed malware scan (injectable; ClamAV opt-in via a compose profile) →
  Pillow re-encode/EXIF-strip (HEIC→JPEG); auth-checked streaming downloads
  (service method with an authorization hook; the HTTP router lands with auth in
  Stage B); retention (`retention_class`/`legal_hold`, no auto-purge, disposal
  report). **Notification outbox** — the Increment-3 stub becomes a durable
  outbox + in-app notification-center schema (`core_notifications`) with Celery
  retry + dead-letter (`core_notification_deliveries`); `send_notification`
  signature unchanged. **Report lineage** (`core_report_lineages`) — provenance
  of every generated output. **Seed framework** — idempotent, environment-aware
  reference-data loader (`load-reference`) with named owners + cadences.
  **Observability** — structured JSON logs with request IDs and a fail-safe
  optional self-hosted error tracker (GlitchTip, compose profile); new
  `docs/standards/api-standards.md`. `docs/compliance/` (PIA template, processing
  register, breach runbook, retention schedule) + expanded `docs/operations/`
  runbooks. Migrations `0003`–`0008`. Verified: **pytest 132/132, lint-imports
  3/3**, full chain idempotent + reversible, attachment round-trip incl. EXIF
  strip + fail-closed download, notification dispatch (inline + celery→worker).
- **Phase 0 Increment 3 — integrations + bootstrap** (2026-07-23): the outward-
  facing seams the later modules consume. **Storage driver abstraction**
  (`core/storage/`): a content-addressed interface with a **local-volume driver**
  (the on-prem production default — atomic writes, SHA-256 dedup, bind-mounted
  `./storage`) and a **Google Drive driver** (Shared-Drive-verified). **Email
  driver abstraction** (`core/email/`): **SMTP** (stdlib, the default transport),
  **Gmail API**, and a **log** driver (dev fail-safe that records instead of
  sending), auto-selected by config, behind a **notification outbox stub**
  (`core/notifications/`, core-service #4 seam) with a **test-email path**.
  **Design-token contract**: `GET /api/v1/config` now serves a **`tokens`** object
  — WCAG-AA neutral defaults (palette, 4-px spacing scale, type scale) as the
  single source of truth, with tenant `branding.tokens` overrides merged in;
  present even under the DB fail-safe. **Bootstrap CLI**
  (`python -m office_connect.ops.bootstrap`): `init` (idempotent tenant + flag
  setup), `create-admin` (records the designated System Admin into a **non-public**
  tenant `settings` bag for Stage B to promote — no login yet, no user table
  until Stage B), `load-fixtures` (synthetic dev activities, **refused in
  production**), `send-test-email`. Migration 0002 adds the non-public
  `core_tenant_configs.settings` JSONB (never exposed by `/api/v1/config`).
  Verified end-to-end: local storage round-trips a file (host + container),
  test email sends via the selected driver (logs in dev), bootstrap works and
  refuses fixtures in prod, config serves tokens without leaking the admin;
  **pytest 68/68, lint-imports 3/3**, migration idempotent + reversible.
- **Phase 0 Increment 2 — ops** (2026-07-23): operability + recoverability for
  the foundation floor. Scheduled `pg_dump -Fc` backups (owner role, 3-2-1
  local leg in `./backups`, retention 7) plus a **proven-restore drill** that
  restores into a throwaway scratch database and re-runs the audit-chain
  `verify_chain()` integrity check (seeding a real ≥3-link chain first so the
  check is never vacuously green). **Celery worker + single beat scheduler**
  (Redis transport, broker/results on separate logical DBs) with the nightly
  backup as the first scheduled task. **Migrations as an explicit deploy step**
  (`alembic upgrade head` before app start); the previous migration-on-boot is
  demoted to a dev-only, env-gated (`OC_MIGRATE_ON_BOOT`), advisory-locked
  convenience that production refuses. **Deploy guard** (`--mode dev|release`):
  single-Alembic-head, backup-before-migrate, no-prod-boot-migration, and — at
  release — no `.devN` version and a non-empty CHANGELOG `[Unreleased]`.
  Operations runbooks (`docs/operations/deploy.md`, `backup-restore.md`) and a
  `scripts/deploy.ps1` dev wrapper. Verified end-to-end: wiped-volume deploy
  (explicit + dev-convenience) comes up read-write; drill green; Celery task
  runs via the broker; pytest 31/31; lint-imports 3/3.
- **Master Plan v1** (2026-07-23, `docs/master-plan.md`): authoritative
  consolidation of the reference execution plan + its amending documents +
  two deep-research rounds (18 digests, `docs/research/`) + owner scope
  additions. Build sequence restructured into Stages A–I + Wave 2; binding
  connectedness contract (one shared core workflow engine for every approval
  flow; core-services registry; connection matrix; Rule 10 "shared service
  first"); consolidated statutory-deadline calendar; reference-corrections
  ledger (EO 77 3-cluster travel rates, FOI 15+20-working-day clock, GAM form
  numbering, RA 12009 procurement forms, ₱50k property threshold, and more).
- **Four new planned modules** (owner additions): QMS (controlled documents ·
  risk registry · management review), Supply Management, Planning & Budget
  (WFP/BED/BAR + PPMP/APP), Performance & Deliverables (SPMS · accomplishment
  reports · COA findings) — plus the Calendar of Activities as a connected
  core surface. Module docs scaffolded with government-standard scope.

### Changed
- **DMWIS renamed to DTWIS (Document Tracking & Workflow IS)** to distinguish
  document *tracking* from the new controlled-document *management* module;
  prefix registry updated (`dtwis_`), no schema existed yet.
- Foundation Increment 2 revised (explicit-step migrations replace
  migration-on-boot for production; 3-2-1 backup placement; git remote must
  live off the future production hardware); Increment 4 (spine amendments)
  added. Production substrate corrected to Hyper-V Ubuntu VM + Docker Engine
  in `tech-stack.md`.
- Development standards codified (2026-07-22): database naming / audit /
  soft-delete standards, UI token & component standards, tech-stack register,
  session workflow with next-session prompts, per-module documentation set,
  `CLAUDE.md` session contract.
- Phase 0 Increment 1 (2026-07-22): core schema spine (`core_tenant_configs`,
  `core_feature_flags`, `core_audit_logs`, `core_query_logs`,
  `core_activities`) via a single Alembic chain; automatic hash-chained audit
  trail on every data change; soft deletes with a global filter; least-
  privilege runtime DB role (`oc_app`, no DELETE anywhere);
  `GET /api/v1/config` (tenant + branding + feature flags, Redis-cached,
  fail-safe OFF, never 500); 31 QA-gate tests + import-linter contracts.
  Hardened by a 34-agent adversarial review (23 confirmed findings fixed).
- Feature-flag rollout note: flags default **OFF**; cohort widenings will be
  recorded here per release.
