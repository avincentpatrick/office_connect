# Tech Stack

Every language, framework, library, image, and tool used in Office-Connect
(standing rule 9). **Maintenance rule:** any change to `requirements.txt`,
`package.json`, `docker-compose.yml`, or the toolchain updates this file **in
the same session** (session-end checklist step 3).

---

## 1. Languages & runtimes

| Language | Version | Used for | Pinned where |
|---|---|---|---|
| Python | 3.12 | Backend (FastAPI API, workers, CLI) | `Dockerfile` (`python:3.12-slim`) |
| SQL (PostgreSQL dialect) | PG 16 | Schema, migrations, grants | `docker-compose.yml` (`postgres:16-alpine`) |
| PowerShell | 5.1+ | Windows ops scripts | `scripts/*.ps1` |
| TypeScript / React | — | Frontend — **DEFERRED**, filled the session the React scaffold lands | — |

## 2. Backend dependencies (`requirements.txt`)

| Package | Version | Purpose |
|---|---|---|
| fastapi | 0.115.6 | ASGI web framework |
| uvicorn[standard] | 0.34.0 | ASGI server (`--proxy-headers` for reverse-proxy deployments) |
| sqlalchemy[asyncio] | 2.0.36 | Async ORM; shared `Base` + naming convention + audit/soft-delete listeners |
| asyncpg | 0.30.0 | PostgreSQL async driver |
| alembic | 1.14.0 | Migrations — single chain, async `env.py` |
| redis | 5.2.1 | Redis client (config cache, later Celery broker) |
| celery | 5.4.0 | Background jobs (worker service wired in Phase 0 Increment 2) |
| pydantic-settings | 2.7.1 | `.env`-driven typed settings |
| python-dotenv | 1.0.1 | `.env` loading |
| httpx | 0.28.1 | HTTP client; also drives ASGI tests |
| pytest | 8.3.4 | Test runner (QA gates) |
| pytest-asyncio | 0.24.0 | Async test support |
| asgi-lifespan | 2.1.0 | Runs FastAPI lifespan under httpx `ASGITransport` in tests |
| import-linter | 2.1 | Enforces "modules import core, never each other" (`pyproject.toml`) |
| tzdata | 2024.2 | IANA zoneinfo data for slim images / Windows hosts |

## 3. Infrastructure images & services (`docker-compose.yml`)

| Service | Image | Host port | Notes |
|---|---|---|---|
| `db` | postgres:16-alpine | 5432 | volume `pgdata`; healthcheck `pg_isready`; roles: `oc_dev` (owner/migrations), `oc_app` (runtime, no DELETE) |
| `redis` | redis:7-alpine | **6380** → 6379 | 6380 avoids Laragon's 6379 |
| `app` | built from `Dockerfile` | 8001 | uvicorn `office_connect.main:app`; 8000 is Laragon's |
| *(worker)* | same image | — | Celery worker — commented out until Increment 2 |

Port deconfliction with the coexisting Laragon `dev_pims` app: Laragon owns
80/3306/8000/5173/6379; Office-Connect uses 8001/5432/6380 (+5174 for Vite later).

## 4. Frontend stack — DEFERRED

Locked by the execution plan: **React + Vite (:5174) + Tailwind**, tokens-only
styling per [`ui-standards.md`](ui-standards.md). This section is filled with
exact versions and libraries **the session the frontend scaffold lands**.

## 5. Dev & QA tooling

| Tool | Purpose |
|---|---|
| Docker Desktop + WSL2 | Dev containers on Windows 11 |
| pytest (+ pytest-asyncio, asgi-lifespan, httpx) | Phase QA gates |
| import-linter (`lint-imports`) | Architecture contract enforcement |
| Alembic CLI | Migrations (runs as `oc_dev` via `MIGRATION_DATABASE_URL`) |
| `scripts/setup-windows.ps1` | One-time elevated prerequisites installer |
| `scripts/smoke-test.ps1` | Build + health-check the stack |
| Git | Local commits per session; push + tag per phase (see `development-workflow.md` §4) |
| Claude Code (AI assistant) | Pair-builds the project; session contract in `CLAUDE.md` |

## 6. External services

| Service | Role | Status |
|---|---|---|
| Google Drive / Docs API | Storage driver + template assembly (plan S-5) | Phase 0 Increment 3 |
| SMTP / Gmail API | Two-driver email abstraction | Phase 0 Increment 3 |
| Hugging Face Space | Legacy CSS-IS host until its migration (Phases 1/8) | External, unchanged |

## 7. Production substrate (post-development)

On-prem **Windows Server** (see `references/Hosting_Target_Clarification.md`):
IIS/nginx/Caddy for TLS, PostgreSQL as a Windows service, Memurai for Redis,
NSSM-wrapped services, scheduled `pg_dump` backups. Docker is dev-only.
