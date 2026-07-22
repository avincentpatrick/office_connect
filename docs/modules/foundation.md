# Module: Foundation (Phases 0–2)

The shared floor everything else — reimbursement included — sits on.
Nothing user-facing precedes it (`references/Phased_Rollout_Assessment.md` §3).

## 1. Scope & status

| Piece | Phase | Status |
|---|---|---|
| Dev environment (Docker, ports, health) | 0 (pre-work) | ✅ done (session 1) |
| Increment 1 — schema spine + conventions + tests | 0 | 🔨 in progress (session 2) |
| Increment 2 — ops: deploy, backup/restore, Celery, migration-on-boot | 0 | not started |
| Increment 3 — integrations: Drive/email drivers, bootstrap CLI, token contract | 0 | not started |
| Auth / RBAC / staff directory ("one login") | 2 | not started |

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
- **Conventions layer** — `core/base.py`: shared `Base` with the §4 naming
  convention, `PKMixin` (BIGINT identity), `AuditColsMixin`, `SoftDeleteMixin`,
  `LookupMixin`; `core/time.py` (UTC store / Manila display, naive rejected).
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

### Increment 2 — ops

Deploy script with live-DB + version-bump + CHANGELOG guards; scheduled
`pg_dump` backup **plus one proven restore before real data exists**; wire the
Celery worker service + first beat task; migration-on-boot in the app lifespan.
**Also: provision the private git remote (required before the Phase 0 push).**

### Increment 3 — integrations + bootstrap

Google Drive storage driver behind a storage abstraction (S-5) + Shared-Drive
verification; SMTP + Gmail API two-driver email abstraction + test-email path;
bootstrap CLI (first System Admin; refuses fixtures in prod) + synthetic
fixtures; design-token contract served via `/api/v1/config` (UI standards §2).

## 4. Spine tables (pluralized per DB standards §2)

| Table | Class | Notes |
|---|---|---|
| `core_tenant_configs` | business | name, short_name, display timezone, `branding` JSONB |
| `core_feature_flags` | lookup | `key` unique (partial, live rows), `enabled` default **false**; `is_active` retires a row, `enabled` is the flag state — a feature is ON only if both |
| `core_audit_logs` | append-only | hash chain (`prev_hash`/`row_hash`), actor, request, old/new JSONB; PK `GENERATED ALWAYS` |
| `core_query_logs` | append-only | privacy-preserving (ids/params only); populated from Phase 2 middleware |
| `core_activities` | business | join-key registry (Blueprint §2.2): title, ppa_code, division/section (BIGINT, FKs in Phase 2), dates, venue, status enum, `custom` JSONB |

## 5. Phase 2 plan (outline — detailed at its build sessions)

Shared auth (promote CSS-IS `auth.py` + `ratelimit.py`), RBAC, staff
directory; add the deferred FKs (`*_by`, `division_id`, `section_id`) in one
migration; query-log middleware.
**Open decisions (resolve before Phase 2 starts):**
- **`core_users` vs `core_staff`** — one identity table or auth-users vs
  staff-directory split; also settles the irregular plural ("staff").
- **Directory slice vs greenfield** — take the staff-directory slice from
  CSS-IS's data or build greenfield (`references/Reimbursement_First_Dependency_Analysis.md` §7).

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
- *(Increment 2 adds: one proven backup restore; migration-on-boot)*

## 7. Decisions log

- **2026-07-22** — 9 standing dev rules issued; naming = prefixed **plural**;
  soft deletes on all business tables (append-only exception); commit per
  session / push per phase; PK = BIGINT identity (no UUIDs); `*_by` columns
  plain BIGINT until Phase 2 FKs; audit = app-level session listeners
  (not triggers), hash payload includes app-set `created_at`.
