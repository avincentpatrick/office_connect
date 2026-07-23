# Module: Foundation (Phases 0–2)

The shared floor everything else — reimbursement included — sits on.
Nothing user-facing precedes it (`references/Phased_Rollout_Assessment.md` §3).

## 1. Scope & status

| Piece | Phase | Status |
|---|---|---|
| Dev environment (Docker, ports, health) | 0 (pre-work) | ✅ done (session 1) |
| Increment 1 — schema spine + conventions + tests | 0 | ✅ done (session 2) — 31 QA-gate tests green, adversarially reviewed |
| Increment 2 — ops: deploy, backup/restore, Celery, explicit-step migrations, git remote | 0 / Stage A | ✅ done (session 4) — proven-restore drill green, worker/beat up, pytest 31/31 |
| Increment 3 — integrations: storage/email drivers, bootstrap CLI, token contract | 0 / Stage A | not started |
| Increment 4 — spine amendments (master plan §2 Stage A) | 0 / Stage A | not started |
| Auth / RBAC / staff directory ("one login") | 2 / Stage B | not started |

> **2026-07-23:** sequencing and scope now governed by [`docs/master-plan.md`](../master-plan.md)
> (Stage A = Phase 0 increments 2–4; Stage B = Phase 2). This doc keeps the
> increment detail.

## 2. Source references

- `references/OfficeConnect_Build_Execution_Plan_v1_0.docx` §7 / §12 / §25 (Day-1 items, layout, QA gates)
- `references/Digital_Transformation_Integration_Blueprint.md` §2 (spine: `core_activity` join key, soft references)
- `references/Phased_Rollout_Assessment.md` §3 (foundation floor definition)
- `references/Hosting_Target_Clarification.md` (Windows Server prod substrate)
- Standards: [`database-standards.md`](../standards/database-standards.md) · [`development-workflow.md`](../standards/development-workflow.md)

## 3. Phase 0 build plan

*(Absorbed from the session-2 plan so the repo is self-contained; the old
out-of-repo plan file is superseded by this section.)*

### Increment 1 — schema spine + conventions + tests *(current)*

