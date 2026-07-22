# Office-Connect — Progress Log

## 2026-07-22 — Dev environment set up & verified ✅

**Milestone: local development environment is running and proven to coexist with
the existing Laragon `dev_pims` app on the same machine.**

### What exists now
- **Project scaffold** at `c:\Python Project\dev_office_connect` (Python /
  FastAPI + PostgreSQL + Redis, containerized):
  - `docker-compose.yml` — `postgres:16` + `redis:7` + FastAPI `app`
  - `Dockerfile` (python:3.12), `requirements.txt`
  - `app/main.py` (`/` + `/health` that pings Postgres & Redis),
    `app/core/config.py`, `app/core/db.py` (async SQLAlchemy pool 10/20)
  - `.env` / `.env.example` (real `.env` git-ignored)
  - `scripts/setup-windows.ps1` (one-time elevated installer),
    `scripts/smoke-test.ps1` (build + health check)
  - `README.md`, git initialized
- **Docker Desktop + WSL2 installed** (by the user, elevated) and the engine is
  running (server 29.6.2).

### Verified this session
- Stack builds and starts: `db` healthy, `redis` healthy, `app` up.
- `http://localhost:8001/health` → **200** `{"status":"healthy","checks":{"postgres":"ok","redis":"ok"}}`
- **Runs simultaneously with Laragon `dev_pims`, zero conflict** — all six ports
  listening at once, both apps reachable:

  | Port | Owner |
  |---|---|
  | 80 / 3306 / 8000 | Laragon `dev_pims` (Apache / MySQL / `php artisan serve`) |
  | 8001 / 5432 / 6380 | Office-Connect (FastAPI / PostgreSQL / Redis) |

  MySQL vs PostgreSQL and PHP vs Python are fully isolated; ports were chosen to
  avoid Laragon (dev_pims runs on 8000, so the API uses 8001; Redis on 6380 not
  6379; Postgres 5432 is free).

### How to run (from the project root)
```powershell
docker compose up -d        # start (add --build after changing deps/Dockerfile)
docker compose ps           # status
docker compose logs -f app  # API log
docker compose down         # stop (Laragon unaffected)
```
Open: http://localhost:8001/health · http://localhost:8001/docs

### Key decisions locked
- **Production host = on-prem Windows Server** (handled *after* development), NOT
  a Hugging Face Space. CSS-IS (Module 1) stays on Hugging Face and is migrated
  in. Recorded in `references/Hosting_Target_Clarification.md` (overrides plan C-4).
- **First user-facing module = Local Travel Reimbursement** (author decision,
  `references/Phased_Rollout_Assessment.md` §0.1), built on the foundation floor.

---

## Next up (deferred to a future session)
Per the user: *planning and creating skills continue next session.*

1. **Phase 0 foundation build** — the shared-schema spine + platform conventions
   the current scaffold does NOT yet have: Alembic migration chain; `core_*`
   spine tables (tenant config, feature flags, **append-only hash-chained
   audit**, query log, `core_activity`); UTC-store/Manila-display timezone
   convention; `/api/v1/config` feature-flag endpoint (fail-safe OFF); package
   restructure to `office_connect/core` + `modules/` with import-linter; pytest
   QA gates; deploy + `pg_dump`/restore scripts; bootstrap-admin CLI + fixtures;
   Google Drive + email drivers.
   → Drafted increment plan: `C:\Users\avinc\.claude\plans\glowing-dazzling-emerson.md`
2. **Phase 2** — shared core auth / RBAC / staff directory ("one login").
3. **Reimbursement module** — R-0 requirements session (author decisions: claim
   fields, FS-BD-01 checklist, signatory/certification chain,
   directory-slice-vs-greenfield, pilot cohort) → R-1 schema+config → R-2 wizard
   → R-3…R-9 (spec: `references/Reimbursement_Module_Build_Spec_v1.md` §14).
4. **Governance gate** — DOH / Data Privacy Act clearance blocks loading *real*
   financial/personal data (not the build).

### Reference docs (in `references/`)
- `OfficeConnect_Build_Execution_Plan_v1_0.docx` — single source of truth
- `Hosting_Target_Clarification.md` — Windows Server hosting override
- `Reimbursement_First_Dependency_Analysis.md`, `Reimbursement_Module_Build_Spec_v1.md`
- `Phased_Rollout_Assessment.md`, `Digital_Transformation_Integration_Blueprint.md`
- `Source_Grounding_and_Understanding.md`, `CSS-IS_Current_Build_Reconciliation.md`
