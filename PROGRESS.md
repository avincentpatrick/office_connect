# Office-Connect — Progress Tracker

## ▶ CURRENT STATUS *(overwrite each session)*

- **Phase:** 0 (Foundation floor) — **Increment 1 ✅ complete**; Increments 2–3 remain
- **Last session:** #2 — 2026-07-22 — 9 dev rules codified into standards docs + Increment 1 built, adversarially reviewed, all QA gates green
- **Blockers / waiting on user:** none (R-0 author decisions can be prepared in parallel — see `docs/modules/reimbursement.md` §3)

## ▶ NEXT SESSION PROMPT *(rule 3 — paste this to resume)*

```text
Context: Office-Connect Phase 0 Increment 1 is complete (schema spine, audit
chain, soft deletes, /api/v1/config — 31 QA-gate tests green, commit f76dd9b).
Standards live in docs/standards/; read CLAUDE.md first.
Task: Build Phase 0 Increment 2 (ops) per docs/modules/foundation.md §3:
(1) deploy script with live-DB/version-bump/CHANGELOG guards, (2) scheduled
pg_dump backup + ONE PROVEN RESTORE, (3) enable the Celery worker service +
first beat backup task, (4) migration-on-boot in the app lifespan,
(5) provision the private git remote (required before the Phase 0 push).
Files: scripts/, docker-compose.yml (worker), office_connect/main.py
(lifespan), office_connect/worker.py (new), docs/modules/foundation.md.
Acceptance: docker compose up -d --build from a wiped volume comes up
read-write with no manual migration step; a backup file is produced and
restored successfully into a scratch DB; pytest still 31/31 green;
lint-imports green.
Open questions for the user: where should off-box backup copies go
(second disk / network share / Drive)? Create the private git remote on
which host (GitHub private / Gitea / other)?
```

---

## Phase tracker *(rule 4 — commit per session, push per phase)*

| Phase | Scope | Status | Sessions | QA gate | Pushed (tag / date) |
|---|---|---|---|---|---|
| 0 | Foundation floor (spine, audit, flags, ops, integrations) | in progress | 1–2 | pending | — |
| 2 | Shared core: auth / RBAC / staff directory | not started | — | — | — |
| R-0…R-9 | Reimbursement module | not started | — | — | — |
| 3 | Landing shell / query bar | not started | — | — | — |
| 4–7 | DMWIS | not started | — | — | — |
| 1/8 | CSS-IS migration | not started | — | — | — |
| 9 | Admin + Reports | not started | — | — | — |
| 10 | Hardening / SIT | not started | — | — | — |

Status values: `not started → in progress → QA → complete (pushed)`.
A phase's **Pushed** cell is filled only when its QA gate passed and the tag is
on the remote — that cell enforces the push-per-phase rule.
Governance gate (DOH / Data Privacy Act) blocks loading **real** data, not the build.

---

## Session log *(newest first)*

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
