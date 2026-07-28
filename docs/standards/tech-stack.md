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
| TypeScript / React | TS 5.9.3 · React 19.2.8 | Frontend (`web/` Vite SPA — R-2-shell, 2026-07-28) | `web/package.json` (exact pins, `.npmrc save-exact`) |
| Node.js | **22 LTS** | FE toolchain runtime (Vite dev server + build) | `docker-compose.yml` (`node:22-alpine`) + `web/package.json` `engines` (`>=22 <23`, `engine-strict`) |

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
| python-multipart | 0.0.20 | Multipart/form-data parsing (Stage B / Inc 4): required by FastAPI for the attachments upload router and the directory CSV-import route (any endpoint declaring `File()`/`Form()`). Pure-Python |
| sentry-sdk | 2.20.0 | Observability (Increment 4): error tracking (GlitchTip-compatible); lazy-imported, active only with `SENTRY_DSN` |
| argon2-cffi | 23.1.0 | Auth (Stage B): Argon2id password hashing (`core/security/password.py`). **Cost params: `time_cost=2`, `memory_cost=19 MiB (19456 KiB)`, `parallelism=1`** (OWASP / RFC 9106 option 2, on-prem-sized). Self-contained manylinux wheels (no apt). PHC hash self-describes cost → raise deliberately + re-hash on next login |
| pyotp | 2.9.0 | Auth (Stage B / Inc 2): TOTP MFA (RFC 6238) for approver/admin roles (NPC Circular 2023-06). Pure-Python; returns the `otpauth://` provisioning URI so the client renders the QR — **no QR-image dependency** server-side. `valid_window=1` (±30 s skew); a used code is single-use within its step (Redis `SETNX`) |
| pytest | 8.3.4 | Test runner (QA gates) |
| pytest-asyncio | 0.24.0 | Async test support |
| asgi-lifespan | 2.1.0 | Runs FastAPI lifespan under httpx `ASGITransport` in tests |
| import-linter | 2.1 | Enforces "modules import core, never each other" (`pyproject.toml`) |
| tzdata | 2024.2 | IANA zoneinfo data for slim images / Windows hosts |

**Vendored package data (no runtime cloud call):** the NIST 800-63B-4 password
blocklist — SecLists `Pwdb_top-100000.txt` (100k entries) — is committed **gzipped**
at `office_connect/core/security/blocklists/top-100000.txt.gz` (~432 KB; provenance
+ SHA-256 in the sibling `README.md`, marked binary + `linguist-vendored` in
`.gitattributes`). Loaded lazily into a normalized `frozenset` on first check.

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
| `web` | node:22-alpine | **5174** | Vite dev server (R-2-shell, default profile). `npm install` at boot (no-op when the lockfile is unchanged — exact pins); `node_modules` on named volume `web_node_modules` (never the Windows bind mount); `CHOKIDAR_USEPOLLING` for HMR through the bind mount; proxies `/api` → `app:8001` (same-origin contract — **no CORS by design**, api-standards §6) |

Increment-4 env (app + worker): `ATTACHMENT_SCANNER`/`CLAMAV_HOST`/`CLAMAV_PORT`
(empty host → fail-closed `NullScanner`), `NOTIFICATIONS_DISPATCH` (`inline`|
`celery`; app defaults `celery`, CLI/tests `inline`), `LOG_JSON`, `SENTRY_DSN`,
`ATTACHMENT_MAX_BYTES`.

Celery uses the **Redis transport** (already-pinned `redis` package — no
`celery[redis]` extra needed): broker on Redis logical **db 1**, results on
**db 2**, so the app config cache (db 0) never collides.

**Redis logical-DB map:** db 0 = app config cache · db 1 = Celery broker · db 2 =
Celery results · db 3 = GlitchTip (observability profile) · **db 4 = auth sessions
+ throttle + pending-MFA + the RBAC permission cache** (Stage B / Inc 2–3,
`SESSION_REDIS_DB`; a dedicated client on `app.state.session_redis`). db 4 was chosen
over the brief's db 3 to avoid the GlitchTip keyspace when the observability profile
runs — no `docker-compose` change. The B3 permission cache reuses the same client
(`app.state.permission_cache`), keys `authz:perm:{uid}:v{permissions_version}`.

