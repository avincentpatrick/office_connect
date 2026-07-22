# Module: Local Travel Reimbursement

First user-facing module (author decision, `references/Phased_Rollout_Assessment.md` §0.1).

## 1. Source of truth

**The build spec is [`references/Reimbursement_Module_Build_Spec_v1.md`](../../references/Reimbursement_Module_Build_Spec_v1.md)
— read it before any R-phase work.** This file records only status, decisions,
and deltas; it never duplicates the spec.

Feature flag: `module.reimbursement` (fail-safe OFF) · Ref numbers:
`RB-YYYY-NNNN` (claims), `LQ-YYYY-NNNN` (liquidations) · Namespace: `reimb_*`.

## 2. Delta register *(spec says → we implement → why)*

| Spec says | We implement | Why |
|---|---|---|
| Singular table names (`reimb_claim`, …) | **Pluralized**: `reimb_configs`, `reimb_claims`, `reimb_cash_advances`, `reimb_itinerary_legs`, `reimb_checklist_catalogs`, `reimb_checklist_items`, `reimb_approval_steps`, `reimb_signatory_configs`, `reimb_return_reason_catalogs`, `reimb_return_events`, `reimb_attachments`, `reimb_status_histories`, `reimb_external_events`, `reimb_template_maps` | DB standards §2 (standing rule 7) |
| `created/updated` shorthand columns | Full mandatory set: `created_at/created_by/updated_at/updated_by` + `deleted_at/deleted_by`; catalogs also `is_active` | DB standards §6 (rules 5+6) |
| — (no immutability note) | `reimb_status_histories`, `reimb_return_events`, `reimb_external_events` are **append-only class**: `created_*` only, `REVOKE UPDATE` from `oc_app` in their migration | DB standards §6 append-only exception |
| `ref_no` unique | **Partial** unique index `WHERE deleted_at IS NULL`; numbers never reused even after soft delete | DB standards §8/§12 |
| — | Every FK column named `<singular>_id` per DB standards §3 | rule 7 |

*(Grows as build proceeds — every divergence from the spec lands here.)*

## 3. R-0 confirmations tracker (spec §15 — user decisions)

- [ ] 30-day liquidation clock: calendar vs working days; COA circular basis
- [ ] Signatory / certification chain (A/B/C) per amount tier
- [ ] Wet-signature capture points vs digital approvals
- [ ] Directory data: slice from CSS-IS vs greenfield (shared with Phase 2 — see `foundation.md` §5)
- [ ] HUC (highly urbanized city) list for per-diem rules

## 4. R-phase status

| Phase | Scope | Status | QA | Sessions |
|---|---|---|---|---|
| R-0 | Requirements / author decisions | not started | — | — |
| R-1 | Schema + config | not started | — | — |
| R-2 | Claim wizard | not started | — | — |
| R-3…R-9 | Per spec §14 | not started | — | — |

## 5. Decisions log

- **2026-07-22** — Module doc created; delta register seeded with the
  plural-naming and mandatory-column deltas (standing rules 5–7).
