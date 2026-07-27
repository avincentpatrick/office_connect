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
| Per diem `₱2,200 metro_manila_huc / ₱1,800 other` (spec §4) | **EO 77 Annex A 3-cluster DTE by destination region**: I ₱1,500 · II ₱1,800 · III ₱2,200; per-day rate follows that day's destination cluster; `reimb_dte_clusters` + PSGC region map, **effective-dated config** | Research correction — `docs/research/round1/ph-travel-reimbursement-rules.md` |
| (spec silent) | Per-day **host-provided lodging/meals flags** (strip 50 %/30 %), **gov-vehicle flag** per leg (suppresses fare), **excess-claim path** (agency-head necessity cert + receipts, capped), **affidavit-of-loss never satisfies the lodging-OR item** (hard block), 50-km rule needs official-station + overnight-stay attestation | COA disallowance patterns — same digest |
| Checklist seeded from FS-BD-01 vs COA 2012-001 | Checklist catalog **versioned to COA Circular 2023-004** (updates 2012-001 §1.2.4.1); CA-grant set includes the Chief-Accountant no-unliquidated-CA certification as a **DB-enforced block** (PD 1445 §89), not a warning | same digest |
| "Appendix A/B" (FS-BD-01 internal labels) | Generated PDFs print-faithful to **GAM Vol II**: App 32 DV · App 44 Liquidation Report · **App 45 Itinerary of Travel** · App 46 RER · App 47 Certificate of Travel Completed | GAM 2015 numbering — same digest |
| Approved IoT is the only itinerary | **Revised IoT as a new version** (justification required) when actuals deviate; CTC text discloses the deviation | COA liquidation requirement |
| Module-internal approval steps (`reimb_approval_steps`) behind narrow interfaces | Chain runs on the **shared core workflow engine** (`core_workflow_*`, **built 2026-07-27** as pure core — R-4 core pulled forward; reimbursement is its first *definition* at R-4-app); delegation/OIC + versioned definitions come free | Owner decision 2026-07-22 + Rule 10 — supersedes the spec's reconciliation-debt approach. Contract: `docs/standards/workflow-standards.md` |
| `reimb_attachments` self-contained | Rides the **core attachments service** (validation/scan/store) with a module join table; retention_class = 10-yr financial records (GRDS 2023) | Rule 10 + records-retention research |
| `reimb_approval_step` + `reimb_signatory_config` runtime tables (R-1) | **DROPPED / DEFERRED (R-1, 2026-07-27):** per-step runtime rows ARE `core_workflow_steps`; the signatory chain IS the workflow definition (authored at R-4-app). `reimb_approval_steps` dropped; `reimb_signatory_configs` deferred to R-4-app. | Rule 10 — don't duplicate the engine |
| `reimb_template_map` (R-1) | **DEFERRED to R-5** (templates) / candidate for the shared document-taxonomy registry (core-service #13) | Rule 10 — R-1 is schema+config only |
| `destination_class ENUM(metro_manila_huc, other)` on the claim | **Replaced** by `destination_region_code` (PSGC) on claim + per leg; rate class resolves via `reimb_region_clusters` → `reimb_dte_clusters` | EO 77 3-cluster delta |
| Ref numbers via a per-module strategy (spec §16) | Built as the **core reference-number service #5** (`core_reference_sequences` + `core/reference_numbers.py::allocate_reference_number`, `XX-YYYY-NNNN`, yearly reset, never reused) — all modules consume it | Rule 10 — it was unbuilt; reimb is first consumer |
| §4 config pack as constants | `reimb_configs` (effective-dated key rows with legal `source`) + `reimb_dte_clusters` + `reimb_region_clusters`, all seeded (`modules/reimbursement/seeds.py`) | effective-dated + tenant-overridable |
| (spec silent) | **Physical-document custody states** per attachment (scanned → original to Accounting → forwarded to COA); e-signature decision per artifact with the resident COA auditor (default: printed + wet-ink remains the record) | paper post-audit reality — master plan §3.1 |

*(Grows as build proceeds — every divergence from the spec lands here.)*

## 3. R-0 confirmations tracker (spec §15 — user decisions)

- [ ] 30-day liquidation clock: calendar vs working days; COA circular basis
      *(research default: calendar days from return date, per COA 97-002)*
- [ ] Signatory / certification chain (A/B/C) per amount tier — obtain DOH DO
      2019-0225 / -0225A as the delegation source for the reference tenant
- [ ] Wet-signature capture points vs digital approvals — settle per artifact
      with the resident COA auditor (RA 8792 / COA 2021-006; master plan §4 #5)
- [ ] Directory data: greenfield + CSV import is the recommended default
      (shared with Stage B — see `foundation.md` §5)
- [ ] ~~HUC list~~ **reframed**: seed `reimb_dte_clusters` (EO 77 Annex A
      3 clusters) + PSGC region→cluster map; confirm against the EO text at R-0

## 4. R-phase status

| Phase | Scope | Status | QA | Sessions |
|---|---|---|---|---|
| R-0 | Requirements / author decisions | resolved in the delta register + kickoff (research-backed defaults adopted) | — | 12 |
| R-1 | Schema + config — `reimb_*` tables (13) + `core_reference_sequences` (#5), migration `0013`, EO 77 3-cluster + PSGC seed, config pack, CA hard-block DB constraint, catalogs. **Computation logic is R-2; approval runtime is the engine.** Fixtures trimmed to the config/catalog seeds (full synthetic trip set → R-2). | **done** (session 12) | pytest 340 (+20), lint 3/3, migration `0013` reversible | 12 |
| R-2 | Claim wizard — **also delivers the first React surface: app shell + design tokens + component-library seed (TaskList, StatusTag, ErrorSummary, wizard)** per ui-standards §7 fill-trigger (owner decision 2026-07-22) | not started | — | — |
| R-3 | Checklist engine + uploads (checklist grammar built as a **core service** — Rule 10) | not started | — | — |
| R-4 | Approval chain + work management — **ships the shared core workflow engine** (first consumer). **Engine core shipped 2026-07-27** (session 11, `core_workflow_*`, migration `0012`); R-4-app remaining = author the reimbursement definition (states = spec §6 machine; certify_A/B/C via `step_kind`→gate config), wire `reimb_claims.workflow_instance_id`, the My-Work inbox, and the escalation-notification via `register_sla_enqueuer` | engine core ✅ / R-4-app not started | engine core green | 11 |
| R-5…R-9 | Per spec §14 (templates/signatures → liquidation → external tracking → insights → hardening/pilot) | not started | — | — |

## 5. Decisions log

- **2026-07-27 (session 12 — Stage C R-1: model + config pack)** — built the `reimb_*`
  schema (13 tables, migration `0013`, autogenerated then hand-tuned) + the **core
  reference-number service #5** (`core_reference_sequences`; unbuilt before, reimb is first
  consumer). Decisions: **dropped `reimb_approval_steps`** (= `core_workflow_steps`) and
  **deferred `reimb_signatory_configs`** to R-4-app (= the workflow definition) +
  **`reimb_template_maps`** to R-5 (Rule 10 — no engine duplication); **`destination_class`
  → `destination_region_code`** (PSGC) routed via `reimb_region_clusters`/`reimb_dte_clusters`;
  **CA hard-block = a partial-unique DB index** on `reimb_cash_advances` (one non-settled CA
  per claimant, PD 1445 §89), not a workflow guard; **`reimb_claims.workflow_instance_id`
  FKs INTO** the engine; append-only reimb logs (return/status/external events) are
  REVOKE-UPDATE **and audited** (module tables can't join core's `_UNAUDITED`); the config
  pack + EO 77 3-cluster + PSGC map + a representative COA-2023-004 checklist + return-reason
  taxonomy are seeded (`modules/reimbursement/seeds.py`, module-local since core can't import
  modules). 30-day clock stored as `calendar` days (COA 97-002 default). **Fixtures trimmed**
  to config/catalog seeds — the full synthetic 6-traveller/10-trip set moves to R-2 (wizard).
  Verified: pytest 340 (+20), lint 3/3, migration `0013` idempotent + reversible.
- **2026-07-27 (session 11 — Stage C: shared core workflow engine)** — the ONE approval
  engine (`core_workflow_*`) was built as pure core (R-4 core pulled forward, ahead of the
  reimbursement schema). Contract: `docs/standards/workflow-standards.md`; decisions in
  `foundation.md` §7. **Consequences for the reimbursement build:**
  - R-1 can now add `reimb_claims.workflow_instance_id BIGINT FK → core_workflow_instances`
    (module→core; the engine never references `reimb_*`).
  - The spec §6 status machine maps to `core_workflow_states` rows; DV-box certifications
    (`step_kind` certify_A/B/C) map to gate states with `enforce_segregation=true` +
    distinct `required_permission`. **TODO (R-4-app):** define the amount-tier →
    `required_permission` mapping (DOH DO 2019-0225 chain) as transition amount guards +
    per-state permissions. The default `reimb.claim.approve` is a single-gate placeholder.
  - CA hard-block (PD 1445 §89) stays a **DB constraint on `reimb_cash_advances`** (R-1/R-6)
    — it is a data-integrity rule, NOT a workflow guard.
  - Escalation notifications: R-4-app registers a notifier via
    `core.workflow.register_sla_enqueuer` (the engine emits `escalation` events now;
    delivery is deferred).
- **2026-07-23** — Delta register extended with the research corrections
  (EO 77 3-cluster DTE, deduction/vehicle flags, COA 2023-004 checklist basis,
  GAM form numbering, CA hard-block, Revised-IoT versioning, custody states);
  core-workflow-engine and R-2-shell decisions recorded (master plan §2 Stage C).
- **2026-07-22** — Module doc created; delta register seeded with the
  plural-naming and mandatory-column deltas (standing rules 5–7).
