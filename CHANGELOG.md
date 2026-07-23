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
