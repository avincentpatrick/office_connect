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
| google-api-python-client | 2.156.0 | Google Drive storage driver + Gmail email driver (Increment 3); pure-Python |
| google-auth | 2.37.0 | Service-account credentials for the Google drivers |
| google-auth-httplib2 | 0.2.0 | httplib2 transport the Google API client uses |
| Pillow | 11.1.0 | Attachments (Increment 4): image re-encode + EXIF/XMP strip; self-contained wheels (no apt) |
| pillow-heif | 0.21.0 | Attachments: HEIC/HEIF decode → JPEG normalization; bundles libheif |
| clamd | 1.0.2 | Attachments: pure-Python ClamAV TCP client (lazy-imported; scanner is injectable + fail-closed) |
| sentry-sdk | 2.20.0 | Observability (Increment 4): error tracking (GlitchTip-compatible); lazy-imported, active only with `SENTRY_DSN` |
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
| `app` | built from `Dockerfile` | 8001 | uvicorn `office_connect.main:app`; 8000 is Laragon's; entrypoint runs the dev-only env-gated boot migration |
| `worker` | same image | — | Celery worker (`office_connect.worker.celery_app`); runs the nightly `pg_dump` backup task; carries the owner DSN; `restart: unless-stopped` |
| `beat` | same image | — | Celery beat scheduler — **single instance only** (never scale; duplicate schedulers = duplicate backups); schedule state on volume `beatdata`. Inc-4 adds the `scan-pending-attachments` beat task |
| `clamav` | clamav/clamav:1.4 | — (internal) | **Profile `clamav`** (not in default `up`/CI). Attachments malware scan; `mem_limit ~3g`; signature DB on volume `clamdb`; no host port (prod publishes only 443). Enable: `CLAMAV_HOST=clamav docker compose --profile clamav up -d` |
| `glitchtip` (+ `glitchtip-db`, `glitchtip-worker`) | glitchtip/glitchtip:v4.0, postgres:16-alpine | 8080 (dev only) | **Profile `observability`** (not in default stack). Self-hosted error tracker (Sentry-SDK compatible); own PG volume `glitchtip_pg`, Redis db 3. App/worker emit only when `SENTRY_DSN` is set. Full hardening = Stage C |

Increment-4 env (app + worker): `ATTACHMENT_SCANNER`/`CLAMAV_HOST`/`CLAMAV_PORT`
(empty host → fail-closed `NullScanner`), `NOTIFICATIONS_DISPATCH` (`inline`|
`celery`; app defaults `celery`, CLI/tests `inline`), `LOG_JSON`, `SENTRY_DSN`,
`ATTACHMENT_MAX_BYTES`.

Celery uses the **Redis transport** (already-pinned `redis` package — no
`celery[redis]` extra needed): broker on Redis logical **db 1**, results on
**db 2**, so the app config cache (db 0) never collides.

Port deconfliction with the coexisting Laragon `dev_pims` app: Laragon owns
80/3306/8000/5173/6379; Office-Connect uses 8001/5432/6380 (+5174 for Vite later).

**Image system dependencies** (`Dockerfile`, beyond `requirements.txt`):

| Package | Source | Purpose |
|---|---|---|
| `postgresql-client-16` | PGDG apt (suite = base image codename) | `pg_dump`/`pg_restore`/`createdb`/`dropdb` for backup + restore drill. Client MAJOR must **match** the PG16 server (a newer client emits SET commands PG16 rejects on restore). Bump with the `db` image tag. |

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
| `scripts/deploy.ps1` | Dev deploy wrapper (backup → guard → migrate → up); mirrors `docs/operations/deploy.md` (authoritative POSIX-sh prod runbook) |
| `scripts/entrypoint.sh` | Container entrypoint; dev-only env-gated advisory-locked boot migration then execs the service command |
| `office_connect.ops` CLI | `python -m office_connect.ops {backup,restore-drill,backup-and-drill,scan-pending}` + `office_connect.ops.deploy_guard` + `office_connect.ops.bootstrap {init,create-admin,load-fixtures,load-reference,send-test-email}` (Inc 4 adds `scan-pending` + `load-reference`) |
| Git | Local commits per session; push + tag per phase (see `development-workflow.md` §4) |
| Claude Code (AI assistant) | Pair-builds the project; session contract in `CLAUDE.md` |

## 6. External services

| Service | Role | Status |
|---|---|---|
| Google Drive API | Storage driver (Shared-Drive target; local volume is the prod default) | **Built** Increment 3 (`core/storage/gdrive.py`) |
| SMTP | Email driver — the on-prem default transport (stdlib `smtplib`) | **Built** Increment 3 (`core/email/smtp.py`) |
| Gmail API | Alternate email driver (Workspace domain-wide delegation) | **Built** Increment 3 (`core/email/gmail.py`) |
| ClamAV | Attachments malware scan (fail-closed) | **Built** Increment 4 (`core/attachments/scanner.py`); opt-in compose profile `clamav`; offline signature mirror (`cvdupdate`) deferred to Stage C |
| GlitchTip | Self-hosted error tracker (Sentry-SDK compatible) | **Wired** Increment 4 (compose profile `observability`, fail-safe optional `SENTRY_DSN`); full hardening Stage C |
| Google Docs API | Template assembly (plan S-5) | Deferred to the template→PDF service |
| Hugging Face Space | Legacy CSS-IS host until its migration (Phases 1/8) | External, unchanged |

## 7. Production substrate (post-development)

On-prem **Windows Server** (see `references/Hosting_Target_Clarification.md`).

**Revised 2026-07-23 (research — `docs/research/round1/onprem-windows-server-ops.md`;
master plan §3.2):** Windows Server acts as the **Hyper-V host only**; the stack
runs in an **Ubuntu LTS VM with Docker Engine + Compose** (same containers as
dev). The earlier sketch (PostgreSQL as a Windows service, Memurai, NSSM
wrappers) is superseded — rationale:

- Linux containers cannot run natively on Windows Server; LCOW is removed from
  Docker 23+; WSL2 has no production-support statement and fragile boot
  autostart.
- **Docker Desktop requires a paid subscription for government entities** —
  Docker Engine in a Linux VM is Apache-2.0.
- Memurai needs a commercial license for production; Redis in the VM does not.
- Unattended-boot chain uses only built-ins: Hyper-V Automatic Start Action →
  systemd → `restart: unless-stopped` (power-cycle-tested before go-live).

Only 443 is published, via Caddy/nginx with an internal cert (AD CS via GPO
preferred; Caddy internal CA fallback). Postgres/Redis stay on the
compose-internal network. Backups: nightly `pg_dump -Fc` + 3-2-1 placement,
graduating to pgBackRest + WAL archiving before real claims if a sub-24 h RPO
is demanded. Exact VM/OS/engine versions recorded here at deployment
provisioning (rule 9).
