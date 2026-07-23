# Office-Connect — Progress Tracker

## ▶ RESUME *(copy this one line to start the next session)*

> **Resume Office-Connect — Stage B (Phase 2): Identity & Access — auth, RBAC, staff directory, delegation.**

That one line is all you paste. Per the start-of-session ritual I read the
*Current Status* + *Next Session Prompt* below (and the cited module docs) to
expand it into the full task and confirm with you before starting.

## ▶ CURRENT STATUS *(overwrite each session)*

- **Phase:** **Stage A (= Phase 0) COMPLETE** — Increments 1 ✅, 2 ✅, 3 ✅, 4 ✅;
  all Phase 0 QA-gate checks pass; tagged **`phase-0-complete`** and **pushed to
  GitHub** (`origin/master` = `5eb19a4`, tag on remote — verified via
  `git ls-remote`; the first push, after re-authenticating as `avincentpatrick`).
  **Next: Stage B (Phase 2) — Identity & Access.** Master Plan v1 in force
  (`docs/master-plan.md`).
- **Last session:** #6 — 2026-07-23 — Increment 4 (spine amendments) + Phase 0
  gate: the shared day-1 tables + services — activity taxonomies, UACS/PREXC
  codes, holiday + working-day engine, statutory compliance calendar (22 rows),
  content-addressed **attachments service** (magic-byte allowlist, EXIF strip,
  HEIC→JPEG, fail-closed ClamAV-opt-in scan, retention), **notification outbox**
  (durable + in-app center + Celery retry/dead-letter; stub replaced,
  signature-stable), report lineage, an idempotent **seed framework**, and
  **observability** (JSON logs + request IDs + fail-safe GlitchTip profile).
  Migrations `0003`–`0008`. Verified end-to-end (**pytest 132/132, lint-imports
  3/3**; full chain idempotent ×2 + downgrade-to-base→re-upgrade clean;
  attachment round-trip incl. EXIF strip + fail-closed download; notification
  dispatch inline **and** celery→worker; JSON logs carry the request id).
- **Decisions this session:** attachments = **full pipeline now, ClamAV opt-in**
  (injectable fail-closed scanner; compose profile); observability = **JSON logs
  now, tracker as a profile** (fail-safe `SENTRY_DSN`); auth-checked attachment
  download router + per-user notification prefs **defer to Stage B** (no auth
  yet — built as service seams). See `docs/modules/foundation.md` §7.
- **Blockers / waiting on user:** none. (The first push initially failed — the
  cached GitHub credential was for `icvpitahc`, which lacks write access; cleared
  it and re-authenticated as `avincentpatrick`, then the push landed.)

## ▶ NEXT SESSION PROMPT *(rule 3 — the full brief I expand the RESUME line into)*

```text
Context: Phase 0 / Stage A is COMPLETE and pushed (tag phase-0-complete). The
foundation floor is in place: schema spine + hash-chained audit + soft delete;
ops (backup/proven-restore, Celery worker/beat, explicit-step migrations);
integrations (storage + email drivers, bootstrap CLI, /api/v1/config tokens);
and the Increment-4 spine amendments — activity taxonomies, UACS/PREXC codes,
holiday + working-day engine, compliance calendar, attachments service,
notification outbox, report lineage, seed framework, observability (pytest
132/132, lint-imports 3/3; migration head 0008). Read CLAUDE.md, then
master-plan.md §2 Stage B + §1.1 (staff directory #14), then
docs/modules/foundation.md §5 (Phase 2 plan) which already scopes this stage.
Task: Build Stage B (Phase 2) — Identity & Access ("one login"). Per
foundation.md §5 + docs/research/round1/auth-rbac-onprem.md:
  (1) Resolve the OPEN DECISION first: core_users vs core_staff (one identity
      table vs auth-users + staff-directory split) — this also settles the
      irregular plural "staff". Confirm with the user at kickoff.
  (2) core_users/core_roles/permissions + org units; the deferred-FK migration
      that finally constrains every *_by / actor_id / division_id / section_id /
      recipient_user_id / holder_id across the whole spine (Inc 1–4 left these
      nullable BIGINT).
  (3) Auth: Redis server-side sessions, Argon2id, NIST 800-63B-4 password policy
      (len 12+ + blocklist; no composition rules / no forced rotation — record
      the reference's "letter+number" as a deviation), throttle-not-lockout,
      custom-header CSRF, break-glass local admin, TOTP MFA for approver/admin
      (NPC 2023-06).
  (4) RBAC: permission strings + role→permission tables + org-unit-scoped grants;
      delegation/OIC (on-behalf-of); maker-checker DB checks; read-only auditor
      role (COA Res. 2020-034) + printable chain-verification report.
  (5) Wire the deferred surfaces Inc 4 built as seams: the authenticated
      attachments upload/download router (inject the real RBAC authorize closure
      through (holder_kind, holder_id)), and notification per-user prefs +
      recipient_user_id resolution.
  (6) Staff directory: greenfield core tables seeded via CSV import from a CSS-IS
      export (recommended default — confirm at kickoff); query-log middleware;
      audit-payload SPI policy decision (master plan §4 #4) executes here.
Files: alembic/versions/0009_*.py (+ the deferred-FK migration),
office_connect/core/ (auth, rbac, models/users+roles+orgunits, directory),
office_connect/core/api/ (auth + attachments routers), docs/modules/foundation.md,
docs/standards/*, docs/compliance/ (per-module PIA before real data).
Acceptance: migration idempotent + reversible; login/logout/session lifecycle;
RBAC denies/permits per permission + org scope; delegation works; maker-checker
enforced; deferred FKs added cleanly; attachments router auth-checked end-to-end;
pytest green; lint-imports green. Phase 2 has its own QA gate (tag phase-2-complete).
Open questions for the user: (a) core_users vs core_staff identity model; (b)
staff-directory seed = greenfield + CSV-from-CSS-IS (default) or another source;
(c) confirm the audit-payload SPI policy (what personal values may enter the
immutable hash-chained log) before any real data.
```

---

## Stage tracker *(rule 4 — commit per session, push per phase/stage gate)*

Stages per `docs/master-plan.md` §2 (old phase numbers kept for traceability).

| Stage | Old # | Scope | Status | Sessions | QA gate | Pushed (tag / date) |
|---|---|---|---|---|---|---|
| A | 0 (inc 1–4) | Foundation: spine ✅, ops ✅, integrations ✅, spine amendments ✅ | complete (pushed) | 1–6 | ✅ passed | `phase-0-complete` / 2026-07-23 |
| B | 2 | Identity & access: auth / RBAC / directory / delegation | not started | — | — | — |
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
