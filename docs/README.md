# docs/ — Project Documentation Index

Our own **project documentation, plans, and notes**. For the source-of-truth
reference material we were given (execution plan `.docx` + companion specs),
see [`../references/`](../references/) — that folder is **read-only, never
edited**.

## Standards (binding conventions)

| Doc | Purpose | Update when |
|---|---|---|
| [`standards/development-workflow.md`](standards/development-workflow.md) | Session lifecycle, session-end checklist, next-prompt format, git strategy (commit/session, push/phase) | Process changes |
| [`standards/database-standards.md`](standards/database-standards.md) | Naming (prefixed plural), keys, mandatory audit/soft-delete columns, time, money, JSONB, ref numbers, migration rules | Any schema-convention decision, same session |
| [`standards/ui-standards.md`](standards/ui-standards.md) | Design tokens, component inventory, layout templates, copy, WCAG AA (LOCKED/DEFERRED tagged) | Any UI decision, same session |
| [`standards/tech-stack.md`](standards/tech-stack.md) | Every language / dependency / image / tool, versioned | Any dependency change, same session |

## Modules (rule 8 — one doc per main module)

| Doc | Content today | Phase slot |
|---|---|---|
| [`modules/foundation.md`](modules/foundation.md) | **REAL** — Phase 0 increments, spine tables, QA gates, Phase 2 outline | 0–2 |
| [`modules/reimbursement.md`](modules/reimbursement.md) | **REAL** — delta register vs spec, R-0 tracker, R-phase status | R-0…R-9 |
| [`modules/landing.md`](modules/landing.md) | scaffold | 3 |
| [`modules/dmwis.md`](modules/dmwis.md) | scaffold | 4–7 |
| [`modules/css-is.md`](modules/css-is.md) | scaffold | 1/8 |
| [`modules/admin.md`](modules/admin.md) | scaffold | 9 |
| [`modules/reports.md`](modules/reports.md) | scaffold | 9 (+ Day-1 lineage) |

Scaffolds carry status, purpose, source references, **integration
obligations** (so cross-module promises survive until their build sessions),
and open decisions; their Plan sections are filled at each module's
requirements session.

## Root-level

| Doc | Purpose |
|---|---|
| [`../CLAUDE.md`](../CLAUDE.md) | AI session contract — distilled rules, loaded every session |
| [`../PROGRESS.md`](../PROGRESS.md) | Current status, next-session prompt, phase tracker, session log |
| [`../CHANGELOG.md`](../CHANGELOG.md) | User-visible changes; versions align to phases |
