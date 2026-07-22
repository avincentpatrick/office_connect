# Office-Connect — Progress Tracker

## ▶ CURRENT STATUS *(overwrite each session)*

- **Phase:** 0 (Foundation floor) — Increment 1 in progress (session 2 underway)
- **Last session:** #2 — 2026-07-22 — standards codified + Phase 0 Increment 1
- **Blockers / waiting on user:** none

## ▶ NEXT SESSION PROMPT *(rule 3 — paste this to resume)*

```text
(Being written at the end of session 2 — see development-workflow.md §3.)
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

### Session 2 — 2026-07-22 — Standards codified + Phase 0 Increment 1

*(entry completed at session end)*

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