Port deconfliction with the coexisting Laragon `dev_pims` app: Laragon owns
80/3306/8000/5173/6379; Office-Connect uses 8001/5432/6380/**5174 (Vite, active
since R-2-shell)**.

**Image system dependencies** (`Dockerfile`, beyond `requirements.txt`):

| Package | Source | Purpose |
|---|---|---|
| `postgresql-client-16` | PGDG apt (suite = base image codename) | `pg_dump`/`pg_restore`/`createdb`/`dropdb` for backup + restore drill. Client MAJOR must **match** the PG16 server (a newer client emits SET commands PG16 rejects on restore). Bump with the `db` image tag. |

## 4. Frontend stack (`web/package.json`) — FILLED (R-2-shell, 2026-07-28)

**React 19 + Vite 6 + Tailwind 4 + TypeScript**, tokens-only styling per
[`ui-standards.md`](ui-standards.md) §7. Every dependency exact-pinned
(`.npmrc`: `save-exact=true`, `engine-strict=true`); Node pinned to **22 LTS**
(§1). All npm commands run via the `web` container — no host Node required.

**Runtime dependencies:**

| Package | Version | Purpose |
|---|---|---|
| react / react-dom | 19.2.8 | UI runtime |
| react-router | 7.18.1 | Routing (library mode — `createBrowserRouter`; no SSR/framework mode) |
| @tanstack/react-query | 5.101.4 | Server-state layer: config/me caching, mutation states, global 401 handling; carries the wizard's save-and-return next session |
| radix-ui | 1.6.7 | Headless a11y primitives (Dialog, Tabs, Toast) — the ONE primitive library; allowed only inside `web/src/components/` |
| lucide-react | 1.27.0 | **The** platform icon set (ui-standards §7); per-icon imports |

**Dev dependencies:**

| Package | Version | Purpose |
|---|---|---|
| vite | 6.4.3 | Dev server (:5174, `/api` proxy) + production bundler |
| @vitejs/plugin-react | 4.7.0 | React fast-refresh + JSX transform |
| typescript | 5.9.3 | Strict type checking (`tsc -b`) |
| tailwindcss + @tailwindcss/vite | 4.3.3 | Utility CSS on the `--oc-*` tokens (v4 CSS-first `@theme inline`) |
| @types/react / @types/react-dom | 19.2.17 / 19.2.3 | React typings |
| @types/node | 22.20.1 | Node typings (vite.config) |
| vitest | 3.2.7 | FE test runner (jsdom env) |
| jsdom | 30.0.0 | DOM for tests |
| @testing-library/react | 16.3.2 | Component testing |
| @testing-library/jest-dom | 7.0.0 | DOM matchers |
| @testing-library/user-event | 14.6.1 | Interaction simulation |
| axe-core | 4.12.1 | A11y assertions in component tests (`src/test/a11y.ts`; color-contrast covered server-side by `tests/test_tokens.py`) |
| eslint + @eslint/js | 9.39.5 | Lint (flat config) |
| typescript-eslint | 8.65.0 | TS lint rules |
| eslint-plugin-react-hooks | 7.1.1 | Hooks + React-compiler-era rules |
| eslint-plugin-react-refresh | 0.5.3 | HMR-safety (only-export-components) |
| eslint-plugin-jsx-a11y | 6.10.2 | Static a11y lint |
| eslint-config-prettier | 10.1.8 | Disables style rules Prettier owns |
| prettier | 3.9.6 | Formatting |
| globals | 17.8.0 | Browser globals for the lint config |

**Deliberate exclusions (recorded deferrals):** no axios (native `fetch` via
the one wrapper `web/src/api/http.ts`); no Storybook (`/ui-foundation` DEV
catalog instead — ui-standards §7); no state library; no form library
(react-hook-form/zod decision belongs to the wizard session); no QR renderer
for MFA enrollment (manual secret entry until the admin finds it painful).

## 5. Dev & QA tooling

| Tool | Purpose |
|---|---|
| Docker Desktop + WSL2 | Dev containers on Windows 11 |
| pytest (+ pytest-asyncio, asgi-lifespan, httpx) | Phase QA gates (backend) |
| import-linter (`lint-imports`) | Architecture contract enforcement |
| **FE QA gate** (`web/` npm scripts) | `docker compose run --rm web sh -c "npm run lint && npm run typecheck && npm run test && npm run build"` — eslint + `tsc -b` + vitest + production build; paired with the backend gates |
| Prettier (`npm run format` / `format:check`) | FE formatting |
| Alembic CLI | Migrations (runs as `oc_dev` via `MIGRATION_DATABASE_URL`) |
| `scripts/setup-windows.ps1` | One-time elevated prerequisites installer |
| `scripts/smoke-test.ps1` | Build + health-check the stack |
| `scripts/deploy.ps1` | Dev deploy wrapper (backup → guard → migrate → up); mirrors `docs/operations/deploy.md` (authoritative POSIX-sh prod runbook) |
| `scripts/entrypoint.sh` | Container entrypoint; dev-only env-gated advisory-locked boot migration then execs the service command |
| `office_connect.ops` CLI | `python -m office_connect.ops {backup,restore-drill,backup-and-drill,scan-pending}` + `office_connect.ops.deploy_guard` + `office_connect.ops.bootstrap {init,create-admin,load-fixtures,load-reference,seed-rbac,promote-admin,send-test-email}` (Stage B adds `seed-rbac` + `promote-admin`) |
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
