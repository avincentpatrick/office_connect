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
| §8 calculator: per-leg pct; 50-km = strip lodging only (justification unlocks) | **R-2 engine (2026-07-27): per-DAY computation** over the trip span (arrival/full/return/same_day), each day attributed to its **controlling leg** (last of the date by `(seq, id)` — other same-date legs get 0%, so double-claiming is structurally impossible; legless days carry the region forward). Breakdown persisted in `reimb_claims.totals["days"]` JSONB (sanctioned computed-snapshot form, DB standards §11; promote to a day table if R-5 App-45 printing demands rows). **50-km**: within 50 km **without overnight → fare only, 0% DTE** via two attested claim booleans `is_within_50km` + `overnight_stay` (migration `0014`) — supersedes the spec's lodging-only strip. Return-day rate follows the controlling leg's region when set, else the claim destination | research digest (per-day breakdown, commuter = fare only) + COA disallowance patterns |
| (spec silent: rounding, same-day trips, gov-vehicle fare edge) | **ROUND_HALF_UP** to the centavo via new `core/money.py` (quantize each component after its pct, then sum — printed day rows always re-add exactly); **same-day round trip = 50%** (no night → no lodging component; **accountant-confirmed 2026-07-28**, §3); a gov-vehicle leg carrying a fare **hard-fails 422** `reimb_gov_vehicle_fare` (fail-closed, never a silent drop); `per_diem_pct` stores the **day-type gross** (100/50/0) — host strips reduce `per_diem_amount`, never the pct; money inside JSONB = 2-dp **strings** | money standards §10 + audit re-performance |
| §6.1 machine incl. a `reject`-less exit set + "Submitted (instant)" + FMS journey statuses (With Budget / With Accounting / Payment Processing, any order/skips) | **R-4-app definition v1** (`reimbursement.claim`, seeded by `modules/reimbursement/workflow.py::ensure_claim_definition`): `draft → division_approval → admin_review → handed_to_fms → paid_closed`, `returned` loop + `cancelled` — **NO `reject`** (spec §6.1 has only Return/Cancel; the engine's terminal reject stays unused); **"Submitted" is transient** (start_instance + submit in one tx — never observable, history goes draft→division_approval); **FMS sub-statuses are NOT states** — they ride `reimb_external_events` at R-7 over the single `handed_to_fms` state (the engine's closed action enum routes one `(state, action)` by guards, not user choice — multi-way user-chosen branching can't be authored) | spec fidelity vs engine semantics; R-7 owns external tracking |
| §5.5 chain per amount tier (DOH DO 2019-0225) + Director-sign step; `reimb_signatory_config` | **Tiers DEFERRED — definition v2 when the DO is obtained** (R-0 item still open; no peso bands exist in any source we hold). v1 = the §5.5 role chain with per-gate permissions (`reimb.claim.approve` → new `reimb.claim.review` → new `reimb.claim.fms_update`; new `admin_officer` role); versioned definitions make the tiered chain a clean authored v2 (in-flight items finish on v1). **`reimb_signatory_configs` RESOLVED: never built — the definition IS the chain** (closes the R-1 deferral) | DO 2019-0225/-0225A unobtained (research: public PDFs scanned/inaccessible) |
| `status` a first-class column (db-standards §5 names a `reimb_claim_status` PG enum) | **Stays varchar**: the column is a **derived read-model** of engine state codes (stored verbatim; labels + the §6.1 next-action copy in `services/status.py`); legality is the engine's closed transitions set, not DDL — a PG enum would demand a migration per definition version (e.g. R-7's sub-statuses). Synced ONLY by `services/lifecycle.py` (the single sanctioned caller of `start_instance`/`execute_action`); history rows only on real moves | workflow-standards §1 (status mutated by scattered code is forbidden) |
| §7.1 "holder = current step assignee" | **Holder = a deterministic work-management pointer, never authorization** (any permission-holder may still act). Resolution in the lifecycle sync: claimant states → the owner's user (`core_users.staff_id` bridge, fallback originator); gates → **scoped-grant holders only** (`core/org_units.py::permission_holders`; global grants — system_admin's shape — never hold), nearest org unit first, originator excluded under segregation, lowest-id tie-break, **zero match → the transition itself refuses** (`reimb_no_eligible_holder` — never a null holder); `handed_to_fms` → `holder_kind='external_fms'`, `holder_id` NULL (the sanctioned polymorphic pair); terminals → cleared | spec §7.1 non-negotiable + no assignee concept in the engine (OrgUnit has no head/chief column) |
| §7.4 SLA in working days + repeating 2-WD ladder | Gates authored **`sla_hours=None`**; the lifecycle wrapper stamps `step.sla_due_at` itself — Manila date + `add_working_days(sla.approval_working_days=3)` at 17:00 Manila → UTC (the engine column is CALENDAR hours; working-day stamping pends core-service #6's ownership). Engine sweep escalates once (unchanged); the **repeating holder-only ladder** = ops beat `ops.reimb_sla_reminders` (daily 08:30 Manila) with outbox `dedup_key reimb.claim.sla:<step>:<k>` idempotency; `handed_to_fms` is never stamped/nudged (external holder; spec §7.5 is a dashboard filter) | spec §7.4 (holder only, never superiors — non-negotiable) |
| §3.2 submit "Claim owner; Admin Officer on behalf"; cancel "Admin Officer/System Admin any time" | **v1 owner-only submit** (`actor.staff_id == claimant_id`) — segregation guards `instance.originator_user_id` as the maker, so an on-behalf submit would guard the wrong person (recorded deferral; `claimant_user_id` stashed in `instance.context` for the future path). **Cancel only from draft/returned** (owner, or a `reimb.claim.review` holder) — admin void-ANYTIME deferred (the engine authorizes the originator on any authored cancel transition, so authoring one from FMS states would let the owner cancel mid-FMS). Submit/resubmit/cancel transitions all carry `reimb.claim.review` — a permission-less originator transition is an **open gate to any user** (engine fact) | segregation integrity + engine originator semantics |
| ≥1 taxonomy reason per return (`reimb_return_events`) | Service accepts `reason_ids` and always writes the return event (with the returned **step id**, recovered module-side — the engine only stamps step ids on approve); the **≥1-reason enforcement lands with the R-2-wizard return dialog** over the seeded taxonomy | UI owns the picker; comment (engine `requires_comment`) already makes a reason mandatory |

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
- [x] **Same-day round trip = 50%** (meals + incidentals, no lodging component —
      R-2-engine interpretation 2026-07-27) — **accountant CONFIRMED 2026-07-28**
      (session-14 kickoff); the engine's config-driven 50% stands

## 4. R-phase status

| Phase | Scope | Status | QA | Sessions |
|---|---|---|---|---|
| R-0 | Requirements / author decisions | resolved in the delta register + kickoff (research-backed defaults adopted) | — | 12 |
| R-1 | Schema + config — `reimb_*` tables (13) + `core_reference_sequences` (#5), migration `0013`, EO 77 3-cluster + PSGC seed, config pack, CA hard-block DB constraint, catalogs. **Computation logic is R-2; approval runtime is the engine.** Fixtures trimmed to the config/catalog seeds (full synthetic trip set → R-2). | **done** (session 12) | pytest 340 (+20), lint 3/3, migration `0013` reversible | 12 |
| R-2-engine | **Per-diem computation engine** — pure core `services/per_diem.py` + `compute_claim_totals` persist wrapper (writes per-leg `per_diem_pct/per_diem_amount/leg_total` + the `totals` JSONB v1 snapshot); 50-km attestation columns (migration `0014`); `core/money.py` (ROUND_HALF_UP); representative trip factories (R-1 fixture deferral discharged) | **done** (session 13) | pytest 377 (+37), lint 3/3, `0014` reversible; **₱5,500 anchor + cluster switch + 50-km gate green** | 13 |
| R-2-shell | **The first React surface** (the FE-foundation half of R-2-wizard, split 2026-07-28): `web/` Vite SPA — app shell + the 6 layout templates + the **14-component inventory seed** (incl. the ErrorSummary amendment) on the runtime `--oc-*` token pipeline (`@theme inline` + `injectTokens`); full auth flows (login → forced password change → forced MFA setup, session expiry, 429 countdown); NAV_GROUPS seed gated on flags+roles; compose `web` service (:5174, Node 22) with the same-origin `/api` proxy (**no CORS** — api-standards §6); DEV `/ui-foundation` catalog. ui-standards §7/§8 filled; tech-stack §4 filled (rule 9). **Zero backend changes.** | **done** (session 14) | FE gate green (eslint + tsc + vitest 28 + build); pytest 377 unchanged, lint 3/3; live proxy smoke (config 200, CSRF 403) | 14 |
| R-2-wizard | Claim wizard **on the shell** — the module's first HTTP surface (`/api/v1/reimbursement/…` draft endpoints), GOV.UK task-list-driven wizard (WizardPage/Stepper/FormField, **react-hook-form + zod** — confirmed 2026-07-29), server-side save-and-return, check-your-answers + confirmation, directory prefill, `compute_claim_totals` on the money step, **submit ends REAL via `services/lifecycle.py::submit_claim`** (R-4-app), **+ the My-Work inbox** (moved here 2026-07-29 — it is an HTTP/UI surface and the wizard owns the module's first HTTP surface) | not started | — | — |
| R-3 | Checklist engine + uploads (checklist grammar built as a **core service** — Rule 10) | not started | — | — |
| R-4 | Approval chain + work management — **ships the shared core workflow engine** (first consumer). **Engine core shipped 2026-07-27** (session 11, `core_workflow_*`, migration `0012`). **R-4-app shipped 2026-07-29** (session 15): the `reimbursement.claim` definition v1 (spec §5.5 role chain, tiers deferred — delta register), `submit_claim`/`claim_action` lifecycle service (atomic totals + `RB-` ref + instance + status/holder/next-action sync + history), working-day SLA stamping + escalation delivery + the 2-WD holder-only ladder via `register_sla_enqueuer` + `ops.reimb_sla_reminders`, bootstrap `seed-workflows`, migration `0015` (claim↔instance unique belt). **My-Work inbox → R-2-wizard** (scope note) | engine core ✅ / **R-4-app done** | pytest 413 (+36), lint 3/3, `0015` reversible; no-null-holder walk + segregation + double-submit race + ladder idempotency green | 11, 15 |
| R-5…R-9 | Per spec §14 (templates/signatures → liquidation → external tracking → insights → hardening/pilot) | not started | — | — |

## 5. Decisions log

- **2026-07-29 (session 15 — Stage C R-4-app: the reimbursement workflow definition +
  claim wiring + SLA delivery)** — reimbursement became the engine's first real
  definition. Kickoff choices: **R-4-app over R-2-wizard** (the wizard now ends at a
  real submit) and **react-hook-form + zod** for the future wizard (tech-stack §4).
  Design decisions (all in the delta register): **§5.5 role chain, amount tiers
  deferred** to an authored definition v2 (DO 2019-0225 unobtained — R-0 item stays
  open); **claim definition only** (the liquidation chain with certify A→B→C lands at
  R-6; A=claimant is the maker, never a checker slot); **My-Work inbox → R-2-wizard**;
  **status stays varchar** (engine state codes verbatim; labels + §6.1 next-action
  copy in `services/status.py`). Engineering: `services/lifecycle.py` is the single
  sanctioned mutation path (claim-row `FOR UPDATE` serializes double-submit; the flag
  gate fires BEFORE a ref number is burned; ref year = Manila); holder = deterministic
  scoped-grants-only pointer, fail-closed (`core/org_units.py::permission_holders`,
  ancestry now proximity-ordered); working-day SLA stamped module-side
  (`sla_hours=None` on gates); escalation delivery + the repeating 2-WD holder-only
  ladder in `ops/reimbursement_tasks.py` (enqueuer fires pre-commit inside the sweep
  tx → the notify task re-reads committed state and retries; the daily ladder's k=0
  dedup key is the backstop); new RBAC: `reimb.claim.review`, `reimb.claim.fms_update`,
  role `admin_officer`; bootstrap: `load-reference` now applies module seeds +
  new `seed-workflows` (idempotent — a re-run never mints a version); migration
  `0015` = partial-unique claim↔instance belt. Verified: pytest **413** (+36 net),
  lint-imports 3/3, `0015` reversible, seed-workflows ×2 + load-reference ×2 no-op,
  QA-gate walks green (no-null-holder property, chief-self-approval 409, race burns
  one ref, ladder dedup).
- **2026-07-28 (session 14 — Stage C R-2-shell: the first React surface)** — split
  R-2-wizard's FE foundation into its own increment (kickoff choice over R-4-app) and
  shipped it: `web/` (React 19.2.8 + Vite 6.4.3 + Tailwind 4.3.3 + TS 5.9.3, exact-pinned,
  Node 22 LTS). Decisions: **icon set = Lucide** and **primitives = Radix** (unified
  `radix-ui`, components-dir only) — both kickoff-confirmed; **dev connectivity = Vite
  same-origin `/api` proxy, NO CORS** (supersedes the "+ CORS" brief note; cookie
  `Path=/api` + `X-Requested-With` work unchanged; prod serves the SPA same-origin —
  recorded in api-standards §6); **Storybook NO** (DEV `/ui-foundation` catalog instead);
  **breakpoints = Tailwind 4 defaults**, phone-first by convention; **ErrorSummary added
  as inventory item 14** (ui-standards §3 amendment — page-level, not a Form-field state);
  data layer = @tanstack/react-query (global 401 → session-expired redirect); UI gating =
  feature flags + roles (self-permissions endpoint = recorded deferral); tokens =
  `@theme inline` on `var(--oc-*)` + baked neutral fallback + runtime `injectTokens()`
  (tenant re-brand with no rebuild — ui-standards §7/§9); `node_modules` on a named
  volume (Windows bind-mount perf), `npm install`-at-boot. **R-0 closed: same-day round
  trip = 50% accountant-confirmed** (§3). Deferred: form library (react-hook-form/zod)
  to the wizard; MFA QR render; bell feed API. Verified: FE gate green (28 tests),
  pytest 377 unchanged, lint-imports 3/3, live login-path smoke via the proxy.
- **2026-07-27 (session 13 — Stage C R-2-engine: per-diem computation)** — built the
  computation engine as **pure core + async wrapper** (`services/per_diem.py` no-I/O,
  `services/compute.py` loads/persists in the caller's session, flushes, caller commits;
  errors are fail-closed `APIError` factories in `services/errors.py` — the module's first
  service code). Decisions: **per-DAY unit of computation** attributed to the day's
  controlling leg (no day table — breakdown lives in `totals["days"]` JSONB, promotion path
  R-5); **50-km = fare-only without overnight** via two attested claim booleans (migration
  `0014`) superseding spec §8's lodging-only strip; **same-day trip = 50%** (accountant
  confirmation pending, §3); **components quantize-then-sum** with the new platform-wide
  `core/money.py` (`ROUND_HALF_UP`, money-in-JSONB as 2-dp strings — database-standards §10
  updated); **gov-vehicle leg with a fare hard-fails** (`reimb_gov_vehicle_fare`); rates /
  region map / configs all resolve **as-of each day** (mid-trip rate change pays per day);
  settlement `advance − grand` → `to_refund` / `to_reimburse` (spec §6.2), no-CA claims get
  `to_reimburse = grand`. `totals` v1 schema documented in the delta register; trip
  factories (`tests/reimbursement_trip_factories.py`) discharge the R-1 fixture deferral.
  Verified: pytest 377 (+37), lint 3/3, `0013↔0014` reversible, **₱5,500 anchor green**.
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
