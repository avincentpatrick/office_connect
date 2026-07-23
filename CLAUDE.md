# CLAUDE.md — Office-Connect session contract

## Project snapshot

Configurable multi-tenant government workplace platform (BLHSD/DOH reference
tenant). Backend: FastAPI + async SQLAlchemy 2.0 + PostgreSQL 16 + Redis +
Celery; frontend React/Vite/Tailwind in later phases. Dev = Docker on Windows
(ports **8001/5432/6380**, coexisting with Laragon `dev_pims` on 8000/3306/6379).
Production = on-prem **Windows Server**, post-development. First user-facing
module: **Local Travel Reimbursement**, built on the Phase 0–2 foundation floor.

## Start-of-session ritual

**Read the top of `PROGRESS.md` first.** The *Current Status* block and the
*Next Session Prompt* say exactly where to resume. Never start work without
them; confirm the prompt with the user.

**▶ To resume (one line):** open [`PROGRESS.md`](PROGRESS.md) and copy the single
line under **▶ RESUME** at the top — e.g. *"Resume Office-Connect — Stage A
Increment 3"* — and paste it as your first message. That is all you paste.
Claude then reads *Current Status* + the **▶ NEXT SESSION PROMPT** brief (rule 3;
the detailed, self-contained task/acceptance/files spec) plus the cited module
docs, expands the one line into the full task, and confirms before starting.
**Every session must end by refreshing both the RESUME line and the brief** —
that is the guaranteed hand-off, not an optional courtesy.

## Doc map & precedence

| Where | What |
|---|---|
| `references/` | Given source material — **READ-ONLY, never edit**. Uses *singular* table names (historical). |
| `docs/master-plan.md` | **Authoritative build plan v1** — stages A–I + Wave 2, connectedness contract, core-services registry, corrections ledger. |
| `docs/standards/` | Binding conventions (DB, UI, workflow, tech stack). |
| `docs/modules/` | Per-module plan + status + delta register. |
| `docs/research/` | 18 deep-research digests behind the plan (cited by delta registers). |
| `PROGRESS.md` | Current status, stage tracker, session log, next prompt. |
| `CHANGELOG.md` | User-visible changes; `[Unreleased]` → version per phase. |

Precedence on conflict: **standing rules → docs/standards/ → master-plan.md →
references/ module specs → the `.docx` execution plan** (scope/sequence only).

## The 10 standing rules (1–9 locked 2026-07-22; 10 locked 2026-07-23)

1. **Uniform UI** — every element from the shared component inventory & layout templates → `docs/standards/ui-standards.md`
2. **Document every session** — all work lands in the relevant `.md` + progress tracker at session end → `development-workflow.md` §2
3. **Next Session Prompt** — written at every session end → `development-workflow.md` §3
4. **Git per phase** — commit locally per session; push + tag only at phase QA gates → `development-workflow.md` §4
5. **Everything auditable** — ownership columns + hash-chained `core_audit_logs` → `database-standards.md` §7
6. **Soft deletes always** — `deleted_at`/`deleted_by`; app role has no DELETE → `database-standards.md` §8
7. **DB naming standards** — prefixed plural tables, `<singular>_id` FKs → `database-standards.md` §2–§4
8. **Per-module docs** — every main module has `docs/modules/<module>.md`
9. **Documented tech stack** — every dependency/tool recorded → `tech-stack.md`
10. **Shared service first** — one core workflow engine for every approval flow;
    check the core-services registry before adding any table/service; duplication
    needs a documented waiver → `development-workflow.md` §5a + `master-plan.md` §1

## DB quick card

- Tables: `<prefix>_<plural>` — `core_users`, `reimb_claims`. Prefixes:
  `core_ / reimb_ / css_ / dtwis_ / admin_ / qms_ / supply_ / plan_ / perf_`
  (`dtwis_` renamed from `dmwis_` 2026-07-22).
- PK `id` BIGINT identity · FK `<singular>_id` (`role_id → core_roles.id`).
- Business tables: `created_at/created_by/updated_at/updated_by` +
  `deleted_at/deleted_by`. Lookups: + `is_active`. Append-only logs:
  `created_*` only (documented exception).
- `timestamptz` UTC only (display Manila via `core/time.py`); money
  `numeric(12,2)`; ref numbers `XX-YYYY-NNNN`, never reused.
- **Reference specs use singular names — pluralize on implementation** and
  record the delta in the module doc.
- Never hard DELETE; `oc_app` role physically cannot.

## UI quick card

Tokens only (no raw hex/px) · components only from the inventory · pages only
from the layout templates · GOV.UK task-list for checklists · WCAG AA ·
semantic status colors (green done / amber due / red blocked / grey waiting).

## Git strategy

Local commit at every session end (`session(YYYY-MM-DD): summary`); logical
mid-session commits encouraged. Push + tag `phase-N-complete` **only** when a
phase's QA gate passes. No remote yet — provision before Phase 0 closes.

## Session-end checklist (MANDATORY — full version: development-workflow.md §2)

1. Update `PROGRESS.md` (entry + Current Status + phase tracker)
2. Update touched `docs/modules/*.md`
3. Update standards/tech-stack docs if triggered
4. Update `CHANGELOG.md` `[Unreleased]`
5. Refresh the **▶ RESUME** line + **▶ NEXT SESSION PROMPT** brief (top of `PROGRESS.md`)
6. Local git commit — a session is not over until this lands

## Hard prohibitions

- No hard deletes, anywhere, ever.
- No edits under `references/`.
- No naive datetimes (`ensure_aware()` raises).
- No client-side money math — server computes, UI displays.
- Feature flags fail-safe **OFF**; `/api/v1/config` never 500s.
- No cross-module imports (`lint-imports` must stay green); modules import
  `core`, never each other.
- No UI outside the token/component/template system.
- No skipping the session-end checklist; no pushing mid-phase.