- **Package restructure** `app/` → `office_connect/` (`core/` + `modules/`
  skeleton); `APP_VERSION` in `office_connect/__init__.py`; import-linter
  contracts in `pyproject.toml` ("core never imports modules; modules never
  import each other").
- **Conventions layer** — `core/base.py`: shared `Base` with the DB standards
  §4 naming convention, `PKMixin` (BIGINT identity), `AuditColsMixin`,
  `SoftDeleteMixin`, `LookupMixin`; `core/time.py` (UTC store / Manila
  display, naive rejected).
- **Alembic** — async `env.py` (NullPool + `run_sync`), single chain,
  migration `0001_core_spine` (tables in §4 below + roles/grants + seeds).
- **Audit chain** — `core/audit.py`: session listeners write hash-chained rows
  to `core_audit_logs` atomically with each flush; `verify_chain()`;
  reconcile with CSS-IS `rechain_audit.py` at Phase 1 (repo not in workspace —
  locate before Phase 1/2).
- **Soft deletes** — `core/soft_delete.py`: global `deleted_at IS NULL`
  filter + `include_deleted` escape hatch + `soft_delete()` helper.
- **Two DB roles** — `oc_dev` (owner/migrations) and `oc_app` (runtime:
  no DELETE anywhere, no UPDATE on append-only tables).
- **`GET /api/v1/config`** — tenant identity + branding + feature flags;
  Redis-cached (30 s); **fail-safe OFF**, never 500.
- **pytest QA gates** — see §6.

### Increment 2 — ops *(revised 2026-07-23 per research — master plan §5)*

Deploy script with live-DB + version-bump + CHANGELOG guards; scheduled
`pg_dump -Fc` backup with **3-2-1 placement** (off-VM copy + periodic offline
copy) **plus one proven restore before real data exists** — the restore drill
also runs `verify_chain()` over the restored audit log (free integrity check);
wire the Celery worker service + first beat task; **migrations as an explicit
deploy step** (`alembic upgrade head` run before app start; the previously
planned migration-on-boot is demoted to a dev-only, env-gated convenience —
multi-worker boot races and crash-loop DDL are a known production failure
mode). **Also: provision the private git remote OFF the future production
hardware** (the repo + Alembic history is a disaster-recovery artifact;
required before the Phase 0 push).

### Increment 3 — integrations + bootstrap

Storage driver abstraction (S-5): Google Drive driver + Shared-Drive
verification, with local-volume driver as the likely production choice
(master plan §4 #3 — deployment-time decision); SMTP + Gmail API two-driver
email abstraction + test-email path, wired behind the notification outbox;
bootstrap CLI (first System Admin; refuses fixtures in prod) + synthetic
fixtures; design-token contract served via `/api/v1/config` (UI standards §2).

### Increment 4 — spine amendments *(new 2026-07-23 — master plan §2 Stage A)*

- `core_activities` hardening + `core_activity_tags` (GAD/CCET/DRR/UHC
  taxonomies, never boolean columns).
- `core_pap_codes` + `core_object_codes` skeletons (per-FY PREXC tree,
  effective-dated, UACS never-reuse semantics; travel = 5-02-01-010-00).
- Holiday & work-suspension calendar (`core_holidays`) — the single
  working-day engine for every deadline.
- `core_compliance_deadlines` — the statutory calendar as data (master plan
  §3.4 seed).
- Core attachments service (upload pipeline, content-addressed store,
  fail-closed downloads; ClamAV joins the compose stack).
- Notification outbox tables + in-app notification center schema.
- Report-lineage table (Blueprint Day-1 #17).
- Seed framework: idempotent, environment-aware; named owner + cadence for
  external datasets (PSGC quarterly, holiday proclamations annually,
  GRDS/threshold revisions).
- `docs/compliance/` (PIA template, processing register, breach runbook,
  retention schedule) + `docs/operations/` (runbooks) scaffolds.
- API-versioning + observability standards (structured JSON logs w/ request
  IDs; self-hosted error tracker in compose).

## 4. Spine tables (pluralized per DB standards §2)

| Table | Class | Notes |
|---|---|---|
| `core_tenant_configs` | business | name, short_name, display timezone, `branding` JSONB |
| `core_feature_flags` | lookup | `key` unique (partial, live rows), `enabled` default **false**; `is_active` retires a row, `enabled` is the flag state — a feature is ON only if both |
| `core_audit_logs` | append-only | hash chain (`prev_hash`/`row_hash`), actor, request, old/new JSONB; PK `GENERATED ALWAYS` |
| `core_query_logs` | append-only | privacy-preserving (ids/params only); populated from Phase 2 middleware |
| `core_activities` | business | join-key registry (Blueprint §2.2): title, ppa_code, division/section (BIGINT, FKs in Phase 2), dates, venue, status enum, `custom` JSONB |

## 5. Phase 2 plan (outline — detailed at its build sessions)

Shared auth patterned on CSS-IS `auth.py`/`ratelimit.py` semantics but built
per `docs/research/round1/auth-rbac-onprem.md`: Redis server-side sessions,
Argon2id, NIST 800-63B-4 password policy (length 12+ + blocklist; **no
composition rules / no forced rotation** — the reference's "letter+number"
recorded as a deviation), throttle-not-lockout, custom-header CSRF,
break-glass local admin, TOTP MFA for approver/admin roles (NPC Circular
2023-06). RBAC: permission strings + role→permission tables +
**org-unit-scoped grants**; delegation/OIC table (on-behalf-of); maker-checker
DB checks (DV Boxes A/B/C pairwise distinct); read-only **auditor role** (COA
Res. 2020-034) + printable chain-verification report. Staff directory:
**greenfield core tables seeded via CSV import from a CSS-IS export** (no code
dependency; recommended default — confirm at Stage B kickoff). Deferred FKs
(`*_by`, `division_id`, `section_id`) in one migration; query-log middleware;
audit-payload SPI policy decision executes here (master plan §4 #4).

**Open decisions (resolve before Stage B starts):**
- **`core_users` vs `core_staff`** — one identity table or auth-users vs
  staff-directory split; also settles the irregular plural ("staff").
- **Directory seed detail** — greenfield + CSV import is the recommended
  default (`references/Reimbursement_First_Dependency_Analysis.md` §7;
  master plan §4 #1).

## 6. QA gates (Phase 0)

- `alembic upgrade head` idempotent (×2)
- Every table carries its mandatory column set; append-only tables carry none
  of `updated_*`/`deleted_*`
- Audit tamper attempt detected by `verify_chain`
- `oc_app` denied UPDATE/DELETE on logs and DELETE everywhere
- Soft-delete filter + escape hatch work; soft delete produces an audit row
- UTC↔Manila round-trip; naive datetimes rejected
- `/api/v1/config` fail-safe OFF, never 500
- `lint-imports` green
- *(Increment 2 adds — all verified session 4:* one proven backup restore incl.
  `verify_chain()` on the restored DB *(the drill seeds a real ≥3-link chain
  first, so the check is never vacuously green)*; explicit-step migration proven
  from a wiped volume; dev-convenience advisory-locked boot migration; Celery
  worker/beat up with the nightly-backup task firing end-to-end; deploy guard
  passes `--mode dev` and blocks `--mode release` on the `.devN` version.)*
- *(Increment 4 adds: holiday-calendar working-day math; compliance-deadline
  seed loads; attachment pipeline round-trip incl. fail-closed download)*

## 7. Decisions log

- **2026-07-23 (Increment 2 ops — session 4)** — backup/restore + Celery +
  explicit-step migrations built and verified. Key decisions:
  - **pg client pinned to major 16** (PGDG apt, base-codename-derived) to MATCH
    the PG16 server — a *newer* pg_dump (17) emits `SET transaction_timeout`
    which a PG16 server rejects on restore, so "client newer than server" is
    NOT safe for the dump→restore round-trip. Bump the `db` image tag and the
    client together.
  - **Backups + scratch-DB create/drop run as `oc_dev`** (owner/superuser via
    `MIGRATION_DATABASE_URL`); `oc_app` is SELECT-only with no `CREATEDB`.
  - **The restore drill seeds a real audited chain first** (insert+update+
    soft_delete via `OCSession`) so `verify_chain()` walks ≥3 real links — a
    freshly-migrated DB's chain is empty and would pass vacuously. Never seeds
    when the chain is non-empty or `APP_ENV=production`.
  - **`swap_database` must render with `hide_password=False`** — SQLAlchemy's
    `str(URL)` masks the password as `***`, which broke asyncpg auth on the
    scratch-DB URL (the CLI tools were unaffected as `libpq_env` reads the raw
    `url.password`).
  - **New `office_connect/ops/` package** (backup, restore drill, deploy guard,
    dsn); a new import-linter contract keeps `core` from importing `ops`/
    `worker` (lint-imports now **3/3**).
  - **Celery broker/results on Redis db 1/2** (app config cache stays on db 0);
    the backup task is pure-subprocess (no async loop in the worker). **Beat is
    a dedicated single-replica service** — never `--scale beat`.
  - **Boot migration demoted to a dev-only, env-gated convenience**
    (`OC_MIGRATE_ON_BOOT`, default OFF) in a container **entrypoint** (once per
    container, not per uvicorn worker), advisory-locked; hard-refused when
    `APP_ENV=production`. Prod runs the explicit `alembic upgrade head` step.
  - **Deploy guard** = cross-platform Python in-container (`--mode dev|release`);
    git-tag check stays host-side; runbooks in `docs/operations/` are POSIX-sh
    authoritative (prod = Ubuntu VM), `scripts/deploy.ps1` is the dev wrapper.
  - **Private git remote = GitHub private**; off-box backup target = second/
    external disk (host-side copy step, documented). Remote is *provisioned*
    now; first push fires at the Phase 0 gate (push-per-phase).
- **2026-07-22** — 9 standing dev rules issued; naming = prefixed **plural**;
  soft deletes on all business tables (append-only exception); commit per
  session / push per phase; PK = BIGINT identity (no UUIDs); `*_by` columns
  plain BIGINT until Phase 2 FKs; audit = app-level session listeners
  (not triggers), hash payload includes app-set `created_at`.
- **2026-07-23** — Master plan v1 adopted (`docs/master-plan.md`): Increment 2
  revised (explicit-step migrations; 3-2-1 backups; off-box git remote),
  Increment 4 added (spine amendments); production substrate corrected to
  **Hyper-V Ubuntu VM + Docker Engine** (not Docker Desktop / WSL2 / native
  Windows services — see master plan §3.2 and tech-stack.md); Rule 10
  ("shared service first") adopted; core workflow engine will be built once at
  reimbursement R-4 and shared platform-wide.
- **2026-07-22 (post-review)** — floats stringified in audit payloads (jsonb
  numeric normalization would break the chain); relationships never use
  `delete-orphan`; ORM bulk UPDATE/DELETE blocked (`allow_unaudited` escape
  hatch for maintenance); degraded config payloads never cached;
  `APP_VERSION` carries a `.devN` suffix until the phase gate promotes it;
  known accepted limits: advisory lock held first-flush→commit (keep audited
  transactions short), `session.get()` identity-map hits can return
  soft-deleted objects, changing `OC_APP_PASSWORD` post-migration needs a
  manual `ALTER ROLE`.
