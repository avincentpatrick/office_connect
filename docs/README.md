# docs/ — Project Documentation Index

Our own **project documentation, plans, and notes**. For the source-of-truth
reference material we were given (execution plan `.docx` + companion specs),
see [`../references/`](../references/) — that folder is **read-only, never
edited**.

## Master plan

| Doc | Purpose |
|---|---|
| [`master-plan.md`](master-plan.md) | **Authoritative build plan (v1, 2026-07-23)** — consolidates the references + amendments + research + owner modules: connectedness contract & core-services registry, stage sequence A–I + Wave 2, compliance/ops/training tracks, statutory calendar, open decisions, reference-corrections ledger |
| [`research/index.md`](research/index.md) | 18 deep-research digests (2 rounds) with sources — the citations behind the master plan and module deltas |

## Standards (binding conventions)

| Doc | Purpose | Update when |
|---|---|---|
| [`standards/development-workflow.md`](standards/development-workflow.md) | Session lifecycle, session-end checklist, next-prompt format, git strategy (commit/session, push/phase) | Process changes |
| [`standards/database-standards.md`](standards/database-standards.md) | Naming (prefixed plural), keys, mandatory audit/soft-delete columns, time, money, JSONB, ref numbers, migration rules | Any schema-convention decision, same session |
| [`standards/ui-standards.md`](standards/ui-standards.md) | Design tokens, component inventory, layout templates, copy, WCAG AA (LOCKED/DEFERRED tagged) | Any UI decision, same session |
| [`standards/tech-stack.md`](standards/tech-stack.md) | Every language / dependency / image / tool, versioned | Any dependency change, same session |

## Modules (rule 8 — one doc per main module)

| Doc | Content today | Stage (old phase) |
|---|---|---|
| [`modules/foundation.md`](modules/foundation.md) | **REAL** — Phase 0 increments 1–4, spine tables, QA gates, Stage B outline | A–B (0–2) |
| [`modules/reimbursement.md`](modules/reimbursement.md) | **REAL** — delta register vs spec + research corrections, R-0 tracker, R-phase status | C (R-0…R-9) |
| [`modules/landing.md`](modules/landing.md) | scaffold (+ Calendar of Activities surface) | D (3) |
| [`modules/document-tracking.md`](modules/document-tracking.md) | scaffold — **DTWIS, renamed from DMWIS 2026-07-22** | E (4–7) |
| [`modules/qms.md`](modules/qms.md) | scaffold — controlled documents · risk registry · management review | F (new) |
| [`modules/css-is.md`](modules/css-is.md) | scaffold (+ ARTA CSM v2023 corrections) | G (1/8) |
| [`modules/admin.md`](modules/admin.md) | scaffold | H (9) |
| [`modules/reports.md`](modules/reports.md) | scaffold (+ Government Outputs / transparency pack) | H (9, + Day-1 lineage) |
| [`modules/planning-budget.md`](modules/planning-budget.md) | scaffold — WFP/BED/BAR + PPMP/APP | W2-A (new) |
| [`modules/supply.md`](modules/supply.md) | scaffold — GAM supply/property management | W2-B (new) |
| [`modules/performance.md`](modules/performance.md) | scaffold — SPMS + accomplishments + COA findings | W2-C (new) |

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
