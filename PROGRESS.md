# Office-Connect — Progress Tracker

## ▶ CURRENT STATUS *(overwrite each session)*

- **Phase:** Stage A (= Phase 0) — **Increments 1 ✅, 2 ✅**; Increments 3–4
  remain. **Master Plan v1 adopted** (`docs/master-plan.md`).
- **Last session:** #4 — 2026-07-23 — Increment 2 (ops): backup + proven-restore
  drill (`verify_chain()` green), Celery worker/beat + nightly backup task,
  explicit-step migrations (dev-only env-gated advisory-locked boot migration),
  deploy guard, operations runbooks. Verified end-to-end (wiped-volume deploy,
  drill, task via broker; **pytest 31/31, lint-imports 3/3**).
- **Decisions this session:** git remote = **GitHub private**; off-box backup
  target = **second/external disk**; pg client pinned to major 16; ops in a new
  `office_connect/ops/` package.
- **Blockers / waiting on user:** none. Private git remote **provisioned**
  (`origin` → `github.com/avincentpatrick/office_connect`, `git ls-remote`
  verified — **no push yet**; first push fires at the Phase 0 / Inc-4 gate).

## ▶ NEXT SESSION PROMPT *(rule 3 — paste this to resume)*

```text
Context: Office-Connect Master Plan v1 is adopted (docs/master-plan.md); Phase 0
/ Stage A Increments 1 (schema spine) and 2 (ops) are complete — backup+restore
drill, Celery worker/beat, explicit-step migrations, deploy guard all verified
(pytest 31/31, lint-imports 3/3). Read CLAUDE.md, then master-plan.md §2 Stage A,
then docs/modules/foundation.md §3 (Increment 3).
Task: Build Stage A Increment 3 (integrations + bootstrap): (1) storage driver
abstraction (local-volume driver as the prod default per master-plan §4 #3;
Google Drive driver kept for tenants that want it) behind a clean interface,
(2) SMTP + Gmail two-driver email abstraction wired behind a notification
outbox stub + a test-email path, (3) a bootstrap CLI that creates the first
System Admin and refuses fixtures in prod + synthetic fixtures, (4) the
design-token contract served via GET /api/v1/config (ui-standards §2).
Files: office_connect/core/ (storage/, email/, config endpoint), a new
bootstrap CLI (office_connect/ops/ or a core cli), docs/modules/foundation.md.
Acceptance: local-volume storage round-trips a file; test email sends via the
selected driver (or logs in dev); bootstrap creates an admin and refuses in
prod; /api/v1/config returns the token contract; pytest green; lint-imports 3/3.
Open questions for the user: git remote is wired (origin ->
github.com/avincentpatrick/office_connect; push deferred to the Inc-4 gate).
Confirm storage default = local volume for prod.
```

---

## Stage tracker *(rule 4 — commit per session, push per phase/stage gate)*

Stages per `docs/master-plan.md` §2 (old phase numbers kept for traceability).

| Stage | Old # | Scope | Status | Sessions | QA gate | Pushed (tag / date) |
|---|---|---|---|---|---|---|
| A | 0 (inc 1–4) | Foundation: spine ✅, ops ✅, integrations, spine amendments | in progress | 1–4 | pending | — |
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
