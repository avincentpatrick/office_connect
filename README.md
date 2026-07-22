# Office-Connect

Configurable multi-tenant government workplace platform (BLHSD/DOH reference tenant).
See [`references/`](references/) for the execution plan and companion specs — the
`.docx` is the single source of truth for scope/sequence. Our own documentation,
plans, and notes live in [`docs/`](docs/) (index: [`docs/README.md`](docs/README.md)).

**Start here each session:** [`CLAUDE.md`](CLAUDE.md) (standing rules) and the
top of [`PROGRESS.md`](PROGRESS.md) (current status + next-session prompt).
Binding conventions live in [`docs/standards/`](docs/standards/).

- **Stack:** FastAPI · PostgreSQL · Redis · Celery · React/Vite (later phases)
- **Dev host:** Docker Desktop on Windows
- **Production host:** on-prem **Windows Server** (post-development) —
  see [`references/Hosting_Target_Clarification.md`](references/Hosting_Target_Clarification.md).
  CSS-IS (Module 1) stays on Hugging Face and is migrated in.

---

## One-time machine setup

Prerequisites are installed by a script that needs **administrator** rights.

1. Open **PowerShell as Administrator**, `cd` to this folder, and run:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\setup-windows.ps1
   ```
   This installs **WSL2**, **Docker Desktop**, and (optional) host **Python 3.12**.
2. **Reboot.**
3. Launch **Docker Desktop** once, accept the terms, and wait for the engine to
   finish starting (tray whale icon steady).

Nothing here changes your existing Laragon / `dev_pims` environment.

## Daily development

```powershell
docker compose up -d --build     # start db + redis + api
docker compose logs -f app       # tail the API
docker compose down              # stop (keeps the DB volume)
docker compose down -v           # stop and wipe the DB volume
```

Verify everything is wired correctly:

```powershell
.\scripts\smoke-test.ps1
```

A healthy stack responds at:

| Service | Host URL | Notes |
|---|---|---|
| API | http://localhost:8001 | interactive docs at `/docs`, health at `/health` |
| PostgreSQL | localhost:5432 | db `office_connect`, user `oc_dev` |
| Redis | localhost:6380 | container port 6379 published to host 6380 |

## Coexistence with Laragon (`dev_pims`)

Ports are deliberately chosen so both projects run side by side. Nothing overlaps:

| | `dev_pims` (Laragon) | Office-Connect (this project) |
|---|---|---|
| Web | `php artisan serve` **:8000**, Apache 80/443 | API **:8001** |
| Database | MySQL **:3306** | PostgreSQL **:5432** |
| Redis | configured **:6379** | **:6380** |
| Frontend | Vite **:5173** | Vite **:5174** (later) |

MySQL vs PostgreSQL and PHP vs Python don't interact — the two stacks are fully
isolated. You rarely need both running at once; this machine's 32 GB RAM handles
it if you do.

## Layout

```
office_connect/
  main.py            FastAPI app + /health + /api/v1 (config endpoint)
  core/              platform spine — config, db (oc_app role), base
                     (naming convention + audit/soft-delete mixins), time
                     (UTC/Manila), audit (hash chain), soft_delete (global
                     filter), models/ (core_* tables), api/
  modules/           feature modules (reimbursement, ...) — import core only
alembic/             single migration chain (0001 = core spine + roles/grants)
tests/               Phase-0 QA gates (run: docker compose exec app pytest -q)
docker-compose.yml   db (postgres:16) + redis + app
Dockerfile           python:3.12 API image
pyproject.toml       import-linter contracts + pytest config
requirements.txt     runtime + QA deps
scripts/
  setup-windows.ps1  one-time elevated prerequisites installer
  smoke-test.ps1     build, start, and health-check the stack
.env / .env.example  local config (real .env is git-ignored)
references/          execution plan + companion specs (read-only source)
docs/                standards + module docs (see docs/README.md)
```

Phase 0 Increment 1: the schema spine (audit chain, feature flags, soft
deletes, activities registry) with its QA gates. Modules build on top per
[`docs/modules/`](docs/modules/).
