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
| `reimb_template_map` (R-1) | **CLOSED at R-5-gen (2026-08-04): built as `reimb_template_maps`, a BINDING table, not the spec's placeholder-merge map.** §10 binds claim fields → Google-Docs placeholders; under WeasyPrint + Jinja2 (master-plan #8, which outranks the reference spec) the template IS the field mapping — expressive, diffable and reviewable in a way a JSONB placeholder dictionary is not, and re-encoding it as data would buy nothing while costing a second grammar to validate. What remains genuinely configurable is the binding: `checklist_code` → `document_key` → title/form no., under a `circular_version`, with `is_active` — exactly what the R-9 catalog editor needs to retire a form when a circular is superseded, without a deployment. Addressed by CODE, not catalog id, because the seed framework upserts by natural key. **Stays module-side** as a core-service #13 candidate, mirroring R-3's decision to keep the checklist engine's storage with its one consumer — promote at Stage E when DTWIS can say which columns are actually common | Rule 10 + precedence (master-plan > references spec) |
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
| ≥1 taxonomy reason per return (`reimb_return_events`) | Service accepts `reason_ids` and always writes the return event (with the returned **step id**, recovered module-side — the engine only stamps step ids on approve). **CLOSED at R-4-screens (2026-08-03):** `claim_action` now rejects an empty `reason_ids` (422 `reimb_return_reason_required`) and any id outside the live+active catalog (422 `reimb_unknown_return_reason`) — enforced in the SERVICE, not just the wire schema, because `reason_ids` is FK-less JSONB and Celery/shell callers bypass HTTP | spec §5.6 "≥1 mandatory"; the R-8 learning loop reads these ids |
| §9.3 wizard = 5 steps incl. Documents; §2 "cannot submit with a missing required item" | **CLOSED at R-3 (2026-08-03): 5 steps** — Trip → Itinerary → Money → **Documents** → Review & submit, and the submit gate is HARD (422 `reimb_packet_incomplete`, naming every blocker, enforced in `lifecycle.submit_claim` AFTER compute but BEFORE `start_instance`, so a refused submit creates no instance and burns no RB- number). Documents is blocked by Money (the required SET is unknowable before compute — the rules read `totals.other`, the leg transport modes and `is_jo_cos`) but never re-closes once materialized; it does **not** block Review, because §9.3 step 5 gates the BUTTON, not the page | spec §2 objective 2 + §5.3 "missing required items DO block submission" |
| — (no HTTP surface convention) | **First module router** (`modules/reimbursement/api/`, self-prefixed `/api/v1/reimbursement`, mounted from `main.py`) behind `require_feature("module.reimbursement")` → **flag OFF 404s the router, reads included** (module indistinguishable from absent). **RESOLVED at R-4-screens:** see the un-gated-actions row below | api-standards §9 (new — records the pattern) |
| §9.3 money step "other expenses (each spawns its conditional checklist items)" | **`reimb_claims.other_total` numeric(12,2)** (migration `0016`; snapshots backfilled from `totals->>'other'`); `compute_claim_totals` reads the column (an explicit param persists to it first) — **fixes the latent resubmit-resets-other-to-zero bug** (the old param never survived `claim_action("resubmit")`). Itemized expense lines + their conditional checklist items are R-3 | one source of truth for "other"; regression test pinned |
| §6.1 row 1 "Draft · holder = Claimant" (implicitly from birth) | **`lifecycle.create_draft_claim`** stamps `status='draft'` + holder trio + next-action + a None→draft history row AT CREATION — §7 rule 1 holds from the first row and My-Work's "waiting on you" includes drafts with no OR-branch. Legacy pre-R-2-wizard rows (NULL status) coalesce to draft in reads/editable-checks only | workflow-standards §1 — lifecycle stays the only status writer |
| §3.2 "Owner sees own; Chiefs their division; Admin/Director all — claims are NOT bureau-public" | Route gate `require_permission("reimb.claim.read")` + in-handler **owner-or-scoped** check: owner, else `authorize_scoped` on any of `reimb.claim.{approve,review,fms_update}` against the claim's org unit — because the `staff` role's read grant is GLOBAL and `authorize_scoped` on read alone would make claims bureau-public. My-Work needs no scope check (holder/claimant-keyed by construction) | §3.2 server-side scoping; the authz matrix test is the proof |
| §9.3 step 1 "activity picker (first-class, skippable)" | **Picker omitted from v1** — no activities HTTP endpoint exists yet; `activity_id` is accepted+validated by PATCH (422 `reimb_unknown_activity`) so the wire contract is ready; the picker UI lands with an activities endpoint | a bare numeric field invites junk ids |
| §9.2 wizard "autosave every step" | **Submit-per-step** (explicit Continue = a PATCH/PUT — server-side save-and-return; refresh loses at most the current screen's keystrokes) + an unsaved-changes blocker dialog + `beforeunload`. Editing a compute INPUT (dates/region/attestations/other_total/legs) **clears `totals` server-side**, so the task list re-opens Money automatically — stale money is worse than absent money | GOV.UK one-thing-per-page; spec §14's "autosave survives refresh" holds for everything past a Continue |
| §7.3 zero-state "Nothing waiting on you 🎉"; §7.4 urgency order | Copy kept verbatim, **emoji `aria-hidden`** (SRs would announce "party popper"). "Waiting on you" orders by `holder_since` ASC (longest-waiting first) — the SLA-due badge **CLOSED at R-4-screens** (`sla_due_at` + a server-derived `sla_state` per row, one batched join over active `core_workflow_steps`); status→semantic map: draft/returned/fms_returned=amber, gates/FMS=grey, paid=green, cancelled=red | a11y + v1 urgency proxy |
| §6.1 deep links into submitted claims' wizard steps | Step routes render the **read-only detail in place** for non-editable claims (never a redirect — a post-submit `<Navigate>` would race the page's own navigation to the confirmation); `/claims/:id` is the canonical resume/detail URL (claimant-held → jump to the first incomplete step) | deterministic post-submit flow; pinned by the review-page test |

| workflow-standards §9 "in-flight always finishes" vs api-standards §9 "flag OFF 404s the router" | **R-4-screens (2026-08-03): the flag gates the module's SURFACE; it never gates a DECISION on an instance already in the chain.** `api/actions.py` is a SECOND top-level router (`/approve`, `/return`), mounted from `main.py` **without** `require_feature` — it cannot be included under the gated router (FastAPI applies a router's `dependencies` to everything beneath it). Reads + wizard writes stay gated; `/submit` needs no exemption (`start_instance` already refuses flag-OFF) and its resubmit branch stays gated (claimant-editing work, meaningless without the wizard). **Accepted residual:** flag-OFF the approver UI is unreachable though the POST answers — the guarantee is that the engine and its HTTP mirror never refuse an in-flight transition, not that the SPA stays up | api-standards §9a (new — records the pattern); pinned by `test_reimb_api_flag_gate.py` |
| — (endpoint shape for workflow actions) | **Per-action routes** `POST /claims/{id}/approve` + `/return` (matching `/submit`, `/cancel`), not one `POST /actions` with an `{action}` discriminator. Each action carries its own schema, so "≥1 reason" fails as a **field-anchored 422** (`loc: ["body","reason_ids"]`) the FE's 422→field mapper attaches to the chip picker itself | user decision at kickoff; api-standards §9a |
| §6.1 rows 3/5/6 are three different-looking approvals | **One `approve` endpoint for the whole chain** — the definition authors the SAME `approve` action on `division_approval→admin_review→handed_to_fms→paid_closed`, so only the LABEL varies by status (`claim-status.ts::actionLabel`: "Approve" / "Approve & hand to FMS" / "Mark paid & close"; return from `fms_returned` reads "Return to claimant"). A claim is now drivable to terminal over HTTP — the chain is e2e-testable for the first time | the graph already said so; inventing three endpoints would have been three ways to get the same guard wrong |
| §9.2 "approval screen — single card, sticky Approve/Return, phone-first" | **Folded into `/claims/:id`**, not a separate `/approve` route — one canonical URL for claimant, approver and bystander, with `DetailPage`'s new sticky `actions` slot carrying the buttons (ui-standards §4 amendment). What differs between the three audiences is entirely `available_actions`, so there is no client-side role routing to get wrong and no second URL for My-Work to choose between. Flagged auto-checks closed at R-3; **the packet PDF preview CLOSED at R-5-packet (2026-08-04)** — a `PacketPreview` card as the page's fourth section, embedded `<iframe>` from `lg` up with a new-tab link at every width (see the preview row below) | delta row 53 (`/claims/:id` is canonical); workflow-standards §3 |
| workflow-standards §3 "the UI renders the server's action set" | **`available_actions` + `row_version` + `sla_*` are EMBEDDED in `ClaimDetail`**, not a sibling `GET …/available-actions`. Every mutation already returns the whole claim, so the buttons, the CAS token and the record refresh in one response — no second query to invalidate, no window where they disagree. `services/actions.py::claim_actions` wraps the engine and answers for a **draft** (no instance exists pre-submit, so the engine has nothing to compute over → owner gets `["submit","cancel"]`) | api-standards §1 (additive within v1) + §9a |
| §7.4 SLA / §6.3 "Due Soon (≤ 7 days) / Overdue" | **`sla_state` is server-derived** (`on_track`/`due_soon`/`overdue`) from the active step's `sla_due_at`, on `ClaimDetail` and on every My-Work row. **Due-soon window = 1 day, not §6.3's 7** — that 7-day window is keyed to the R-6 LIQUIDATION deadline (a 30-day clock); against a 3-working-day approval SLA every item would be born amber. In My-Work, "Waiting on you" spends its one chip on urgency when a row is slipping (spec §9.2 "urgency chips" — the section heading already says the status) | spec §6.3 is two clocks in one sentence; the approver-facing one is the only one in scope |
| §5.7 `reimb_status_history` "feeds the tracker UI" | **`GET /claims/{id}/timeline`** merges the append-only history with `reimb_return_events`. No FK joins them, so pairing is positional: rows landing in `returned`/`fms_returned` are *only* reachable by a `return`, and the two lanes are written 1:1 in one transaction, so the k-th of each match. **Defensive:** a count mismatch drops the reasons rather than attaching them to the wrong return — a misattributed reason is worse than a missing one. **Bug found + fixed en route:** an idempotent replay of a return appended a phantom SECOND `reimb_return_event` (the insert sat after `execute_action`, which returns the original event verbatim on a key hit) — now guarded, which is also what makes the pairing exact | spec §12 "returned → includes reasons verbatim"; append-only tables cannot be repaired after the fact |
| §5.6 return-reason catalog | `GET /return-reasons` orders by `category, code` — the catalog has **no `sort` column** (unlike `reimb_checklist_catalogs`). `category` is a PG ENUM, so Postgres sorts by DECLARATION order, which is the authored taxonomy order (`missing_doc` → … → `other`): the chips land grouped and most-common-first with no sort column existing. Pinned by test so a future enum edit is a visible decision | free ordering beats a migration; the enum already encodes intent |
| §9.2 return dialog "comment optional" | **Comment is MANDATORY** — every authored `return` transition sets `requires_comment`, and spec §12 promises the claimant the reasons *and* the note verbatim. A taxonomy code alone ("Missing official receipt") does not say *which* receipt. Both rules are enforced server-side; the dialog's client-side wording is identical to the server's message (ui-standards §3.14) | engine authoring (R-4-app) already decided this; recording the divergence from §9.2 |
| §9.4 "flagged auto-checks render as amber callouts; never approve past a missing required item" | **CLOSED at R-3 (2026-08-03).** Flags ride `ClaimDetail.checklist.flags` and render as an amber `Callout` above the decision bar; the confirm sheet states that approving past a flag is recorded against the approver. The missing-item block is enforced in `claim_action("approve")` AND filtered out of `available_actions`, so the approver never sees a button certain to 422 — a red `Callout` explains the gap instead, and `return` (their actual remedy) is untouched | spec §9.4; the R-4-screens doctrine that the UI is never offered a doomed button |
| core-service #7 as a shared engine over `reimb_`-prefixed tables | **`office_connect/core/checklist/`** is PURE: `grammar.py` (the closed `always`/`if`/`any`/`all` operator set with `eq`/`contains`/`gt`), `checks.py` (the six §5.3 auto-check types), `engine.py` (idempotent reconciliation + the blocking rule) — dataclasses in, dataclasses out, no ORM, no session. The module keeps its shipped tables, assembles the facts and applies the plan. Core therefore imports no module table and `lint-imports` holds by construction. **Storage promotion to `core_checklist_*` is deferred to Stage E**, when DTWIS becomes consumer #2 and can say which columns are genuinely common | Rule 10 + the import contract + not rewriting shipped schema mid-stage |
| §5.3 "auto-checks set auto_passed/auto_flagged" on one `status` column | **Blocking is computed from EVIDENCE STATE, never from `status`.** `status` is a derived read-model with one writer (`refresh_checklist`), exactly as `reimb_claims.status` mirrors the workflow engine. So `auto_flagged` counts as satisfied (the literal encoding of "a flag never blocks alone"), check results are re-derived on every read rather than persisted (the approver's callouts always describe the claim as it is NOW), and a stale column cannot produce a wrong gate decision. **This is why no check-results column and no `not_applicable` enum value were needed** | spec §5.3 + §9.4 |
| §6.1 gate reads "all required items non-missing", literally | **`generated_doc` items NEVER block** — a system-produced artifact cannot be a precondition of entering the workflow that produces it. Not an R-5 dodge: it stays true after the template engine ships, because generation happens downstream of submit. Without it the three always-on `generated_doc` seed rows (IOT-45, AR-01, DV-32) would make every claim in the tenant permanently unsubmittable. `data_only` is excluded too (the claim's own data IS the evidence — nothing to attach, though it can still flag). Blocking evidence = `upload` + `external_wet_sign` | the gate must be shippable before R-5 |
| master-plan #7 "missing required items block transitions" (plural) | Enforced on **submit, resubmit and approve** — never on `return` or `cancel`. Blocking a return would trap a claim whose packet is incomplete inside the chain, the exact opposite of the rule's intent. Approve reads **persisted rows only** and does NOT re-materialize: fresh evaluation mid-approval would let a catalog edit retroactively block an in-flight claim (workflow-standards §9, "in-flight always finishes"). Row existence encodes what was required at submit, so no `required_snapshot` column is needed | master-plan §1.1 #7 vs workflow-standards §9 |
| §5.3 grammar with no stated failure direction | **Evaluation is TOTAL, validation is STRICT.** `evaluate_required_rule` never raises (it runs on every packet read over admin-editable JSONB); `validate_required_rule` raises and gates the seeds. An unparseable rule fails **OPEN** with a visible `unparseable` flag, not closed: with waivers deferred there is no escape hatch, so blocking on a rule we could not read would strand the claim forever (§9.1 principle 4). The catalog is seed-only until the R-9 admin editor and the seeds are validated, so an unparseable rule cannot reach data today. **When the catalog editor ships, waivers must ship with it and this flips to fail-closed** | §9.1 principle 4 vs compliance safety — recorded so the trade is revisited deliberately |
| §5.3 six auto-check types | **Four implemented over data that exists**: `file_present`, `amount_threshold`, `date_within_trip` (over LEG dates today, widening to receipt dates when OCR lands), `sum_matches`. `keyword_absent` (needs OCR — **re-deferred at R-9 to Stage H**, see below) and `deadline_check` (needs the liquidation clock, R-6 — **now live**) are **registered and implemented but return `skipped` with a named reason** when their substrate is absent — so a seeded rule using one is visibly inert rather than silently passing. Spec §5.3's example key `liquidation.deadline_working_days` does not exist (the seeded key is `liquidation.deadline`, and calendar-vs-working is still an open R-0 item) — do not seed a `deadline_check` before R-6 resolves it. **R-9 re-deferred `keyword_absent`/OCR out of Stage C, deliberately**: this row and master-plan §1.1 both said "R-9" while build spec §14's R-9 row never asks for OCR, so the promise was one this project made to itself. Shipping it would have meant a new system dependency (Tesseract in the worker image), an extraction stage on the attachments pipeline and a new published fact — into the session whose deliverable is *evidence the existing eight increments hold up*. It costs nothing to wait: the check is registered, returns a NAMED `skipped`, and **no seeded rule uses it**, so nothing is silently passing. Lands with the OCR substrate at **Stage H** | honest inertness over a silent pass |
| §5.3 `auto_checks` `on_exceed: "require_item:RER"` | **Carried through as `CheckResult.remedy` and RENDERED, never executed** as a materialization directive. It names code `RER` while the catalog code is `RER-46`, and it sits on the RER-46 row itself (self-referential). An executable "require_item:X" would make materialization order-dependent and let one catalog row conjure another | the seeded directive is incoherent as written — scope fence |
| §5.3 `attachment_ids int[]` on the item | **`reimb_attachments` is the source of truth; `reimb_checklist_items.attachment_ids` is a DISPLAY MIRROR.** The join row has the FK, the soft-delete columns and the custody state; db-standards §11 forbids putting in JSONB anything other code must join on. The mirror is always REASSIGNED, never `.append()`-ed — the column has no `MutableList`, so an in-place mutation would leave the row un-dirty and silently not persist | db-standards §11 + the same doctrine as `reimb_claims.status` |
| — (no upload convention) | **The module owns its upload endpoint** (`POST /claims/{id}/checklist/{catalog_id}/attachments`, on the GATED router) rather than reusing core's generic `POST /attachments` plus a link call: attaching is upload + join row + mirror + status recompute in ONE transaction, and the real rule ("may this actor edit THIS claim's packet") cannot be expressed by a coarse `attachment.upload` permission. Every byte still goes through `core.attachments` (Rule 10). Downloads stay on the core route, scoped by the `register_holder_authorizer` seam Stage B built for exactly this — **zero core router change** | recorded as **api-standards §9b**: Rule 10 + atomicity + §9's coarse-at-route/exact-in-service doctrine |
| — (reads may materialize) | **`GET /checklist` writes NOTHING.** Planned-but-unmaterialized items return `item_id: null`, and every write endpoint is keyed on `catalog_id`, so the client never needs a row to exist before it can act. A row is created exactly when it must hold something. No GET-that-commits, and no write fanned out of every wizard save | a read that commits is a surprise nobody budgets for |
| — (catalog revisions rewrite history) | **`reimb_checklist_items.circular_version`** (migration `0017`) snapshots the revision an item was materialized against. `apply_dataset` upserts catalog rows IN PLACE by natural key, so without it a future COA revision would retroactively change what a historical claim's item meant. Unbackfillable after the fact | master-plan §1.1 #7 "catalog versions pinned to the issuing circular revision" |
| `reimb_attachments.retention_class` default `financial_10yr` | **BUG FIX (migration `0017`): → `financial_dv_10y`.** The shipped default is not a key of `core/attachments/retention.py::RETENTION_CLASSES`, so `retain_until()` fell through its unknown-class fail-safe and returned `None` — every claim attachment would have been permanently non-disposable and mislabeled in the disposal-eligibility report. R-3 creates this table's first rows, so the fix was free now and a data migration later. `retention_starts_at` stays NULL deliberately: GRDS runs 10 years from FINAL SETTLEMENT (`paid_closed`, R-7) | latent defect found while wiring the seam |
| §9.3 step 5 "Submit disabled until required items clear" vs GOV.UK "never disable a submit" | **Spec-literal, a11y-mitigated:** the button stays VISIBLE and `disabled`, with an always-visible `aria-describedby`-linked panel immediately above carrying the server's `gate_message` verbatim and a router link per blocker (`…/documents#checklist-item-{id}`). Previously the code did neither — it HID the button, the worst of the three (no affordance at all, so the goal was invisible). Accepted residual: a disabled button is not focusable, so the panel must never be collapsible. Generalized as a new ui-standards §3 Button rule | spec §9.3 vs GOV.UK guidance — divergence recorded |
| §9.1 chip vocabulary mapped onto the four semantics | **Required-and-missing is AMBER, not red.** On a fresh draft every required item is missing, and a wall of red on a screen you have just arrived at reads as "you did something wrong" — the opposite of §9.1 principle 4. Red is reserved for where the item actually blocks a decision: the Review gate panel and the approver's callout. Same item, two contexts; colour follows CONSEQUENCE. Flags are amber too ("a flag never blocks alone") | §9.1 principles 4 + 5 |
| §9.3 "phone camera capture allowed" | **`capture` deliberately UNSET.** On iOS/Android the attribute FORCES the camera and removes the gallery/files option; `accept="image/*,application/pdf"` already surfaces Camera *alongside* Files in the OS sheet. "Allowed", not "forced" — the prop stays on the component for a future camera-only caller | reading the spec's word literally |
| — (one state per attached file) | **Two chips per attached row, deliberately:** the ITEM chip says "Attached" (the packet requirement is met) while the FILE chip says "Checking" (`scan_status: pending` — saved and counted, but not yet downloadable, so no link is offered). A `pending` scan never blocks: refusing a claimant because the virus scanner is behind would be a self-inflicted outage. Only `infected` disqualifies | honest state over a convenient one |
| §5.3 `waived` status + `waiver_reason` | **Waivers DEFERRED** (user decision at R-3 kickoff). The engine supports `waived` end to end — it outranks every machine verdict and keeps an item alive when the rule stops applying — but no endpoint and no UI ship this increment: waiving a COA requirement needs its own authority rule, audit story and screen. Coupled to the unparseable-rule direction above; both revisit together when the R-9 catalog editor lands | kickoff decision; keeps this increment's surface honest |

| §10 flow: "copy template in Shared Drive → placeholder merge → export PDF" | **Drive DROPPED from the generation path entirely (R-5-gen, user-confirmed at kickoff).** Rendering is **WeasyPrint + Jinja2 in Celery** per master-plan §1.1 #8, which outranks the reference spec on precedence and is what the round-1 research digest concluded: pure-Python, no headless browser, works on an offline on-prem box, and the same design tokens govern print as govern screen. wkhtmltopdf was rejected outright (archived Jan 2023, ancient WebKit). The *rest* of §10 survives intact — SHA-256 → frozen snapshot → checklist flips to `Generated`, idempotent Celery task with 3 retries, and Google/worker-down degrading non-blockingly | precedence + `docs/research/round1/file-attachments-pdf-generation.md` |
| §10 "Templates seeded from the real Drive files: Appendix A, Appendix B, Liquidation Report, JO/COS Certification, Certificate of Appearance" | **Three documents generated, and they are exactly the three `generated_doc` catalog rows:** IOT-45 (GAM App 45 Itinerary), AR-01 (accomplishment report), DV-32 (GAM App 32 Disbursement Voucher). The master plan's R-5 bullet also names App 46 RER and App 47 CTC, but the catalog seeds **RER-46 as `upload`** (the traveller's own receipt) and **CTC-47 as `external_wet_sign`** (a page signed by hand) — generating either would assert something the system cannot know. App 44 Liquidation Report belongs to the R-6 liquidation clock | the catalog's own `evidence` column is the authority on what may be generated |
| — (spec assumes generation happens once) | **DRAFT pre-submit, AUTHORITATIVE at submit** (user-confirmed at kickoff). `ref_no` is only allocated at submit (`lifecycle.submit_claim` step 4), but §9.3 step 4 promises `Generated ✓` cards with preview *inside the wizard*. So a pre-submit pass renders a watermarked draft (banner **and** diagonal mark — colour never carries meaning alone, and a greyscale office printer is where a colour-only marking disappears) stamped `DRAFT-<claimId>_…`; submit regenerates and the new snapshot **supersedes** the draft. Draft-ness is **derived** from claim state inside the task, never passed in, so a job queued while the claim was a draft and executed a second after submit produces the official document | §9.3 step 4 vs the reference-number lifecycle |
| §10 "regeneration after any edit voids prior snapshots" | **Voiding fires on ANY editable field change, not only money inputs — found by the R-5 live smoke.** `purpose` is printed on all three documents but is not a compute input, so an invalidation keyed on `_COMPUTE_INPUTS` left an ACTIVE snapshot asserting a purpose the claim no longer had. `drafts.update_draft_fields` now tracks two separate questions: did a MONEY input move (clear `totals`) and did ANY printed field move (void the packet). Voiding slightly too eagerly costs one re-render of an idempotent job; voiding too rarely leaves a document asserting facts the claim does not contain | a real defect the unit tests did not catch |
| — (no provenance on an attachment) | **`core_attachments.origin` (`uploaded` \| `generated`) — one new core column doing three jobs.** (1) SCAN: generated bytes are born `clean` (`scanner_name='system-generated'`), because they are rendered in-process from autoescaped templates and never leave it — and because in production `NullScanner` returns `error`, so leaving them `pending` would make every generated packet permanently undownloadable wherever ClamAV is absent. (2) DISPOSITION: only generated PDFs are served `Content-Disposition: inline`, which is what makes preview possible at all; uploads stay `attachment` forever because a claimant's PDF can embed JavaScript. Derived server-side from the stored row — never a query parameter. (3) COUNTING: `evidence_counts` filters on `uploaded`, so a generated document is never tallied as evidence a human supplied. Recorded as **api-standards §9c**, which amends §9b's "zero core router change" — how a blob is served is a property of the blob, and that is core's to know | Rule 10 + one column beats three flags |
| §5.3 status `generated` (R-3 shipped the value, nothing could write it) | **`checklist.mark_generated` is the one bootstrap.** `_states` derives `ItemState.generated` from `row.status == "generated"` and `refresh_checklist` writes back only the engine's `derived_status` — a closed loop with no entry point, which is exactly why the three items sat inert after R-3. The generator materializes through `materialize_generated_item`, a **deliberately separate door** from `_item_for_catalog`: a claimant may never upload against IOT-45 (`reimb_evidence_not_uploadable`) and the generator may never manufacture a TO-01 (`reimb_document_not_generatable`). One permissive materializer would erase both rules at once. Once written the value is self-sustaining — `generated` outranks every evidence-derived status and `holds_something` keeps the row alive when its rule stops applying | the R-3 loop needed an entry point, not a wider door |
| §9.3 step 4 "generated docs show as `Generated ✓` cards with preview" | **Card = a page-local composition, not a new inventory row** (ui-standards §3 usage note). One chip, not two: R-3's two-chip rule exists because an upload's ITEM and FILE states genuinely differ, whereas a generated file is born clean, so a second chip would repeat one fact rather than report a second. Preview is a **link to a new tab** (announced `sr-only` per WCAG 3.2.5), not an embedded frame — three inline PDF viewers stacked in a task list are unusable on the phone this module targets. The embedded packet preview §9.2 promises the approver is R-5-packet | §9.3 step 4 + the phone-first constraint |
| §10 "Celery task, idempotent, 3 retries" | **Idempotent by FINGERPRINT**, not by a flag: the SHA-256 of the canonical render context is compared with the live snapshot's before any rendering, so a retry, a double-click and a beat sweep all cost nothing. `generated_at` is excluded from the compared context — it changes every pass by construction and would defeat the whole mechanism. The generate endpoint returns **202 with `queued`**, never 200 with documents: a 200 would be an endpoint that had rendered inline (api-standards §9c). No `documents_render: inline` setting was added — its only purpose would be to permit exactly what master-plan #8 forbids | §10 + §19.12 |
| §9.2 "packet PDF preview" / master-plan R-5 "one printable packet" | **The packet is a CLAIM-LEVEL ARTIFACT, not a checklist document (R-5-packet, 2026-08-04).** No COA circular names the folder its documents travel in — the circulars name the documents inside it — so inventing a catalog row would put a system artifact into the FS-BD-01 checklist and hand a claimant a requirement nobody wrote. Concretely: `reimb.packet` is registered with core-service #8 but is deliberately **absent from `reimb_template_maps`** (whose unique key is `(claim_kind, checklist_code)` and whose code is NOT NULL); it is generated *beside* the bindings loop, calls neither `materialize_generated_item` nor `mark_generated`, and its join row carries `checklist_item_id = NULL`. `claim_evidence()` and `evidence_counts()` already filter `checklist_item_id IS NOT NULL`, so it is invisible to the Documents task list and uncountable as evidence **with no filter change anywhere**. Its title is a code constant, not a seeded row: nothing about it is per-circular configuration | the catalog is COA's, not ours to extend |
| — (spec assumes a packet is assembled from finished files) | **Composed by Jinja include, NOT by PDF merge.** Each form's body moved to a partial (`_iot45_body.html.j2` …) that both its standalone template and `packet.html.j2` include, so one WeasyPrint pass produces cover → COA checklist → evidence manifest → the three forms in full (**6 pages, live-verified**). The alternative — stitching three rendered PDFs with `pypdf` — would have added a dependency (rule 9) to reproduce markup we already had. Two generic print primitives were added to core's stylesheet for it (`.page-break`, `.mono`); neither is knowledge about claims | no dependency for a problem the template engine already solves |
| master-plan R-5 "the packet contains the claimant's evidence" | **The manifest INDEXES the uploads; it never EMBEDS them** (user-confirmed at kickoff). Each line carries checklist code, filename, size, **SHA-256 of the original bytes**, scan state and custody. Three reasons: (1) COA takes delivery of the **original** receipts — which is why `reimb_attachments.custody` exists — so a printed scan is not the evidence and the packet's real job is to say what must be stapled behind it; (2) merging a claimant's PDF would put bytes we did not author inside a document served `Content-Disposition: inline` **precisely because** we authored every byte of it (api-standards §9c) — it would break the born-clean chain and the preview with it; (3) no `pypdf`, no image→PDF path, and no dependency of the packet's CONTENTS on scan timing. A quarantined file is listed and marked, never silently dropped: a clerk counting envelopes needs to know a receipt was rejected | COA reality + the §9c provenance chain |
| §10 "regeneration after any edit voids prior snapshots" (R-5-gen read this as claim FIELDS) | **Attaching or detaching evidence now voids the packet too.** R-5-gen's invalidation was complete while the generated documents printed only claim data; the packet also prints a manifest of the uploads, so a file arriving or leaving makes the frozen packet describe a set of documents the claim no longer has — exactly the argument that made `purpose` a trigger at R-5-gen, one level out. `services/checklist.py` calls `core.documents.void_snapshots` **directly** rather than reusing `drafts.invalidate_packet`: `drafts → lifecycle → checklist` already exists, so importing `drafts` here would close the cycle. It voids only and does **not** enqueue a render — otherwise every upload rebuilds the whole packet mid-wizard; submit regenerates authoritatively. The generator cannot void its own work, because `store_generated_document`/`mark_generated` are a separate door from `attach_evidence` | the same rule as R-5-gen, applied to the manifest |
| — (a document cannot carry its own hash) | **The cover prints the `source_fingerprint`, not a hash of its own bytes** — the latter is circular. The fingerprint is computed over the context, then injected into it for rendering only, and `service.comparable_context` nulls **both** `doc.generated_at` and `doc.fingerprint` before hashing. One shared helper for all four documents: two call sites computing "comparable" differently would make one of them look permanently stale. The cover additionally prints each embedded form's `content_sha256`, which is what lets a single loose page be tied back to the packet it came from. Side effect, accepted: adding the nulled key changed the three forms' fingerprints, so every pre-existing snapshot re-renders once (dev-only data) | a real audit anchor instead of an impossible one |
| — (no rule for who may ask for paperwork) | **`POST /documents/generate` grew a second door.** Owner-while-editable (unchanged), **or** an actor holding a scoped `reimb.claim.review`/`approve` grant on the claim's org unit. Without it an Admin Officer whose `NEXT_ACTION[admin_review]` reads *"Final check & print packet"* and whose worker was down at submit faces that instruction with no packet and no way to ask — the dead end §9.1 principle 4 forbids. Deliberately **not** widened to "anyone who may read the claim": the `staff` role's read grant is GLOBAL (§3.2). The route gate relaxed from `reimb.claim.create` to `reimb.claim.read` (approving is not creating) with the real rule in the service — api-standards §9's coarse-at-route/exact-in-service doctrine. `fms_update` is excluded: FMS tracks a packet it already holds on paper. A refused bystander gets the OWNER path's error verbatim, so the message is not an existence oracle | §9.1 principle 4 vs §3.2 scoping |
| §9.2 "packet PDF preview", phone-first | **Embedded `<iframe>` from `lg` up; a new-tab link at every width.** iOS Safari does not render a PDF in an iframe — it shows a blank box — so an embedded-always frame would fail on precisely the device §9.2 marks phone-first. The link is therefore the primary affordance and the frame is the desktop enhancement over it; only the FRAME is breakpoint-hidden, so no node is rendered twice (`DetailPage`'s single-node rule). `PacketOut` rides `ClaimDetail` rather than a sibling endpoint (delta row 59's reasoning: the decision and the document decided on must never arrive in two responses that can disagree), and needs **no new download route** — core's `/attachments/{id}/content` is already claim-scoped by the holder authorizer and already serves generated PDFs inline. `null` is a real state (fresh draft, or a worker-down submit) and renders as an honest notice, never an empty frame | §9.2 vs what mobile browsers actually do |
| §4 `liquidation.deadline_working_days`; §15 R-0 item 1 "calendar or working days?" | **R-0 ITEM 1 CLOSED (R-6-clock, 2026-08-04): CALENDAR days, with `basis` as a LIVE SWITCH.** COA 97-002 says "30 days" with no working-day qualifier, so the seeded `liquidation.deadline` stays `{"days": 30, "basis": "calendar"}` — but the R-0 question was always whether DOH *practice* differs, and that is a question about an agency, not about arithmetic. `services/deadline.py` therefore READS `basis` and routes to `core/workdays.py::add_working_days` when it says `working`: confirming working-day practice later becomes a config edit, not a code change plus a data migration of every deadline in flight. The two-line branch is the entire cost of not guessing — and the guess would have mattered, because the same "30 days" is **12 calendar days apart** between the two bases (pinned by test) | spec §15 item 1 + COA 97-002 |
| — (no stated fail direction for a deadline) | **The clock fails SHORT.** An unreadable `liquidation.deadline` row falls back to 30 calendar days *and names the reason* (`no_config_row` / `unreadable_days` / `unknown_basis`); an unreadable *basis* keeps the configured day count, because discarding a legitimate `45` over a typo'd basis would be a second wrong answer on top of the first. This is the OPPOSITE direction to `core/checklist/grammar.py`'s fail-OPEN for an unparseable rule (delta row 69), deliberately: a rule that fails open produces a **visible flag** a reviewer can action, whereas a deadline that failed open would quietly hand a traveller time they do not legally have and nobody would ever see it | the two asymmetries are one decision, made in opposite directions for opposite reasons |
| §5.4 `reimb_cash_advance` (built R-1, no surface) | **`deadline_date` + `deadline_basis` are a PINNED computed snapshot** (migration `0019`), not a derived read. Three reasons, the third decisive: the daily sweep range-queries the date instead of resolving the effective config pack per row; `reimb_claims.liquidation_deadline` already set the stored-deadline precedent; and **the deadline a traveller was TOLD must not silently move** when an admin edits `liquidation.deadline` or a holiday lands in `core_holidays`. Recomputed on exactly one trigger — `date_return` moving — which is the R-5-gen `purpose` discipline (track which question an edit actually answers) applied to the clock. Re-dating also clears a stale `overdue`: that verdict was about the OLD deadline | pinned-vs-derived, decided by what a traveller was promised |
| — (no writer convention for `reimb_cash_advances`) | **`services/cash_advance.py` is the SINGLE sanctioned writer**, the same chokepoint doctrine `lifecycle.py` applies to `reimb_claims.status` (workflow-standards §1). Nothing else may move `status`/`deadline_date`/`deadline_basis`, so the three can never disagree with each other or with `date_return`. The claim-side `liquidation_deadline` is a **display MIRROR** written only by `link_claim`/`remirror_deadline` — and `checklist_facts` deliberately reads the ADVANCE, not the mirror, so a failed re-mirror can never produce a wrong `deadline_check` verdict | one writer per column, everywhere |
| §5.4 CA hard-block as a DB index (R-1) | **The `IntegrityError` is now caught and re-raised as a named 409** `reimb_cash_advance_unliquidated`, naming the blocking DV and its deadline. The index remains the guarantee; a pre-flight check races it deliberately and both paths yield the identical error, so losing the race is indistinguishable. Before this, PD 1445 §89 surfaced to an Admin Officer as a 500 — a refusal with no path, which §9.1 principle 4 forbids | a constraint is only usable if its violation is a sentence |
| §3.2 (silent on who records an advance) | **Accounting records it** (user-confirmed at kickoff): new `reimb.cash_advance.manage` on `admin_officer` + `system_admin`; claimants READ their own. `dv_no`/`dv_date` are data only Accounting holds, and the §89 block is only worth having if the record it guards is authoritative. Reads gate coarsely on `reimb.claim.read` then apply owner-or-scoped in the service — **not** reusing `can_read_claim`, because the `staff` role's read grant is GLOBAL and leaning on it would make every colleague's DV numbers and peso amounts bureau-public | api-standards §9's coarse-at-route/exact-in-service, applied to a second resource |
| §6.3 "Overdue is a derived badge, never a status" vs §5.4's `overdue` enum value | **Both hold at once: the CA STORES it, the claim DERIVES it.** §6.3 governs the claim, whose status is the workflow engine's to own. §5.4 gives the cash advance a real `overdue` value because §13's report asks for "overdue CAs count + ₱" — and a derived badge cannot be summed. The ladder sweep is the one writer, and it flips the row **even when the claimant has no login to notify**: the overdue count is a financial fact about the advance, not about whether anyone could be emailed | two clocks, two owners |
| §6.3 "Due Soon (≤ 7 days)" | **The 7-day window lands HERE, as R-4-screens said it would.** `deadline_state` (`on_track`/`due_soon`/`overdue`) is server-derived on every cash-advance response, for the same reason `sla_state` is (delta row 60): a browser with a wrong clock, or one outside Manila, must not be able to tell a traveller they still have time to liquidate. `days_remaining` is always CALENDAR days whatever the basis — "3 working days left" beside a date three weekends away is a countdown nobody can read | delta row 60's deferral, discharged |
| §12 "Liquidation D-7 / D-3 / D-0 / overdue → Claimant (CA holder)"; "email only for liquidation D-3/D-0" | **Milestones are "the most urgent threshold REACHED", not "days_remaining == exactly n".** A beat that missed a day (worker restart, outage) must still warn, and it must warn at the level that is now true — sending "7 days left" on the day 3 remain would be worse than sending nothing. Dedup key is `reimb.liquidation.deadline:<ca>:<rung>:<CHANNEL>`; the channel is IN the key because D-3/D-0 send twice (in-app **and** email) and without it the second row would dedup away against the first, so the email §12 promises would silently never arrive. Overdue repeats carry their index (`overdue:0`, `overdue:1`, …) and stay **in-app only** — §12 names D-3/D-0 for email, and a daily email about a missed deadline trains people to filter the sender. Class `transactional`, so it bypasses opt-outs: a traveller may mute workflow chatter, never COA telling them their salary is about to be deducted | spec §12, read literally |
| — (cadence for the overdue repeat) | **The deadline counts CALENDAR days; the nudge cadence counts WORKING days** (`sla.reminder_repeat_days`). When something is due and how often we chase it are different questions, and nobody should be nagged on a Sunday — the same split the approval ladder already makes | two clocks in one feature, kept apart |
| §4 `liquidation.overdue_note` (never seeded) | **Seeded, and with NO code-side fallback.** The sentence states a legal consequence (6% interest, salary deduction) that the resident COA auditor owns; a developer's paraphrase standing in for a missing row would be indistinguishable from the real thing, so a missing row says nothing at all. It rides the API response only once it APPLIES (due-soon or past) — a banner every advance carries from birth is wallpaper, one that appears at D-7 is a warning | spec §4 "displayed with their legal source" |
| §5.3 `deadline_check` "registered but inert" (delta row 70) | **LIVE at R-6-clock.** `checklist_facts` now fills `deadlines` from the claim's linked advance, keyed by CONFIG KEY (what a check names). `FACTS_VERSION` → **2**: that is a change of MEANING for a key the catalog addresses by name, which is exactly what the counter exists to mark. **No `deadline_check` seeded yet** — the deadline applies to a *liquidation*, and the liquidation catalog is authored at R-6-liq; the substrate ships now with a test proving `skipped → passed → flagged`, and the seeded rule lands with its catalog. A claim with no advance still reports `skipped/deadline_clock_unavailable`, which is the honest answer, not a gap | delta row 70's condition, met |
| §5.5 `reimb_approval_step.snapshot_id` FK | **Not built. Signature CAPTURE is deferred to R-6** (user-confirmed at kickoff). Approval steps are `core_workflow_steps`, and R-5 ships the snapshot half of core-service #3 — everything a signature will later bind to (frozen bytes, both hashes, signer identity, timestamp, void-on-edit, and `stale_snapshots()` as the "modified after signature" re-flag). Certification steps A/B/C and external wet-sign need the liquidation chain and the signatory-config question still open with the resident COA auditor; building them now would encode a chain nobody has confirmed. The DV prints Boxes A–D **blank** for the same reason | §14's R-5 row vs what R-6 actually owns |
| §6.1's status vocabulary as ONE flat set (`ALL_STATES` / `CLAIMANT_STATES` / `NEXT_ACTION`) | **GENERALIZED to one `Vocabulary` per claim kind** (R-6-liq-chain), never forked into a second `liquidation_status.py`: four codes (`draft`/`returned`/`handed_to_fms`/`cancelled`) are genuinely SHARED and mean the same thing in both chains, so two copies would duplicate them and drift the day one chain gains a state. A test pins that a shared code never changes CATEGORY between kinds — only its next-action copy. **The one place a union is still correct is cross-kind SQL**: My-Work's two queries span both kinds in a single statement and so filter on `ALL_TERMINAL_STATES`, which is DERIVED from the vocabularies rather than hand-listed — a `settled` missing from it would have left every finished liquidation in the claimant's inbox forever. `vocabulary()` raises on an unknown kind rather than falling back, because a silent fallback would render a liquidation with claim labels and read as working software | workflow-standards §1 (one read-model, one writer) applied to two chains |
| §6.2 `CA Open → Liquidation Draft → Submitted → Certifications (A→B→C in order) → Handed to FMS → … → Settled` | **`reimbursement.liquidation` v1** — a SECOND definition on the shared engine (rule 10: definitions are DATA, not tables), authored `draft → certify_b → certify_c → handed_to_fms → settled` + the `returned` loop + `cancelled`. **Two definitions, ONE `SUBJECT_KIND`** (`reimb.claim`): a liquidation is a `reimb_claims` row, so the polymorphic back-ref never forks. **No new engine verb** — the certifications are `approve` at gate states, exactly like the claim chain's approvals, which is why the un-gated `api/actions.py` drives this chain with zero new routes and zero new schemas. `_assert_graph_invariants` now takes the vocabulary as a PARAMETER: checking both graphs against one merged set would have accepted a liquidation state authored into the claim graph, the exact drift the check exists to catch | spec §6.2 + rule 10 + the R-4-app precedent |
| §5.5 "Certification **A = claimant**" as a chain step | **A is folded into SUBMIT — it has no state at all** (user-confirmed at kickoff). A certifies that the claimant incurred the expenses, and the claimant is the MAKER; the engine's `enforce_segregation` guards `instance.originator_user_id`, so authoring A as a gate would ask the maker to check themselves. Submitting IS certification A, and the event log records who and when. The absence is the decision, pinned by test | the R-4-app maker/checker decision, applied verbatim |
| §5.5 "C = Head, Accounting Unit (external wet-sign capture)" | **`certify_c` is cleared by the Admin Officer under the existing `reimb.claim.review`**, and its `approve` transition is the ONLY one in either chain carrying `requires_comment` — they are attesting to a signature made on paper by someone outside the platform, so the note naming whose signature and when is the only record of certification C that Office-Connect holds. Segregation still applies (the claimant can never clear it). Binding a frozen snapshot to the step is core-service #3's signature half, still unbuilt and still deferred — now with a written reason rather than a gap | spec §5.5 vs who actually holds a login |
| §5.5 "B = Director IV" | **A PERMISSION, not a role**: new `reimb.liquidation.certify`, granted to `approver` + `system_admin`. WHICH person holds it at WHICH org unit is grant data, and `resolve_holder`'s nearest-org-unit-first ranking then picks the right one. A `director` role would encode a chain DOH DO 2019-0225 has not confirmed (R-0 item still open) — the same deferral that keeps the claim chain's amount tiers unauthored. Distinct from `reimb.claim.approve` so a tenant can grant one without the other, which is exactly the flexibility the unobtained DO would need | R-0 item 2 still open — do not encode a guess as a role |
| §6.1 row 7's `fms_returned` relay | **NOT authored on the liquidation chain.** §6.2 names no such state, R-7 owns external tracking, and authoring it now would author a state with no screen. A liquidation FMS bounces goes straight to `returned`. If FMS turns out to return liquidations with comments, that is definition **v2** — versioned definitions make it clean and in-flight items finish on v1, the same answer the DO 2019-0225 tiers get | spec fidelity + not building screens nobody asked for |
| `LQ-YYYY-NNNN` (module header, unbuilt since R-1) | **Built as `REF_SCOPES = {reimbursement: "RB", liquidation: "LQ"}` in `lifecycle.submit_claim`** — core-service #5 unchanged, and NO seed and NO migration, because `allocate_reference_number` creates the `(scope, year)` counter row on demand. Numbers are never reused across either series | rule 10 — the allocator was already general |
| §9.3 step 1 "*if a matching open cash advance exists → offer 'Liquidate that instead?'*" | **`POST /cash-advances/{id}/liquidate` + the action on the CASH-ADVANCE CARD**, not a branch inside the New Claim wizard. The ring counting down in front of a traveller is the moment the offer means something; a step-1 field they may never reach is not. Creates a `kind='liquidation'` draft prefilled from the advance (`dpo_no`, `date_return`), links it via `cash_advance.link_claim` (mirroring the deadline, which is what makes the countdown and the seeded `deadline_check` live from the first read) and calls `mark_liquidation_started`. Gated on `reimb.claim.create` at the ROUTE (it creates a claim) with the real rule in the SERVICE — the actor's staff record must BE the advance's claimant, because filing IS certification A. `CashAdvanceOut` carries `liquidation_claim_id`/`ref_no`/`status`, so the card chooses between "Liquidate" and "Open LQ-…" from ONE response; two requests could disagree and the disagreement would surface as a button that 409s | spec §9.3 step 1 + api-standards §9 + delta row 59's one-response doctrine |
| — (no rule for a second liquidation) | **One LIVE liquidation per advance**, enforced by a service check under a `SELECT … FOR UPDATE` on the advance (lock order advance → claim, which no other path takes, so it cannot deadlock). `cancelled` is deliberately excluded from the live set: a mistaken start must be re-filable or the advance is stuck behind a dead claim forever. The 409 NAMES the existing claim so the button has somewhere to go. A partial-unique index is the DB belt behind it and is a migration `0020` candidate — the same order claim↔instance uniqueness took (service lock at R-4-app, index at `0015`) | §9.1 principle 4 + the R-4-app precedent |
| §5.3 `deadline_check` (substrate live at R-6-clock, no rule seeded) | **THE FIRST SEEDED `deadline_check`, on a new `LIQ-30` catalog row** (`{"type": "deadline_check", "key": "liquidation.deadline"}`). `data_only` on purpose: the claim's own dates ARE the evidence, so there is nothing to attach, and a `data_only` item never blocks (delta row 67) while still being able to flag. That is exactly right for a passed deadline — the approver must SEE it and decide, but a late traveller must never be trapped unable to file the very liquidation that ends the lateness. Discharges delta rows 70 and 109, three sessions after registration | §5.3 + "a flag never blocks alone" |
| §10 "Templates seeded from … Liquidation Report" (liquidation catalog unbuilt) | **The liquidation catalog is authored as ONE coherent COA set**: `TO-01` + `CTC-47` (both kinds — see below), `OR-01` receipts, `LIQ-30`, `LR-44` and `CRT-C`. `LR-44` (GAM App 44) is seeded but **unbound** until R-6-liq-settle: a `generated_doc` never blocks, so an unbound row is visibly "not produced yet" rather than a silent pass — the honest-inertness doctrine the `deadline_check` itself lived under. Splitting the catalog across two increments would have risked shipping a partial COA set | delta row 70's doctrine, applied to a form |
| §5.5/§10 place CTC-47 (Certificate of Travel Completed) on reimbursement only | **BOTH kinds** (user-confirmed at kickoff). The natural key is `(claim_kind, code)`, so a second row is legal; a traveller who took an advance files a LIQUIDATION and one who did not files a REIMBURSEMENT, and the trip and its documentary proof are identical either way. No claimant is asked twice, because a claim is exactly one kind. `TO-01` follows the same reasoning. This closes the R-6-clock open question about whether CTC-47 belonged on reimbursement at all: it belongs on both, and the dichotomy was false — the catalog is per-kind, not exclusive | the catalog's own natural key answers it |
| — (where the certification-C signed page lives) | **`CRT-C` is seeded `{"always": false}` — deliberately never required.** A required wet-sign row would block SUBMIT and certification B too, because the checklist gate is a PRE-workflow gate by construction (it runs at submit and at every approve): it would demand the Accounting head's signature before the chain that obtains it has started. That is delta row 67's argument ("a system-produced artifact cannot be a precondition of the workflow that produces it") one level out. So the row exists as a home for the page, and the RECORD of certification C is the mandatory comment on its transition | the same asymmetry, one level out |
| — (a defect found by this increment's FE gate) | **`CashAdvancesPage` passed `<ErrorSummary items={…}>` where the component's prop is `errors`** (R-6-clock). `errors` arrived `undefined`, so `errors.length` threw and the record dialog would have WHITE-SCREENED on any server error — including the PD 1445 §89 409 that R-6-clock built the named message for. Every other call site in the codebase uses `errors`. It survived because `tsc -b` is incremental and the stale build info did not re-check that file; a full typecheck catches it. Fixed here | a typed prop is only a guarantee if the checker actually ran |
| §6.2 "…→ Handed to FMS → …external… → Settled" (the transition records nothing) | **Recording the money and closing the claim are ONE service call** (R-6-liq-settle). The engine's `approve` carries no payload — `wf.execute_action` takes an actor, a comment and a CAS token, nothing else — so `services/settlement.py::record_settlement` records the settlement on the advance and THEN drives that same `approve`, inside one transaction. The split alternative was rejected on a concrete failure, not on taste: `mark_settled` releases the PD 1445 §89 slot the instant it commits, so a settlement whose approve never followed would let the traveller take a NEW advance while a live liquidation still stood against the old one — and `0020`'s belt then forbids repairing it. No compensating transaction exists anywhere in this codebase. `lifecycle.claim_action` gains the chokepoint: a liquidation leaving `handed_to_fms` must find its advance already settled, else a 409 NAMING the settle route | workflow-standards §11 (new, generalized from here) |
| §9.2's decision bar renders `available_actions` verbatim | **`approve` is REWRITTEN to `settle` at liquidation@`handed_to_fms`, not dropped.** The R-4-screens rule ("never offer a button certain to fail") would say drop it — but the actor IS authorized to clear that gate; they just have to carry the money while doing it, on a different route. Dropping it leaves a hole exactly where the approver needs a button. `spawn` joins the set on the same reasoning: the alternative was the browser comparing claimant ids, which is the client computing permissions | R-4-screens' rule, read as "offer the button that WORKS" |
| §3.2 "Record settlement (refund OR / payout) \| Admin Officer, System Admin" | **`POST /claims/{id}/settle` on the UN-GATED `api/actions.py`**, coarse `reimb.claim.read` at the route + `can_manage_cash_advances` as the exact rule. Behind `require_feature` a flag-OFF would 404 the route and strand every liquidation at `handed_to_fms`, each still holding its claimant's §89 slot with no way to release it — precisely what that router exists to prevent. **`POST /claims/{id}/spawn-reimbursement` stays GATED**: it creates NEW work, which is exactly what a flag-OFF module should refuse | api-standards §9a's own argument, applied twice in opposite directions |
| §6.2 "spawns linked reimbursement of the difference — one tap, pre-filled" | **The spawn copies the trip header AND the itinerary AND links the SAME cash advance**, so `compute_claim_totals` nets `grand − advance` and DV-32 prints the standard GAM shape (*Total claim / Less: cash advance / Amount due the payee*). Parking the bare difference in `other_total` would have printed a fabricated expense category and an empty itinerary for a trip that demonstrably happened — two lies to avoid one duplication the DV's own "Less" line already explains. The link is written DIRECTLY rather than through `link_claim`, which also mirrors the deadline: a reimbursement answers no clock. **Evidence carry-over (`TO-01`/`CTC-47`) is a recorded DEFERRAL** — re-using an attachment join across two claims raises a provenance question worth answering once, generally; the FE copy says "Start your claim", never "done" | spec §8's `advance − actual`, printed the way an accountant reads it |
| — (`cash_advance_id` meant exactly one thing) | **The spawn gives it a second meaning, so three readers were kind-guarded**: `checklist_facts._deadline_facts` (a reimbursement must not inherit a `liquidation.deadline` fact), `cash_advance.remirror_deadline` (must not stamp a countdown on a spawn) and `api/deps.cash_advance_out` (a SETTLED advance reports no `deadline_state`/`days_remaining`/`overdue_note`). The last is a defect this increment created and had to fix: without it a settled-but-late advance renders a red **Overdue** ring and the COA "6% interest / salary deduction" copy forever — threatening a traveller who already answered | overloading a column is legal; leaving its readers un-told is not |
| §10 "Templates seeded from … Liquidation Report" | **LR-44 is BOUND** (`reimb.lr44` + `_lr44_body.html.j2` + the `claim_kind='liquidation'` seed row) — discharging the deliberately-inert catalog row three sessions after it was authored, the same way `deadline_check` was. **The liquidation packet came free**: `_generate_packet` already ran for every kind, so the binding simply gave it its one section | delta row 121, discharged |
| — (which certification boxes may print a name) | **A prints the claimant's name; B prints as a RECORDED FACT in a `note` beneath a blank rule; C stays blank forever.** `_dv32_body`'s rule ("a pre-filled name in a box the system cannot enforce asserts something untrue") is applied with new information, not relaxed: the workflow really does record who cleared `certify_b`, so reporting it is honest — but never on the `signature-name` line, because a name over an empty rule reads as a completed certification to whoever holds the page. For C the platform holds the ADMIN OFFICER who typed the comment, not the Head of Accounting who signed; printing the recorder there would name the wrong person in a COA certification, which is worse than a blank box | api-standards §9c corollary (new) |
| — (a Liquidation Report generated before the refund exists) | **A blank OR line IS GAM App 44 at the stage it is at** — the traveller walks the form to the cashier and the number is written on. The section is a THREE-way branch: refund + receipt / refund + a blank rule and a `note` saying *this copy predates the refund* / no refund at all. What would be dishonest is printing `₱0.00` (indistinguishable from "nothing refundable") or hiding the section so nobody learns a refund is owed. Settlement then re-renders it, and the earlier copy is **SUPERSEDED, not voided**: it was reissued, not invalidated. `doc.is_draft` is deliberately untouched — widening it would stamp a 72pt DRAFT across a numbered `LQ-` document that certification B is being asked to sign | spec §6.2 + `core/documents/snapshots.py`'s own vocabulary |
| `reimb_template_maps.claim_kind` documented as "NULL = both kinds" | **Its only reader could never match a NULL.** `documents/service.py::_bindings` used `.in_([kind, None])`, and SQL `IN` never matches NULL — so the documented semantic was unreachable, silently, and what would go missing is a government form. Fixed to the `is_(None) \| ==` form `services/checklist.py` had right all along, while the blast radius was still provably ZERO (every seeded row names its kind). That is when a predicate should be fixed | a schema comment its reader cannot honour is a lie in the schema |
| — (a defect the print layer had carried since R-5) | **`_dv32_body.html.j2` tested `{% if totals.advance %}`, and `money_str(0)` is the truthy string `"0.00"`** — so every reimbursement DV in the system printed a `Less: cash advance (₱0.00)` row. Line 71 of the same file always had it right. Fixed here, and the same guard added to `packet.html.j2` | money crosses as a 2-dp STRING; compare the value, never its truthiness |
| §9.2's packet cover (written when one claim kind existed) | **Kind-aware in exactly TWO places** — the cover's money nouns (via a `MONEY_LABELS` map beside `GROUP_LABELS`, one table of prose rather than 38 duplicated lines of markup) and `PACKET_TITLES` (a code-side dict, not a second `DocumentSpec`: forking the KEY would fork the snapshot lineage for one string). The COA checklist, the group ordering and the evidence manifest needed **nothing** — all three were already kind-aware through `checklist_view`. Rule 10 paying off a second time | delta row 111's generalization, arriving where it was aimed |
| §7 rule 5's "External > 10 working days" filter (R-4-app recorded it as an Admin dashboard filter, not a notification) | **`GET /claims?external_over=true`, counted from `holder_since` and NO new column.** For a claim sitting at `handed_to_fms`, `holder_since` IS the hand-off instant — nothing overwrites it while the state does not change — and it correctly restarts if a bounced claim is re-handed. Counted in Manila WORKING days off the real holiday calendar via `core/workdays`, one window load per page, never per row. Deliberately NOT "days since the last external event": §7 rule 5 asks how long FMS has HAD it, and a relay that says "still with Budget" is news, not progress. The threshold is config (`sla.external_followup_working_days`, default 10, fail-soft) because it is an operational tuning knob, not a rule | spec §7 rule 5 + api-standards §9e (a derived deadline value is server-computed) |
| §9.2's screen inventory (My Work, wizard, packet, tracker, approval, board…) — no "queue" row | **A queue was MISSING from the inventory and the model needs one.** `resolve_holder` sets `holder_kind='external_fms'`/`holder_id=NULL` at `handed_to_fms`, and `/my-work`'s "waiting on you" filters `holder_kind='user'` — so a claim with FMS appears in **nobody's** inbox, and the Admin Officer who handed it over had no surface that ever showed it again. That is correct holder modelling and an unusable product, which is why R-7 builds the queue FIRST: every other R-7 button hangs off a claim that could not be reached. My Work answers "what is mine"; the queue answers "what is stuck" | the §7.1 one-holder rule meeting §7 rule 5's "stalls are visible" |
| §3.2's `reimb.claim.read` as the module's read gate | **A LIST may not be keyed on it.** `staff` holds it GLOBALLY (so a traveller can read their own claim anywhere in the tree), so a list gated on it returns every claim in the agency to every employee. The queue is scoped on the OVERSIGHT permissions (`reimb.claim.review`/`.fms_update`/`.approve`) and on the SUBTREE those grants cover; holding none is a **403**, not an empty 200 — "there is no work" is a false statement where the truth is "this surface is not yours". This is R-9's "scope filters!" QA line arriving early, because the first list endpoint is where it bites. Now api-standards **§9f** | spec §3.2's global read grant vs what a list actually asks |
| — (no subtree walker in core) | **`core.org_units.descendants_or_self`, the inverse of `ancestors_or_self`.** Per-row authorization walks UP from the record; a list needs the grants' downward closure, and doing it per row is a query per row, unbounded by page size. Built in CORE beside its sibling (same recursive-CTE shape, soft-delete-stopped, depth-guarded) rather than as module SQL — rule 10 | rule 10; the RBAC scope primitive only had one of its two halves |
| §9.2's list rows (`WorkItemOut`, written when My Work was the only list) | **`QueueItemOut` EXTENDS it** rather than forking a second row mapper, and `work_item`/`holder_names` were promoted out of `api/my_work.py` into `api/deps.py` when the queue became their second caller. Two mappers for one row shape is how two lists drift apart. The queue adds exactly two fields — `claimant_display` (this list mixes travellers; My Work never has to say whose claim it is) and `days_with_fms` (**null**, not 0, when FMS does not hold it: 0 is a false answer to a question that does not apply) | one row shape, one mapper |
| §6.1 row 6's `With Budget → With Accounting → Payment Processing` (an arrow diagram) | **A closed SET, with membership enforced and ORDER never enforced** (R-7-events). The parenthetical — *"admin, any order/skips allowed"* — is the operative half, and the arrow is a typical journey rather than a sequence: FMS pays straight out of Budget, sends packets back to desks they already left, and answers "still with Accounting" twice in a week. So `record_external_event` validates membership only, repeats are legal, and the 422 message says *"in any order, and skipping any of them is fine"* out loud — an operator who infers a sequence from a three-item list will not relay Accounting on a packet that skipped Budget. The FE mirrors it: no option is ever disabled by what was relayed last | spec §6.1 row 6 verbatim; the R-9 QA line is literally "Statuses skip/reorder legally" |
| §6.1's sub-statuses shown only on the reimbursement chain | **The relay works on BOTH kinds.** A liquidation sits at `handed_to_fms` too and is exactly as invisible while it does. Delta row 116's liquidation exclusion is about `fms_returned` — a STATE, needing a screen and a transition — not about a relay that adds no state and reuses one dialog. FMS runs both packets past the same three desks | the exclusion was about states, and this is not one |
| §6.1 row 8's "terminal (admin records payout ref)" (naming no field) | **`payout_ref` + `paid_on` + `paid_by` (migration `0021`), and `record_payout` — workflow-standards §12's second instance.** Until R-7-events this transition was a bare `approve`: the claim went read-only holding no reference, no date, and no way to add either. **The reference is REQUIRED** (user-confirmed at kickoff): a terminal state that asserts nothing is the bare approve this replaces, `paid_closed` is read-only afterwards, and there is no amendment route — so the refusal names the honest alternative instead, which is to relay *Payment processing* until the reference exists. **No unique index on `payout_ref`:** one LDDAP-ADA legitimately pays many disbursement vouchers, so two claims sharing a reference is normal government practice, not a duplicate. `paid_on` is a DATE, not a timestamp — when the money moved is the auditable fact; when somebody typed it in is already `updated_at` plus the history row | workflow-standards §12 + the `0020` `settled_by` precedent |
| §6.1's one `approve` endpoint for the whole chain (R-4-app's "only the LABEL varies") | **BOTH chains' terminal rungs are now rewritten verbs**, and the rewrite is one kind-keyed table rather than two copies: `settle` on a liquidation (R-6-liq-settle), `mark_paid` on a reimbursement (R-7-events). `lifecycle.claim_action` grows the matching second chokepoint — a reimbursement leaving `handed_to_fms` must already carry a payment reference. The verb is REWRITTEN, never dropped: the actor is authorized to clear that gate, so dropping it would leave a hole exactly where they need a button | workflow-standards §12 rule 3, applied twice |
| — (no verb for a non-transition) | **`relay_fms` rides `available_actions` despite moving nothing.** The precedent is `spawn` (R-6-liq-settle): that set is the client's ONLY sanctioned answer to "what may I do here" (workflow-standards §3), and the alternative is a browser inferring a permission from a role name. Offered when the claim is at `handed_to_fms` and the actor's scoped `reimb.claim.fms_update` grant covers it — the check is duplicated in `services/actions.py` and in the route, which is the price of the R-4-screens doctrine: the button must not be offered to someone certain to get a 403, and the service must not trust the button | workflow-standards §3 + the `_can_spawn` precedent |
| §5.7 `reimb_external_event` "(FMS journey updates)" — a table, with no reader named | **Merged into `GET /claims/{id}/timeline`, not offered as a second list.** A claimant asking "where is my money" is asking ONE question, and answering it with two chronologies to interleave by hand is the tracker failing at its only job. `TimelineEventOut` gains a `kind` discriminator and **`to_status` is NULL on an external row**: a sub-status is deliberately not a workflow state (delta row 38), and letting `with_accounting` travel in the field every consumer reads as a claim status is exactly how that would quietly stop being true. **The one existing invariant this could have broken** is the positional return-reason pairing — it is computed from the history rows ALONE, before the external lane is appended, and the merge is a sort at the very end so there is exactly one line where the two lanes meet | spec §9.2 + §12; delta rows 38 and 61 |
| §12's "External status updated → Claimant" (every update) | **A relay that REPEATS the previous status notifies nobody**, and the terminal `paid` event notifies nobody either. The sentence is "your claim is NOW X" — a claim about change — so saying it twice is not news, and `notify_paid` already says the Paid one properly, with the reference and the amount on it. **The second half was a defect the LIVE SMOKE caught, not any assertion:** both messages were individually correct, and only seeing them arrive together showed a traveller getting two notifications about one payment, the less informative one first. Now pinned by a test | spec §12 read as a promise about information, not about row counts |
| §12's "Paid / Settled → Claimant, terminal, celebratory tone" | **Only the *Settled* half existed** (`notify_settlement`, R-6-liq-settle) because until R-7-events nothing recorded a payment. `notify_paid` is the other half, and it carries the payment reference — what a traveller quotes to FMS or their bank when the credit has not appeared, and the one fact they can look up nowhere else. Same mutable class as the relay, deliberately NOT the `transactional` bypass the COA liquidation ladder uses: that class exists so a traveller cannot mute a salary-deduction warning, and good news is mutable | spec §12 + the `notify_settlement` precedent |
| — (GRDS retention had no starter anywhere) | **`core.attachments.start_retention`, and the fact that every claim attachment in the system was permanently non-disposable.** `services/attachments.py` has parked `retention_starts_at=None` since R-2 with a comment promising "final settlement, which is `paid_closed` (R-7)" — nothing ever set it, so `retain_until()` returned None for every file and the disposal report said "retention clock not started" forever. Built in CORE beside `retain_until` (rule 10, the `descendants_or_self` precedent); the module names the moment, core does the stamping. Called from BOTH money terminals — `paid_closed` and `settled`. **Loaded and mutated row by row, never a bulk UPDATE**: `core/audit.py` refuses bulk ORM DML outright and is right to, because starting a legal retention period must appear in the hash-chained log (rule 5 caught this at test time). `WHERE retention_starts_at IS NULL` makes it idempotent AND stops a re-run silently pushing a legal deadline forward | rule 10 + rule 5; GRDS-2023 "10 years from final settlement" |
| — (no rule for a voided claim's evidence) | **`cancelled` deliberately does NOT start the clock** (user-confirmed at the R-7-events kickoff). A voided claim produced no disbursement, so dating a *disbursement-record* retention period from its void would assert a disposal deadline for a payment that never happened. Its files stay non-disposable — the fail-safe — and stay visible in the disposal report as an unanswered question rather than a silently-scheduled one. **A recorded deferral, pinned by a test** so a later change is deliberate rather than accidental | fail-safe beats a confident wrong answer |
| — (a test-hygiene defect the new tests surfaced) | **`tests/test_reimb_api_queue.py`'s `_backdate` had the session-#24 disease, one table over.** It aged committed claims to 21 days with FMS and never undid it, and the suite shares one database — so every run left another permanently-over-threshold row, until `?external_over=true`'s first page was nothing but old fixtures and the assertions stopped being about the claims they named. Fixed the same way: an `_undo_backdating` in a `finally`, plus per-claimant scoping on the assertions. **The rule generalizes past holidays: any fixture writing dates relative to TODAY must undo itself** | learned twice now, from two different tables |
| §9.6's board columns "In Bureau / With FMS / Done" (three names, no mapping) | **A `board_column` mapping ON the per-kind `Vocabulary`, mandatory per state, with the column sets DERIVED.** The columns are GROUPS of statuses (spec §9.2 says so: "Columns = status groups"), and the grouping is the increment's one real design decision, so it lives beside `labels` where a state cannot be authored without one. The stakes differ from a label's: an unlabelled state renders as a raw code at a user, who can SEE it is wrong; a state with no column **disappears from a peso total**, and "board totals match DB" is the one sentence spec §14 grades this surface on. `None` is therefore an authored declaration, not a gap — `draft` (nobody's oversight; My Work has it, the same reason `base_query` excludes it) and `cancelled` (spec §6.1 row 9, "excluded from KPIs" — a voided claim produced no disbursement). `_assert_board_columns` runs at import and also checks the sets are **pairwise disjoint**, because `column_totals` groups by status ACROSS kinds in one statement: a code one kind called In Bureau and another called Done would be counted twice and the board would total more than the database holds | spec §9.2/§9.6 + the `ALL_TERMINAL_STATES` "derived, never hand-listed" precedent |
| §9.6 shown for the reimbursement pipeline | **Both KINDS ride ONE board**, and `certify_b`/`certify_c` are In Bureau while `settled` shares Done with `paid_closed`. A liquidation is work in the same pipeline; forking the board by kind would ask a chief to read two boards to answer one question. `returned` and `fms_returned` are **In Bureau** too — the packet is physically back inside the bureau, bounced onto an Admin Officer's desk or back to the traveller who sits in it, and "how much is where" has exactly three answers | one pipeline, one board |
| — (the queue's `base_query` excludes terminal claims) | **`include_terminal: bool = False`, keyword-only — not a second query builder.** `base_query` is the ONE definition of "which claims may this actor see" (the join, `scope_clause`, the draft rule), and a second builder is a second copy of a *security predicate*: a drifted scope clause leaks where a drifted display mapper merely renders wrong. The widening risk is a **default** problem, not a parameter problem — every existing call site is untouched and a caller must type the flag. Explicitly rejected as too clever: *"drop the terminal rule whenever `statuses` is given"*, which would silently turn `GET /claims?status=paid_closed` on the QUEUE from an empty list into a list of paid claims. Pinned from both ends in one test | the queue's own R-7-queue docstring named this as R-7-board's problem |
| §9.6 "counts + peso totals per column header" | **ONE statement, `GROUP BY status`, `SUM((totals->>'grand')::numeric)`, bucketed in Python — never a Python sum over a fetched page.** The header counts the whole column and the page is 20 cards, so a total derived from what is on screen would under-report the bureau's exposure by exactly what did not fit, while looking entirely correct. `GROUP BY status` rather than a SQL `CASE` built from the mapping, for three reasons and the third is the real one: the mapping stays in one place instead of two, at most a dozen rows come back, and **an unmapped status becomes observable** — a code left over from a retired definition version lands in no column and is LOGGED (`reimb.board.unmapped_status`), where a `CASE` would silently `ELSE NULL` it. Which is also why the aggregate does NOT pre-filter on `ALL_BOARD_STATES`: filtering in SQL would hide the very rows the warning exists to catch. **Rejected: `core_workflow_instances.amount`** — already joined, a real `numeric(12,2)`, no cast — because it is the engine's tier-routing guard input, not the module's money of record, and a board totalling the routing input would drift from the claim the day those two diverge. The `::numeric` cast is safe only because `services/compute.py` is the sole writer of `totals["grand"]` and goes through `money_str`; that is now a load-bearing invariant of another module and is named in the docstring | spec §9.6 + §14 "board totals match DB"; money standards (server computes, UI displays) |
| §9.6 "Done" (unbounded, by implication) | **Done covers a recent window — `board.done_window_days`, default 90 calendar days, fail-soft** (user-confirmed at the R-7-board kickoff). `paid_closed` and `settled` accumulate forever, so an all-time figure stops saying anything about how the bureau is doing: by year two it is a number nobody reads. In Bureau and With FMS stay **unbounded**, deliberately — a claim stuck since March is precisely what spec §7 rule 5 calls non-negotiable to show, and ageing it off the board would hide it. The window's field is **`updated_at`**, because a terminal claim is read-only with no amendment route, so its `updated_at` IS the closing instant and it is the one field that means that on both kinds; `paid_on` is reimbursement-only and records when the MONEY moved, which can precede the recording. `done_window_days` rides the response so the header qualifier quotes the server's number rather than a literal | spec §13's time filters arrive in Stage H; a board still has to be readable before then |
| §9.6 "clicking a card opens the tracker" vs ui-standards' "a board `<article>`, **no link affordance**" | **The STANDARD is amended, not quietly contradicted** — precedence puts `docs/standards/` above the reference spec, so the inventory line gets rewritten rather than ignored. `PipelineCard` gains an optional `to`; the `<Link>` wraps the **title** with a stretched overlay (`after:absolute after:inset-0`) so the whole card is clickable while the accessible name stays the title alone. Wrapping the entire card in one anchor would also have worked, and would have given every card a link named "RB-2026-0001 Handed to FMS Iloilo field visit M. Santos · 12 working days with FMS · ₱6,500.00" — read aloud in full, forty times down a column | precedence (standards > references spec) + WCAG AA link naming |
| `GET /claims/board` (the obvious URL) | **`GET /board`.** `claims.router` is included before `queue.router` and declares `GET /claims/{claim_id}`; FastAPI matches in registration order and the path param has no convertor, so `/claims/board` is read as a claim id and **422s**. Making that URL work would mean pinning `include_router` order — a dependency nothing in the codebase declares, invisible at both call sites, and silently broken by a future alphabetization. A sibling segment is correct by construction. Pinned by a test that asserts BOTH (`/board` 200, `/claims/board` 422) so the reason survives the decision. Now api-standards **§9g** | route-matching order is not a contract |
| §9.2's list rows again (`QueueItemOut`, delta row 140) | **The row shape is reused verbatim; only the META LINE is a third composer.** Row 140's rule is one *row mapper* for one row shape, and it holds — the board sends `QueueItemOut` unchanged and `_queue_rows`/`_urgency_first` were extracted from `api/queue.py` so three columns share ONE batched pass (one holiday window, one `DISTINCT ON`, one due-date query for the whole board rather than nine round-trips). What could not be reused is `queueMeta`: a terminal claim has no holder and no `holder_since`, so `days_in_state` is 0, and the queue's wording would print **"0 days in this step" on a claim paid three weeks ago** — a false statement the queue never had to make, because a queue has no terminal rows. `boardMeta` dates it by `updated_at` instead, and the shared `daysPhrase` is extracted so the working-days-with-FMS vs calendar-days-in-state distinction cannot fork | one row shape, one mapper — and one honest sentence per surface |
| — (Done's ordering) | **Done sorts `updated_at DESC`, not longest-waiting-first, and skips the urgency lift.** A terminal state CLEARS the holder, so `holder_since` is null on every Done row: "longest waiting" is not merely wrong there, it is undefined, and every row would tie on NULL and fall through to `id`. What a Done column is asked is "what just finished". The urgency lift is for work that still needs chasing, and floating a finished claim over a more recently finished one answers a question nobody asked | spec §9.6's "overdue cards float to top" is about live work |
| — (an accepted inconsistency worth recording) | **The aggregate and the three card queries are separate statements under READ COMMITTED**, so each takes its own snapshot: a claim that transitions mid-request can be counted in Done and carded in With FMS for exactly one render. **Documented and accepted** — a board is a dashboard, the header is the authority, and a refresh self-heals; raising the handler to REPEATABLE READ is disproportionate to a one-render skew. Recorded so a later reader does not "fix" it as a phantom bug | proportionality; the alternative costs more than the defect |
| §13's "unlinked to activity" filter on the board | **DEFERRED to Stage H with the rest of §13's KPI surface** (cycle time, return rate, top return reasons, time filters, deltas), where master-plan §119 puts it. R-7-board's headers carry a count and a peso total and nothing else (user-confirmed at the #24 kickoff). Recorded as a decision rather than left silent, so it reads as scope at the QA gate and not as an oversight | master-plan §119 owns the KPI surface |
| — (a new test-hygiene rule this surface introduces) | **On a COUNTED surface, absolute assertions are the shared-database trap wearing a new coat.** Every other test's committed claims sit in these three columns, so `count == 3` is a claim about the whole suite. `tests/test_reimb_api_board.py` asserts through a **SCOPED overseer** whose office `standard_cast` created fresh for that test — which makes every count and total about that test's claims and nothing else — and the two tests that genuinely need a global grant assert membership only, never a number. Date-relative fixtures still undo themselves in a `finally` (delta row 151, learned twice) | delta row 151, generalized from dates to counts |

| §5.6 `promoted_check bool` on `reimb_return_reason_catalog` | **REINTERPRETED at R-8 from "this reason CAN be promoted" to "this reason IS promoted"**, which is the only reading spec §11 can use (the promotion has to be *recorded* somewhere, and this is the column the spec put there). The R-1 seed had shipped `True` on three rows under the old gloss; migration **`0022`** resets them, because under the new meaning they are three warnings every claimant sees that nobody authored. No new table: the row is audited (`updated_by`/`updated_at` + the hash chain), so "who promoted this and when" is already answerable, and a promotion table would duplicate the audit log with a worse guarantee | rule 10 (use the pre-built thing) + spec §5.6 owns the column |
| §11 "promote to pre-check … it writes an `auto_checks` row" | **A promotion writes the reason's `promoted_check` flag, NOT an `auto_checks` element**, and the divergence is semantic rather than convenient. Our `auto_checks` are **item-scoped**: a check runs against one `reimb_checklist_catalogs` row, its flag sets that item to `auto_flagged`, and `engine.SATISFIED_STATUSES` counts `auto_flagged` as **DONE** — so promoting a reason through `auto_checks` would mark a document satisfied and land in the approver's flag list. A return-reason advisory is **claim-scoped**, pre-submit, and for the claimant. Two further blockers: there is no reason→catalog-row mapping, and reasons like `PER_DIEM_CALC` have no catalog row at all. What §11 actually asks for — *"no code change"* — is honoured exactly: a promotion is one boolean, and `GET /return-reasons` carries it to the wizard | spec's INTENT (data, not deploy) over its example encoding |
| — (the seed defect this prevents) | **`promoted_check` is now ABSENT from every seed row, and its absence is load-bearing.** `apply_dataset` writes only the keys a row dict contains, so a column named in the seed is re-asserted on every run — which for this one would mean **every `seed` silently demotes every reason an Admin Officer promoted**, on the next deployment, leaving nothing behind but a warning that stopped appearing. Omitted, the column keeps its `server_default false` at insert and is owned thereafter by one writer (`services/insights.py::set_promoted`). `test_reimbursement_seeds.py`'s assertion inverted to "nothing ships promoted", which is also the canary for a test that promotes and forgets to demote | seed semantics: a dataset asserts what it lists |
| §11 "Insights ranks reasons by 90-day count with trend" | **ONE grouped statement over BOTH windows** (`count(*) FILTER (…)` twice), never two round-trips: a return landing between two queries would be counted in neither, which on a surface whose only job is counting is a wrong answer rather than a rounding error. `reason_ids` is unnested with `jsonb_array_elements_text` and **grouped on the TEXT element — deliberately NOT cast to `bigint` in SQL**. `queue._GRAND`'s `::numeric` is safe only because `compute.py` is the sole writer of what it casts; `reason_ids` is FK-less JSONB with no database-level guarantee, so one junk element would 500 the whole surface instead of surfacing one bad row. Resolution happens in Python and an unresolvable id is **logged** — `column_totals`'s unmapped-status rule, same reason | R-7-board's GROUP-BY-then-bucket-in-Python shape, copied with its reasoning |
| — (what a "count" counts) | **Two true numbers that answer different questions, and the header takes the second.** A return citing three reasons contributes 1 to each ranked row, so the column sums higher than `total_returns`, which counts PACKETS that came back once each. The copy says "returns citing this" on a row and "N returns in the last 90 days" in the header. **Neither is a rate** — a return rate needs a submissions denominator (spec §13 → Stage H), and a plausible-looking percentage is the number people quote | spec §13 stays in Stage H; half a rate is worse than none |
| §6.1 row 9 "Cancelled/Void … excluded from KPIs" | **Returns on claims later CANCELLED still count in Insights** — a deliberate divergence, pinned by test. The board honours the exclusion (a voided claim moved no money), but this is not a KPI: the fact being counted is the **return event**, not the claim's outcome. A packet that came back for a missing OR came back for a missing OR, and cancelling it afterwards does not unlearn the lesson. One predicate to flip if the resident COA auditor disagrees | the unit of analysis is the return, not the claim |
| — (a reason that stopped happening) | **A reason with zero returns this window but some in the previous one is KEPT and sorts last, as `trend: "down"`.** Dropping it because its current count is 0 would delete the only evidence that a promotion worked, on the one surface built to show it. It is excluded from `total_returns`, which describes the window — the header counts the period, the row explains the period before it | the payoff of the loop must be visible |
| §11 "aggregates only … per-person counts only to the person themselves" | **The scope IS the privacy boundary** (new api-standards **§9h**). Insights is read under `queue.oversight_scope` on the SAME `base_query` as the queue and the board, so it can only aggregate rows the actor could already open one at a time — which makes the privacy claim structural rather than a promise in the copy, and is why **no minimum-cell suppression is applied** (a small division's counts are about few people, and the actor already oversees exactly those people). The response carries **no person dimension and nowhere to add one**. The claimant-facing advisory carries the **reason and never a count**. A traveller gets a 403 with its own slug (`reimb_insights_not_permitted`), not the queue's — "your claims are on My Work" answers no part of "why do packets come back", so the message names their own claim tracker | spec §11 + §14.7's ids-not-values pattern |
| — (the write rule is narrower than the read rule — a first) | **Promotion needs an AGENCY-WIDE `reimb.claim.review` grant**, while reading needs only oversight of somebody. A promotion shows a warning to every claimant in the tenant, so a division-scoped grant reaching it would be a scope escalation that looks exactly like the button working. Narrower on the permission too: `oversight_scope` unions review/approve/fms_update because any of them makes you an overseer (right for a read), but authoring the taxonomy is the Admin Officer's job — `seeds.py`'s `owner` field says so. `can_promote` rides the envelope so the UI never offers a doomed button (R-4-screens doctrine) | api-standards §9h |
| §11 "a warning-level auto-check at wizard step 5" | **Advisory, and structurally incapable of gating.** Nothing the promotion writes is read by `checklist.assert_packet_complete`; the Callout is not in `blocked` and never touches Submit. R-3's hard gate is about MISSING DOCUMENTS, and conflating "often returned" with "incomplete" would let a statistic refuse a legitimate claim. **The fail-safe direction here is the OPPOSITE of the usual one** — everywhere else the safe answer is to block or flag; for an advisory it is to say nothing, so a failed or still-loading taxonomy fetch renders nothing at all, and a retired reason cannot be promoted (422). An unexplained warning is worse than no warning | spec §9.1 principle 4 + R-3's gate is about documents |
| — (the wizard reads the approver's taxonomy) | **No second endpoint for the advisory.** `GET /return-reasons` — the return dialog's own chip source — gained `promoted`, and the wizard filters on it. One cached list means the wording a claimant is warned with and the wording an approver picks can never drift, and it is what makes the acceptance line testable end to end: promote → invalidate `reimbKeys.returnReasons()` → the warning is there, with no deploy | one list, one set of labels |
| — (a THIRD test-hygiene shape) | **A promotion mutates SHARED SEEDED DATA**, tenant-wide by design. A test that promotes and does not demote leaves a warning standing for every later test and for the next developer's dev database — the same class as the aged claims that leaked for three sessions (#24–#26) and the counted-surface trap (row above), wearing a third coat. Every promoting test undoes itself in a `finally`; `test_reimbursement_seeds.py`'s "nothing ships promoted" is the canary. Also: `reimb_return_events` REVOKEs UPDATE, so a window/trend fixture **INSERTs** a row with an explicit `created_at` — it cannot backdate one | delta rows 151/165, generalized from dates → counts → shared seed rows |

| §14 R-9 "flag ON for pilot cohort only" | **A cohort is a GRANT LIST, not a flag dimension.** `core_feature_flags` stays a tenant-wide boolean; the flag answers *"is this module on"*, RBAC grants answer *"for whom"*. Verified before deciding: **nothing in the codebase auto-assigns a role** — there is no default-grant path — so a user reaches the module only because an administrator granted them one, and the grant list already IS the cohort, scoped per org unit, time-bounded, revocable and audited. Giving the flag an org dimension would have been a second, weaker copy of that, plus a rewrite of the one endpoint the hard prohibitions say must never 500. **The honest risk is stated rather than discovered:** a cohort you cannot enumerate is a cohort you cannot verify, and one global `staff` grant admits an outsider invisibly — so the posture ships with its control, `bootstrap pilot-roster`. Pinned by the census driving all 32 routes with a grant-less user | api-standards §9i; spec §14 asks for a cohort, not for a schema |
| §14 R-9 "security suite (scope filters!)" | **Tested by ATTACKER, not by endpoint — and the difference found a defect.** Every increment tested its own surface; what had never been tested was the SET. `submit_claim`/`cancel_draft_claim` checked claim STATE before OWNERSHIP, returning `409 already_submitted` to a stranger — an enumeration oracle over every claim in the agency (exists-unsubmitted / exists-submitted / never-issued) from any `staff` login, with **every existing test passing** because each submitted its own claim. The rule was already written in `services/drafts.py`'s comment and two functions one file over did not follow it. Now **api-standards §9i**: authorization precedes state. Fixed in three places incl. `claim_action`'s no-instance branch (the one branch the engine cannot authorize, since authorizing needs an instance) via the new `lifecycle.may_see_claim` | a doctrine in one module's comment is not a standard |
| — (the census, and why it reads the app) | **`test_reimb_authz_census.py` enumerates `app.routes`; a route with no declared rule FAILS.** §9f had been applied four times by remembering. The table records each of the 32 routes' gate class, route permission and exact service rule, and is machine-checked against the running app through two new markers (`oc_permission`/`oc_feature_flag`) on core's dependency factories — a closure is opaque to introspection, and grepping the source would have re-created the hand-list problem this replaces. Reading the table also makes §9f's warning visible as data: **28 of 32 routes are gated on a permission an ordinary traveller holds**, so on almost every route the route gate provably cannot be the scope rule | absence never fails a hand-written list |
| — (test hygiene, made mechanical) | **The fourth recurrence is where you stop asking people to remember.** Sessions #24–#27 each lost time to shared state left modified: a holiday row, aged `holder_since`, a promoted reason. Every fix was a `finally` plus a docstring. R-9 added session-scoped **`seed_guard`** — snapshots every seeded row's mutable columns and FAILS the run on unrestored drift (proven against a deliberate leaked promotion) — and made `_backdate` a **context manager that owns its own undo**, so the aging cannot be taken without the restore. Guards LIVE rows only: a properly retired row (rule 6) is not drift, but retiring a genuinely seeded one still reports | delta row 168's third shape, now enforced rather than documented |
| — (`verify_chain`'s real limit) | **Its budget is MEMORY, not time.** 501,423 audit rows → 18.7 s and **1.47 GiB peak RSS** (~3 KiB/row, linear, no headroom trick). 19 s is nothing for a job nobody runs in a request path; 1.47 GiB is not nothing at 3× that. **Measure RSS, not `tracemalloc`** — the first pass used the latter and reported a 77.7 s wall time, ~4× inflated by its own tracing overhead, which would have sent someone optimising a 19-second job. Threshold recorded at **≈1M rows** with the batched replacement sketched, in database-standards §7a. Worth stating because the failure mode is an OOM-killed verification, which reads as *"the integrity check is broken"* at exactly the moment somebody is asking whether the log can be trusted | a budget nobody wrote down is a budget nobody meets |
| §14 fixtures "used everywhere" | **Data, never workflow history.** `load-pilot-fixtures` builds the six travellers, ten trips and aged advance with **server-computed** money (the §8 example returns ₱6,500 from the engine; the figure appears nowhere in the fixture file) and leaves every claim a DRAFT. Submitting them would mean writing hash-chained audit rows asserting people made decisions they never made — in the one structure whose entire value is that you can believe it. The manual test guide (§4-M) drives the chain by hand. Also: the advance goes through `services/cash_advance` rather than a bare INSERT, because the first attempt's direct insert left `deadline_date` NULL — an advance with no countdown, which is the one thing the fixture exists to show | rule 10 (sanctioned writer) + an audit chain is only worth what it asserts |

*(Grows as build proceeds — every divergence from the spec lands here.)*

## 3. R-0 confirmations tracker (spec §15 — user decisions)

- [x] **30-day liquidation clock: CALENDAR days, `basis` a live config switch**
      (R-6-clock kickoff, **user-CONFIRMED 2026-08-04**, session 21) — COA
      Circular 97-002's text says "30 days" with no working-day qualifier, so
      the seed stays `{"days": 30, "basis": "calendar"}`; `services/deadline.py`
      honours a `working` basis if DOH practice is ever confirmed, making that a
      config edit rather than a code change. The guess would have mattered: the
      same "30 days" is 12 calendar days apart between the two bases
- [~] **Certification chain (A/B/C) — SHAPE settled at R-6-liq-chain
      (user-confirmed 2026-08-04, session 22); AMOUNT TIERS still open.** The
      authored chain is `draft → certify_b (Director IV, the new
      `reimb.liquidation.certify`) → certify_c (Head, Accounting Unit — signed on
      paper, recorded by the Admin Officer under a mandatory comment) →
      handed_to_fms → settled`, with **certification A folded into submit**
      because the claimant is the maker. What remains open is the same thing that
      has been open since R-4-app: DOH DO 2019-0225 / -0225A as the peso-band
      delegation source. Both chains stay untiered until it is obtained, and both
      gain tiers as an authored **v2** — in-flight items finish on v1
- [ ] Wet-signature capture points vs digital approvals — settle per artifact
      with the resident COA auditor (RA 8792 / COA 2021-006; master plan §4 #5).
      **R-6-liq-chain narrowed it:** certification C is recorded as a mandatory
      comment on the transition, and `CRT-C` (`{"always": false}`) is where the
      signed page is filed. Binding a frozen SNAPSHOT to the step — core-service
      #3's signature half — is what is still unbuilt, and it is the thing this
      item actually has to answer.
      **R-6-liq-settle narrowed it again, from the PRINT side:** GAM App 44 now
      states exactly what the platform holds and no more — A names the claimant,
      B reports who cleared `certify_b` in a note beneath a blank rule, and C
      stays blank because the recorder is not the signatory. So the question is
      no longer "what may we print"; it is only whether the auditor requires the
      signed page to be BOUND to the step as a frozen snapshot, or whether
      filing it under `CRT-C` suffices. One question, one artifact
- [ ] **Amount tiers for BOTH chains** — DOH DO 2019-0225 / -0225A as the
      peso-band delegation source (split out of the certification item above,
      which is otherwise closed). Both chains stay untiered until it is
      obtained; tiers land as an authored **v2** so in-flight items finish on v1
- [x] **What the Admin Officer records when FMS pays: ONE reference + a date,
      and the reference is REQUIRED** (R-7-events kickoff, **user-CONFIRMED
      2026-08-05**, session 25) — spec §6.1 row 8 says "admin records payout
      ref" and names no field, so `0021` adds `payout_ref` + `paid_on` +
      `paid_by` and nothing more. Richer shapes (a DV/ADA split, an echoed
      amount) become an authored v2 if the accountant confirms DOH BLHSD's FMS
      actually quotes two references — the same posture the untiered chains
      take. **No unique index:** one LDDAP-ADA legitimately pays many vouchers.
      Required because `paid_closed` is read-only with no amendment route, so a
      blank reference would recreate the bare `approve` this replaced; the
      refusal names the honest alternative (relay *Payment processing*)
- [x] **GRDS retention starts at the two MONEY terminals only** (R-7-events
      kickoff, **user-CONFIRMED 2026-08-05**, session 25) — `paid_closed` and
      `settled` stamp `retention_starts_at`; **`cancelled` deliberately does
      not**, because a voided claim produced no disbursement and dating a
      disbursement-record retention period from its void would assert a disposal
      deadline for a payment that never happened. A cancelled claim's files stay
      non-disposable (the fail-safe) and stay visible in the disposal report as
      an unanswered question. Revisit only with the resident COA auditor
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
| R-2-wizard | Claim wizard **on the shell** + **My-Work inbox** — the module's first HTTP surface: 9 endpoints under `/api/v1/reimbursement` (draft create w/ server-side directory prefill + `is_jo_cos` derivation, read w/ §3.2 owner-or-scoped authz, PATCH, bulk legs replace w/ soft-deletes, `/compute` returning server totals, `/submit` = `lifecycle.submit_claim` (routes `returned`→resubmit), `/cancel`, `/my-work`, `/regions`) behind the new `require_feature`→404 gate; `lifecycle.create_draft_claim` (holder from birth) + `services/drafts.py` (business-field writes + stale-totals clearing); `other_total` column (`0016`, resubmit-reset fix). FE: 4-step GOV.UK wizard (react-hook-form 7.83 + zod 4.4.3, shape-only) w/ task-list save-and-return, check-your-answers + RB- confirmation, My-Work landing; Form-field family (Select/Textarea/Checkbox/RadioGroup) + SummaryList + ConfirmationPanel + WorkItemRow inventory additions (ui-standards §3/§8 amended); `set-flag` bootstrap subcommand (dev flag ON) | **done** (session 16) | pytest 442 (+29), lint-imports 3/3, `0016` reversible, FE gate green (75 tests incl. first page-level tests); 45-agent adversarial review — 13 findings fixed pre-commit; e2e smoke via :5174 (flag→config, 401 gate, SPA) | 16 |
| R-3 | **Checklist engine + uploads** — core-service #7 as a PURE core package (`core/checklist/`: the §5.3 grammar + the six auto-check types + idempotent reconciliation + the blocking rule, all over dataclasses); module-side `checklist_facts.py` (the published fact contract), `checklist.py` (materialize / attach / detach / the two gate asserts), `attachments.py` (the core-attachments seam + the `reimb_claim` holder authorizer — zero core router change); migration `0017` (item uniqueness index, `circular_version` pinning, the `retention_class` bug fix); the HARD submit gate on submit/resubmit + the approve-side gate + `available_actions` filtering; `GET`/`POST`/`DELETE` `/claims/{id}/checklist…` on the gated router (api-standards §9b NEW). FE: the wizard's 5th **Documents** step (grouped GOV.UK task list, per-item upload, the §9.1 progress line), the Review submit gate with per-blocker deep links, the approver's amber flag callouts + red missing-document callout, inventory rows 20–21 (**FileUpload** + **Callout**) and the TaskList `action`/`detail`/`id` amendment | **done** (session 18) | pytest **616/616 on a clean DB** (+146), lint-imports 3/3, `0017` reversible + `alembic check` clean, FE gate green (137 tests, +41); live smoke: 422-then-submit, holder-scoped downloads, approve-past-a-flag | 18 |
| R-4 | Approval chain + work management — **ships the shared core workflow engine** (first consumer). **Engine core shipped 2026-07-27** (session 11, `core_workflow_*`, migration `0012`). **R-4-app shipped 2026-07-29** (session 15): the `reimbursement.claim` definition v1 (spec §5.5 role chain, tiers deferred — delta register), `submit_claim`/`claim_action` lifecycle service (atomic totals + `RB-` ref + instance + status/holder/next-action sync + history), working-day SLA stamping + escalation delivery + the 2-WD holder-only ladder via `register_sla_enqueuer` + `ops.reimb_sla_reminders`, bootstrap `seed-workflows`, migration `0015` (claim↔instance unique belt). **My-Work inbox → R-2-wizard** (scope note). **R-4-screens shipped 2026-08-03** (session 17): the approver surface — un-gated `api/actions.py` (`/approve` + `/return`, api-standards §9a), ≥1-reason enforcement + the replay-duplicate fix in `claim_action`, `services/actions.py` (per-actor action set + the §6.3 SLA badge), `api/tracking.py` (`/timeline` + `/return-reasons`), `available_actions`/`row_version`/`sla_*` on `ClaimDetail`, core `available_actions` filtering segregation + already-acted (Rule 10). FE: the phone-first decision bar folded into `/claims/:id` (sticky `DetailPage.actions`), the return dialog (ChipGroup + FormDialog, inventory rows 18–19), the claim tracker, My-Work urgency chips | engine core ✅ / R-4-app ✅ / **R-4-screens done** | pytest 470 (+28), lint-imports 3/3, `alembic check` clean (no migration — head stays `0016`), FE gate green (96 tests, +21); live smoke 14/14 incl. the whole chain to `paid_closed` + the flag-OFF action contract | 11, 15, 17 |
| R-5-gen | **Template auto-assembly** — core-service **#8** (`core/documents/`: registry + autoescape/StrictUndefined Jinja env + token-built print stylesheet + **injectable** WeasyPrint renderer + the ops enqueue seam) and the **snapshot half of #3** (`core_document_snapshots`: freeze/supersede/void, content-hash + context-fingerprint, `stale_snapshots()` re-flag). Module consumer generates **IOT-45 / AR-01 / DV-32** from claim data, stores each through core attachments with the new `core_attachments.origin='generated'` (born scan-clean, served **inline** so it previews), joins it to the claim, and flips the item via the new `checklist.mark_generated` — the one bootstrap of a status R-3 could write nowhere. `reimb_template_maps` built as a binding table + seeded. **Draft pre-submit → authoritative regeneration at submit**; any claim edit voids the packet. FE: Generated cards with preview + the §19.12 degrade notice. Migration `0018`. | ✅ complete | 19 |
| R-5-packet | **The combined printable packet + the §9.2 approver preview** — `reimb.packet` as a **claim-level artifact** (registered with #8, deliberately unbound in `reimb_template_maps`, `checklist_item_id = NULL`); `packet.html.j2` composing cover → COA checklist → evidence manifest → the three forms **by Jinja include, not PDF merge** (form bodies extracted to `_*_body.html.j2` partials); the manifest **indexes** uploads with their SHA-256 rather than embedding them; `build_packet_context` + the shared `comparable_context` (cover prints the source fingerprint + each form's content hash); attach/detach now void the packet; `PacketOut` on `ClaimDetail`; the generate endpoint's **second door** for a scoped reviewer/approver. FE: `PacketPreview` on `/claims/:id`, Review and the confirmation — frame from `lg`, link everywhere. **No migration — head stays `0018`.** Closes module-doc row 58 and completes R-5 | ✅ complete | pytest **658 + 1 pre-existing** (+9), lint-imports 3/3, `alembic check` clean, FE gate green (**150 vitest**, +10); live smoke through the real worker + real WeasyPrint: **6-page packet**, void-on-attach → regenerate, manifest content | 20 |
| R-6-clock | **Cash advances + the COA 30-day liquidation clock** — R-0 item 1 CLOSED (calendar, `basis` a live switch); `services/deadline.py` (pure calculator + the §6.3 due-soon window) and `services/cash_advance.py` (the single sanctioned writer of `reimb_cash_advances`, §89 as a named 409, deadline pinned on `date_return` only); migration `0019` (`deadline_date` + `deadline_basis`, backfilled); new `reimb.cash_advance.manage` RBAC + the `liquidation.overdue_note` seed; 4 routes on the gated router with a **server-derived** countdown; `deadlines` fact wired so `deadline_check` stops returning `skipped` (`FACTS_VERSION` → 2); the **D-7/D-3/D-0/overdue ladder** (`sweep_liquidation_reminders` + `ops.reimb_liquidation_reminders`, daily 08:35 Manila) which also flips the advance to `overdue`; `CashAdvanceOut` on `ClaimDetail`. FE: **CountdownRing** (inventory row 22), the CA card, the Accounting register, the My-Work section and the claim rail. **Also fixes the 3-session-old SLA-ladder failure and the production defect behind it.** | ✅ complete | pytest **737 (+79), 0 failures** (the pre-existing one is fixed), lint-imports 3/3, `0019` reversible + `alembic check` clean, seeds ×2 no-op, FE gate green (**168 vitest**, +18) + build; live smoke: pinned clock, §89 409, D-7→D-3→D-0→overdue→repeat through the **real Celery worker**, idempotent re-beats, authenticated HTTP round-trip | 21 |
| R-6-liq-chain | **The liquidation workflow** — the status vocabulary GENERALIZED to one `Vocabulary` per claim kind (plus the derived `ALL_TERMINAL_STATES` union that cross-kind SQL needs); `reimbursement.liquidation` as a SECOND definition on the shared engine (`draft → certify_b → certify_c → handed_to_fms → settled`, certification A folded into submit, no new engine verb, `_assert_graph_invariants` now vocabulary-parameterized); new `reimb.liquidation.certify` RBAC; `LQ-YYYY-NNNN` via core-service #5; `services/liquidation.py::start_liquidation` (the create-from-advance path, owner-only, one-live-per-advance under a row lock); the liquidation checklist catalog incl. **the first seeded `deadline_check`** (`LIQ-30`) and CTC-47 on both kinds; `POST /cash-advances/{id}/liquidate` + `liquidation_*` on `CashAdvanceOut`. FE: the `ClaimStatus` union + the certification labels/consequences, `LiquidateAction` on the cash-advance card, the kind in the tracker title. **No migration — head stays `0019`.** | ✅ complete | pytest **771 (+34), 0 failures**, lint-imports 3/3, `alembic check` clean, seeds ×2 no-op, FE gate green (**177 vitest**, +9) + build; live smoke **23/23** through the real stack: authenticated HTTP round-trip, §89-style 409s, and the whole chain to `settled` | 22 |
| R-6-liq-settle | **Settlement — the answer's content.** `services/settlement.py` (`record_settlement` records the money AND drives the terminal `approve` in one transaction — the engine's verb carries no payload, so a data-carrying decision is a separate PRIOR call; plus `spawn_reimbursement`, spec §6.2's "one tap"); `cash_advance.mark_settled` (written from scratch — `PROGRESS.md` wrongly said it existed) with `settled_at`'s first-ever writer; the chokepoint in `claim_action` (a liquidation may not reach `settled` before its advance is closed) and the `approve → settle` verb rewrite in `claim_actions`; **GAM App 44** (`reimb.lr44` + `_lr44_body.html.j2` + the binding row that discharges the inert `LR-44`), the `advance`/`settlement`/`certifications` context blocks (unconditional — StrictUndefined), `MONEY_LABELS` + `PACKET_TITLES` making the packet kind-aware; migration `0020` (5 settlement columns, the spawn link, and R-6-liq-chain's deferred one-liquidation belt); the un-gated `/settle` + gated `/spawn-reimbursement`; the over-advance nudge. **Four fixes carried:** the `_bindings` NULL predicate, DV-32's `"0.00"` truthiness, and three `cash_advance_id` readers the spawn newly overloads. FE: `SettlementDialog` + `SettlementOutcome`, the `settle`/`spawn` verbs, a settled advance stops counting down | ✅ complete | pytest **807 (+36), 0 failures**, lint-imports 3/3, `0020` reversible + `alembic check` clean, seeds ×2 no-op, FE gate green (**186 vitest**, +9) + build; live smoke **25/25** through the real stack + a print-layer check that the reissued LR-44 carries the OR and its predecessor is `superseded` | 23 |
| R-7-queue | **The oversight queue — making FMS-held work findable.** Spec §14's R-7 row is four deliverables ("FMS statuses, external events, board, admin queue"), split three ways at kickoff (user-confirmed) with the queue FIRST because nothing else in R-7 is reachable without it: a claim at `handed_to_fms` is held by `external_fms` and so appears in nobody's My Work. Core: **`descendants_or_self`** (the missing inverse of `ancestors_or_self` — a list needs the grants' subtree closure in ONE query). Module: `services/queue.py` (`oversight_scope` over the OVERSIGHT permissions, never the globally-granted `reimb.claim.read`; `days_with_fms` in Manila working days off the holiday calendar, one window per page; the config threshold), `api/queue.py` = **`GET /claims`** on the gated router with `status`/`kind`/`claimant_id`/`external_over` + `limit`/`offset` and an honest `total`, `QueueItemOut` extending `WorkItemOut`, `work_item`/`holder_names` promoted into `api/deps.py`, the new `reimb_queue_not_permitted` 403 that names My Work, and the `sla.external_followup_working_days` seed. FE: `ClaimQueuePage` (the List page's **first real `filters` row**), the `queueChip`/`queueMeta` display rules, `useClaimQueue`, the route + the role-gated nav entry. **No migration — head stays `0020`**; the clock derives from `holder_since`. New standards: **api-standards §9f** (a list may not borrow a row's read rule) + the ui-standards §4 filter-row note | ✅ complete | pytest **822 (+15), 0 failures**, lint-imports 3/3, `alembic check` clean (no migration), seeds ×2 no-op, FE gate green (**193 vitest**, +7) + build; live smoke **23/23** through the real stack incl. the hand-counted working-day figure and the traveller's 403 | 24 |
| R-7-events | **The FMS journey record — relaying what FMS says, recording what FMS did.** `services/external.py`: the FIRST EVER writer of `reimb_external_events` (shipped inert in `0013`, zero writers and zero readers until now) — `record_external_event` is a PURE APPEND enforcing MEMBERSHIP of the closed set and never ORDER (spec §6.1 row 6's "any order/skips allowed"), on BOTH claim kinds; plus `record_payout`, workflow-standards §12's **second instance** (reference + `paid` event first, then the unchanged `approve`, one transaction) and `lifecycle._assert_payout_recorded`, the chokepoint that refuses the bare verb and NAMES `/mark-paid`. Migration **`0021`** (`payout_ref` / `paid_on` / `paid_by`; no unique index — one LDDAP-ADA pays many vouchers). Core: **`attachments.start_retention`**, which finally starts the GRDS-2023 clock `services/attachments.py` has been parking since R-2 — every claim attachment in the system was permanently non-disposable. Two spec §12 notifications (`notify_external_status`, `notify_paid` — the *Paid* half of a row only half-built at R-6-liq-settle). `GET /claims/{id}/timeline` merges both lanes into ONE chronology with `to_status` NULL on an FMS row. Routes: relay on the GATED router (a relay strands nothing), `/mark-paid` UN-GATED beside `/settle` (it drives a transition). FE: `FmsStatusDialog` + `MarkPaidDialog` + `PaidOutcome`, the merged tracker, the rail's "Latest from FMS", the queue row's last-heard status | ✅ complete | pytest **860 (+38), 0 failures**, lint-imports 3/3, `0021` reversible (down→up) + `alembic check` clean, seeds ×2 no-op, FE gate green (**214 vitest**, +21) + build; live smoke **28/28** through the real stack, which is what caught the duplicate-payment-notification defect | 25 |
| R-7-board | **The pipeline board — how much is where. CLOSES R-7.** Spec §9.6's "module's public face": three columns (In Bureau / With FMS / Done) that are GROUPS of statuses, each headed by a count and a server-summed peso total. `services/status.py` gains a per-kind **`board_column`** mapping ON the `Vocabulary` — mandatory per state, with the column sets derived and an import-time invariant that also proves them **pairwise disjoint** (the cross-kind `GROUP BY` would otherwise double-count). `services/queue.py` gains **`include_terminal`** on `base_query` (the trap its own R-7-queue docstring flagged: Done is entirely terminal and a queue excludes exactly that), plus `column_totals` — **ONE grouped aggregate**, `SUM((totals->>'grand')::numeric)`, never a Python sum over the 20-card page — and `board_card_query` with Done sorting `updated_at DESC` because a terminal state clears `holder_since`. Done is **bounded to `board.done_window_days` (90, fail-soft)**; the live columns are not. Route is **`GET /board`, not `/claims/board`** — `claims.router` is included first and `/claims/{claim_id}` would swallow the literal segment and 422 (now api-standards **§9g**). `api/queue.py`'s row-building is extracted into `_queue_rows`/`_urgency_first` so all three columns share ONE batched pass. FE: the pre-built `BoardPage` + `PipelineCard` **wired rather than rebuilt** — the layout gains `total`/`footer`/`loading`/`emptyState` and the card an optional `to` (ui-standards §3/§4 amended; spec §9.6's "clicking a card opens the tracker" vs the inventory's "no link affordance"), plus `boardMeta`/`daysPhrase`, `ClaimBoardPage`, the route and the nav entry. **No migration — head stays `0021`** | ✅ complete | pytest **890 (+30), 0 failures**, lint-imports 3/3, `alembic check` clean (no migration), seeds ×2 no-op, FE gate green (**230 vitest**, +16) + build; live smoke **47/47** whose centrepiece is a RECONCILIATION: the three columns hand-bucketed from a raw `GROUP BY` over `reimb_claims`, column for column and peso for peso (spec §14's "board totals match DB"), plus a real `/mark-paid` moving ₱6,500 from With FMS to Done with the board's grand total unchanged | 26 |
| R-8 | **Insights + the comment-learning loop — the first feature that makes the system get BETTER as it is used.** Spec §11 / Objective 3: every return has stored its reasons since R-4-screens and nothing had ever read them back. `services/insights.py`: `ranked_reasons` — **ONE grouped statement over BOTH windows** (`count(*) FILTER`, 90 days vs the 90 before), `jsonb_array_elements_text` unnested and grouped **on the text element** (a SQL `::bigint` would 500 the surface on one junk element, where `queue._GRAND`'s cast is safe only because `compute.py` is its sole writer), bucketed in Python so an unmapped id is LOGGED — `column_totals`'s shape and its reason. Built on `queue.base_query(include_terminal=True)` so the SECURITY predicate has one definition. Plus `set_promoted` (load-and-mutate, never a bulk UPDATE — the R-7-events lesson) and `may_promote` (**agency-wide** `reimb.claim.review`: the write rule is narrower than the read rule, a first for this module, because a promotion warns every claimant in the tenant). `api/insights.py` = `GET /insights/return-reasons` + `/promote` + `/demote` on the gated router, `/insights` a **sibling segment** (§9g, pinned both ways). `promoted_check` **reinterpreted** from "can be promoted" to "IS promoted" + migration **`0022`** resetting the three seeded `True`s, and **removed from the seed rows** — leaving it there would have made every `seed` run silently demote every promotion. `promoted` added to `GET /return-reasons`, which is the entire wire from the Admin Officer's click to the claimant's warning. New `insights.window_days` config (90, fail-soft). FE: **`RankedBarList`** (inventory row 23, CountdownRing doctrine — bars `aria-hidden`, every number real text, scaled to the LARGEST row never a total), `InsightsPage`, `insights-copy.ts`, and the step-5 `Callout` that is structurally incapable of gating. New standards: **api-standards §9h** (the scope IS the privacy boundary) + ui-standards §3/§8 | ✅ complete | pytest **907 (+17), 0 failures**, lint-imports 3/3, `0022` reversible (down→up, restoring exactly the three seeded codes) + `alembic check` clean, seeds ×2 no-op, FE gate green (**260 vitest**, +30) + build; live smoke **28/28** whose centrepiece is a RECONCILIATION — six reasons, both windows, against a raw `GROUP BY` over **535 real return events**, reason for reason — plus the graded line driven end to end (promote → the claimant's taxonomy carries the warning with **no deploy or restart** → demote), and a 441,731-row audit chain verified intact | 27 |
| R-9 | **Hardening + the pilot gate — CLOSES Stage C.** Not a feature increment: the deliverable is EVIDENCE that eight increments hold up. **The security suite** — `test_reimb_authz_census.py` enumerates `app.routes` and requires every one of the **32** module routes to carry a declared rule (a new route with no rule FAILS rather than being missed), reading the wiring off the app through new `oc_permission`/`oc_feature_flag` markers on `require_permission`/`require_feature`; `test_reimb_scope_security.py` drives every read path from the WRONG actor, organised by attacker rather than by endpoint. **It found a real defect on its first run:** `submit_claim`/`cancel_draft_claim` checked claim STATE before OWNERSHIP, so a stranger got `409 already_submitted` back — an enumeration oracle over every claim in the agency, from any `staff` login, with every existing test passing because they all submitted their own claim. Fixed in three places (+ `claim_action`'s no-instance branch, via the new `lifecycle.may_see_claim`); now api-standards **§9i**. **The pilot cohort** is a STATED posture, not a schema: the flag answers "is this module on", RBAC grants answer "for whom", and the new `bootstrap pilot-roster` makes the cohort enumerable (nothing auto-assigns a role, so the grant list already IS the cohort). **Perf:** both aggregates measured at ~5 ms, migration `0023` (`ix_reimb_return_events_created_at` — for year two, not today), and `verify_chain` given a MEMORY budget (501k rows → 18.7 s / 1.47 GiB RSS; threshold ≈1M rows, database-standards §7a). **Fixtures:** `modules/reimbursement/fixtures.py` + `load-pilot-fixtures` discharge spec §14's list in full. **Test hygiene made MECHANICAL** after four recurrences: a session-scoped `seed_guard` fails the run if seeded reference data was modified and not restored, and `_backdate` became a context manager that owns its own undo. Plus the §14 discharge table (§4a), the manual test guide (§4-M), and the OCR/`keyword_absent` re-deferral to Stage H | ✅ complete | pytest **1003 (+96), 0 failures**, lint-imports 3/3, `0023` reversible + `alembic check` clean, migrations replayed `0012`→head, seeds idempotent from an EMPTY database, FE gate green (**260 vitest**) + build; live smoke **42/42** as FOUR actors incl. the scoped Admin Officer #27 could not cover | 28 |

## 4-M. Manual test guide (Stage C)

Plain-language walkthrough proving the reimbursement vertical end to end — the
QA-gate requirement in `development-workflow.md` §6 step 2, and the script a
pilot demo follows. Shape borrowed from `foundation.md` §8.

**Setup.** Stack up (`docker compose up -d`; ports 8001/5432/6380, SPA on 5174):

```bash
docker compose exec app alembic upgrade head                       # head = 0023
docker compose exec app python -m office_connect.ops.bootstrap load-reference
docker compose exec app python -m office_connect.ops.bootstrap seed-rbac
docker compose exec app python -m office_connect.ops.bootstrap seed-workflows
docker compose exec app python -m office_connect.ops.bootstrap load-fixtures
docker compose exec app python -m office_connect.ops.bootstrap load-pilot-fixtures
docker compose exec app python -m office_connect.ops.bootstrap set-flag module.reimbursement --on
```

> A full `pytest` run leaves the flag OFF (`test_reimb_api_flag_gate.py` restores
> whatever it captured). Re-run the last line before demoing.

You need three logins with different scopes — a traveller, a **scoped** Admin
Officer, and an approver. Grant them with the RBAC admin API or `grant_role`;
confirm with `pilot-roster` (step 11).

1. **The module is switched on, and off means gone.** `GET
   /api/v1/config` → `features["module.reimbursement"] = true`. Flip it off
   (`set-flag … --off`) and load `/api/v1/reimbursement/my-work` → **404**, not
   403 — an OFF module is indistinguishable from an absent one. Flip it back on.
2. **File a claim.** As the traveller, open `/reimbursement/claims/new`. The
   claimant block is prefilled from the directory (you cannot type someone
   else's name — server-side, WCAG 2.2 §3.3.7). Walk the 5 steps. On the money
   step press *Recalculate*: for a 3-day NCR trip with two ₱500 fares the server
   returns **per diem ₱5,500, transport ₱1,000, grand ₱6,500** (spec §8). The
   browser computes nothing — every peso figure on screen came over the wire.
3. **The checklist gates the submit.** On *Documents*, leave a required item
   empty and press Submit on *Review* → **422** with the missing items named and
   a deep link to each. Upload them; a taxi fare over ₱300 raises an amber flag
   demanding an RER — note it **does not block** (flags never block alone).
   Submit → an `RB-2026-NNNN` reference and a confirmation panel.
   *Demo data:* the `[demo] … RER threshold` claim already has the >₱300 fares.
4. **The JO/COS conditional.** Repeat step 2 as the JO/COS traveller
   (`D-0006`, Dexter Pascual) — one extra checklist item appears that did not
   for a permanent employee. That is the rule grammar, not a hardcoded branch.
5. **Approve on a phone.** As the approver, open the claim on a narrow viewport.
   The decision bar is sticky at the bottom. Press *Return*, pick ≥1 reason from
   the taxonomy (it will not submit without one), add a comment → the claim goes
   back to the traveller, who sees the reasons on their tracker. Fix and
   resubmit → the chain restarts at step 1 with a new revision.
6. **The packet.** Open the claim as the approver → the combined PDF previews
   inline (cover + COA checklist + evidence manifest + IOT-45 / AR-01 / DV-32).
   Attach another file → the packet is **voided** and re-offered; regenerate and
   the cover's source fingerprint has changed. That is the "modified after
   signature" re-flag doing its job.
7. **Hand to FMS and relay.** As the Admin Officer, approve past `admin_review`
   → the claim reaches `handed_to_fms` and leaves everybody's My Work (its
   holder is `external_fms`). Record FMS statuses out of order — *With
   Accounting* before *With Budget* — both are accepted; the 422 you get for an
   unknown status says the three are legal **in any order**. Check the queue's
   *Over 10 working days* filter: it counts Manila working days off the holiday
   calendar, and no browser computes it.
8. **Pay it.** *Mark paid* demands a payout reference and a date — a blank
   reference is refused, and the refusal names the honest alternative (relay
   *Payment processing* instead). The claimant gets **one** notification, not
   two. The claim moves to Done on the board and the board's grand total is
   unchanged by the move.
9. **The liquidation clock.** Open the Accounting register → `DV-DEMO-0001`
   (₱18,000) shows an **amber** countdown ring at about D-5 with the COA
   consequence copy. Press *Liquidate* → an `LQ-2026-NNNN` claim pre-filled from
   the advance. Certify B, record certification C's paper signature as a
   mandatory comment, hand to FMS, then *Settle*: record a refund OR if the
   advance exceeded the spend, or spawn a reimbursement claim if it fell short —
   the spawn is pre-filled and links both halves.
10. **The learning loop, with no deploy.** As an Admin Officer with an
    **agency-wide** review grant, open *Insights*. Reasons are ranked over 90
    days with a trend against the 90 before. Press *Promote to pre-check* on
    one. Without restarting anything, open the wizard as a traveller → step 5
    now carries a plain warning naming that reason, and it **cannot block the
    submit**. Press *Stop warning* → it is gone. Try the same promote as a
    **scoped** Admin Officer → refused, because the effect is tenant-wide.
11. **Scope, from the wrong chair (R-9 — the part worth doing slowly).** Signed
    in as traveller B, request traveller A's claim id directly:
    `/api/v1/reimbursement/claims/<A's id>` → **403 `reimb_not_claim_owner`**.
    Same for `/timeline`, `/checklist`, `/external-events`, the cash advance,
    and `/api/v1/attachments/<id>/content` (the packet bytes). Now probe
    `POST …/submit` against **three** ids — A's submitted claim, an unsubmitted
    draft, and `999999999`: the two real claims must answer **identically**, or
    the endpoint is an oracle (api-standards §9i). Ask for `/claims`, `/board`
    and `/insights/return-reasons` as a traveller → **403 with three different
    sentences**, each naming the surface that does answer them. Finally, as a
    **scoped** Admin Officer, confirm the board's column counts and peso totals
    cover only their own office — check the **headers**, not just the cards.
12. **Who is in the pilot.** `docker compose exec app python -m
    office_connect.ops.bootstrap pilot-roster` → every holder of any `reimb.*`
    permission, their scope, and which are `AGENCY-WIDE`. On a clean pilot box
    that list should be short and every name recognisable. The flag says the
    module is on; this says who it is on **for**.
13. **Audit integrity.** `docker compose exec worker python -m office_connect.ops
    backup-and-drill` → `verify: ok`. Every promotion, waiver, settlement and
    status change above is in that chain.

## 4a. Spec §14 QA discharge table (the Stage C gate's audit trail)

Build spec §14 gives every phase an *"automated QA must prove"* column. This
table walks it **clause by clause** and names where each is discharged. It is
the artifact a reviewer actually reads at the gate: "the suite is green" is not
evidence that the *specified* things are true.

Test files are under `tests/`. Where a clause is discharged by a specific test,
the test name is given — those are the ones worth re-reading if the clause is
ever questioned.

| Phase | Clause from spec §14 | Discharged by |
|---|---|---|
| **R-1** | Migrations idempotent | `test_migrations.py` + `conftest.migrated_db` (upgrade to head runs once per session; a re-run is the idempotence check) |
| R-1 | Seeds load | `test_reimbursement_seeds.py`; `bootstrap load-reference` ×2 = no-op |
| R-1 | Config editable | `test_reimbursement_seeds.py::test_eo77_three_cluster_rates` / `test_region_maps_to_cluster` (effective-dated lookups); every cadence value reads fail-soft through `lifecycle.config_int`, exercised in `test_reimb_cash_advances.py` and `test_reimb_checklist_facts.py` |
| R-1 | Rates render with sources | `test_reimbursement_seeds.py::test_config_carries_legal_source` (asserts `COA Circular 97-002` on the liquidation config) |
| **R-2** | Worked example computes ₱5,500 | `test_per_diem_engine.py` **and independently** `test_reimb_pilot_fixtures.py::test_the_worked_example_still_computes_5500_per_diem` (two different paths to the same anchor) |
| R-2 | HUC/other switch | `test_per_diem_engine.py` (3-cluster EO 77 routing); `cluster_switch_trip` factory |
| R-2 | 50-km rule | `test_per_diem_engine.py` + the `within_50km_commuter` / `within_50km_overnight` factories |
| R-2 | Autosave survives refresh | FE: `web/src/pages/reimbursement/TripStepPage.test.tsx` (save-and-return); the server-side half — the draft PATCH the reload reads back — is pinned by `test_reimb_api_drafts.py` |
| **R-3** | JO/CO conditional appears only for JO/COS | `test_checklist_grammar.py`, `test_reimb_checklist_service.py`; demo evidence via `test_reimb_pilot_fixtures.py::test_exactly_one_traveller_is_jo_cos` |
| R-3 | Taxi >₱300 demands RER | `test_checklist_checks.py` (`amount_threshold`); fixture pinned by `test_a_taxi_fare_crosses_the_rer_threshold` |
| R-3 | Submit blocked on missing | `test_reimb_checklist_gate.py` |
| R-3 | Flag ≠ block | `test_checklist_engine.py` (flags never block alone) |
| R-3 | Waiver logged | `test_checklist_engine.py::test_a_human_waiver_outranks_every_machine_verdict` (the precedence rule) + `test_checklist_grammar.py`. **Note:** the waiver *UI/API* is not built — the catalog/taxonomy admin editor is a recorded deferral, and R-3's grammar docstring promises that when it ships, waivers ship with it and `evaluate_required_rule` flips to fail-CLOSED. The engine half is done and tested; the surface is not |
| **R-4** | No null holders (property across all transitions) | `reimb_lifecycle_helpers.assert_holder_invariant` — *a holder exists IFF the claim is non-terminal* — applied after every transition in `test_reimb_lifecycle_actions.py` and `test_reimb_liquidation_lifecycle.py` (both chains). Holder SELECTION is separately pinned by `test_reimb_holder_resolution.py` (deepest scope wins, ties by lowest user id, zero matches fail closed) |
| R-4 | Return requires reason | `test_reimb_lifecycle_actions.py::test_return_requires_reason` + `::test_return_rejects_reasons_outside_the_live_taxonomy` — enforced in `claim_action` (the service), so every caller is covered, not just the HTTP dialog |
| R-4 | Resubmit restarts chain | `test_reimb_lifecycle_actions.py::test_return_paths_never_orphan` (drives `returned → resubmit → division_approval → approve → admin_review → return`, asserting the holder invariant at every rung) |
| R-4 | SLA reminder fires to holder only, never superior | `test_reimb_sla_notifications.py::test_escalation_notifies_holder_only_and_dedups` |
| R-4 | Phone viewport passes | FE: `DetailPage.actions` sticky decision bar tests |
| **R-5** | Placeholder merge exact | `test_reimb_documents.py`, `test_document_render.py` |
| R-5 | Edit-after-sign voids + re-flags | `test_document_snapshots.py` (`stale_snapshots` reports, never voids) |
| R-5 | C-step upload path works | `test_reimb_checklist_api.py` (CRT-C evidence) |
| R-5 | Google-down degrades non-blocking | `test_storage_gdrive.py`; `PdfRenderer` injectable so a renderer outage never blocks |
| **R-6** | Deadline from `date_return` incl. holiday calendar | `test_reimb_liquidation_clock.py`, `test_calendar_workdays.py` |
| R-6 | Refund path records OR | `test_reimb_settlement.py::test_a_refund_records_the_official_receipt` (+ `::test_a_refund_without_its_receipt_is_refused` and `::test_a_receipt_where_nothing_was_refunded_is_refused` — both directions) |
| R-6 | Over-advance spawns pre-filled claim | `test_reimb_settlement.py::test_the_spawn_nets_the_advance_to_the_difference` |
| R-6 | D-notifications fire | `test_reimb_liquidation_reminders.py` (D-7/D-3/D-0/overdue ladder) |
| **R-7** | Statuses skip/reorder legally | `test_reimb_external_events.py` (membership enforced, order never) |
| R-7 | Board totals match DB | `test_reimb_api_board.py` + the #26 live smoke's hand-bucketed `GROUP BY` reconciliation |
| R-7 | >10-day external filter | `test_reimb_api_queue.py::test_the_threshold_boundary_is_exclusive` |
| **R-8** | Promotion creates a working warning with no deploy | `test_reimb_api_insights.py::test_promoting_shows_the_reason_to_the_wizard_with_no_deploy` |
| R-8 | Aggregates only | `test_reimb_api_insights.py` (no person dimension; scope-bounded; traveller refused) + api-standards §9h |
| **R-9** | **Scoped visibility enforced per §3.2 (owner cannot read others' claims via API)** | **`test_reimb_scope_security.py`** — three attackers × every read path; `test_a_traveller_cannot_read_another_travellers_claim` is §3.2's literal sentence |
| R-9 | (same, as a property over future surfaces) | `test_no_list_or_aggregate_leaks_a_foreign_claim_to_a_traveller`; `test_reimb_authz_census.py` fails on any route with no declared rule |
| R-9 | **Flag ON for pilot cohort only** | `test_reimb_authz_census.py::test_an_actor_with_no_reimb_grants_is_refused_on_every_route` (all 32 routes) + `bootstrap pilot-roster` + api-standards §9i |
| R-9 | Resilience / perf budgets | `EXPLAIN ANALYZE` recorded in §4b below; migration `0023`; `verify_chain` budget in database-standards §7a |
| R-9 | Fixtures polish | `office_connect/modules/reimbursement/fixtures.py` + `test_reimb_pilot_fixtures.py` (spec §14's full list) |

**Three clauses NOT fully discharged, and why** — recorded rather than quietly
counted as done, because a discharge table that only lists successes is a
marketing document.

1. **R-3 "waiver logged" — engine yes, surface no.** The precedence rule (a human
   waiver outranks every machine verdict) is implemented and tested, but there is
   no UI or API to *record* one: waivers ship with the catalog/taxonomy admin
   editor, which is a recorded deferral, and R-3's grammar docstring commits that
   `evaluate_required_rule` flips to **fail-CLOSED** when it lands.
2. **Spec §14's fixture list mentions "the real blank templates from Drive."**
   The generated forms are authored Jinja templates matching the GAM appendices;
   no blank originals were ever supplied. The demo fixture ships trips, receipts
   and an advance, not those files.
3. **`keyword_absent` / OCR** — see delta row 70. Re-deferred to Stage H at R-9,
   with the reason stated: build spec §14's R-9 row never asked for it, the check
   returns a named `skipped` rather than a silent pass, and no seeded rule uses
   it.

## 4b. Perf budgets, measured at the Stage C gate (2026-08-05)

Numbers, not adjectives. Measured against the dev database (501,423 audit rows;
4,173 claims; 567 return events).

| Surface | Plan shape | Time |
|---|---|---|
| `queue.column_totals` (board headers) | Merge join `reimb_claims` × `core_workflow_instances`, one `GROUP BY status` with `SUM((totals->>'grand')::numeric)` | **5.1 ms** |
| `insights.ranked_reasons` (both windows) | Same join + hash join to `reimb_return_events`, lateral `jsonb_array_elements_text` **Memoized** (601 hits / 10 misses) | **5.2 ms** |

**One index added** (`0023`): `ix_reimb_return_events_created_at`. The plan
showed a seq scan on that filter, which is currently *correct* — 615 rows. It
was added anyway because the table is append-only and grows forever while its
read window stays fixed at 90 days, so selectivity falls monotonically and the
plan must flip eventually. Cost is one B-tree on a monotonic key. Reasoning in
full in the migration's docstring.

**Not added:** a GIN index on `reason_ids`. It would serve a "which events cite
reason X" query that nothing asks and §9h says nothing should — the aggregate
has no drill-down by design.

**`verify_chain` has a size budget and it is MEMORY** — 501k rows → 18.7 s and
**1.47 GiB peak RSS**. Full analysis, the ~1M-row threshold and what replaces it:
`docs/standards/database-standards.md` §7a.

## 5. Decisions log

- **2026-08-05 (session 28 — Stage C R-9: hardening + the pilot gate. R-9 and
  STAGE C CLOSED)** — a gate session, not a feature session. Spec §14's R-9 row
  grades two sentences, and most of the work went into making them *provable*
  rather than *asserted*.
  - **Four kickoff decisions, all user-confirmed.** (1) **Grants ARE the pilot
    cohort** — the flag stays a tenant-wide boolean. Verified first: there is no
    default-role assignment path anywhere in the codebase, so a user reaches the
    module only because an administrator granted them a role, and the grant list
    already *is* the cohort. What it lacked was a way to READ it, which is the
    new `pilot-roster` command. (2) **OCR / `keyword_absent` re-deferred to
    Stage H** — two docs said "R-9" while build spec §14's R-9 row never asked
    for it. (3) **A dev-only demo seeder** discharges R-1's fixture debt.
    (4) **`stage-c-complete` + v0.3.0**, pushed at the gate.
  - **The security suite found a real defect on its first run, and the shape of
    it is the lesson.** `submit_claim` and `cancel_draft_claim` checked the
    claim's STATE before its OWNERSHIP, so a stranger POSTing `/submit` against
    an id they did not own got back *"This claim is already in the approval
    workflow"* — a correct, well-worded sentence about somebody else's claim.
    Paired with `claim_not_in_workflow` for drafts and `reimb_claim_not_found`
    for unissued ids, that is a three-way **enumeration oracle** over every
    claim in the agency, available from any ordinary `staff` login. Every test
    passed, because every test submitted its own claim. And the rule was already
    written down — one file over, in `services/drafts.py::owned_editable_claim`,
    with a comment naming the exact hazard. A doctrine living in one module's
    comment is not a standard, so it became **api-standards §9i**:
    *authorization precedes state; a caller must be proven entitled to a record
    before any message describing that record's condition is composed.*
    Fixed in three places, including `claim_action`'s no-instance branch — the
    one branch the workflow engine can never authorize, because authorizing
    needs an instance and that branch is the one that says there isn't one.
  - **The census is the durable artifact.** §9f's rule (*a list may not borrow a
    row's read rule*) had been applied four times, each time because a person
    remembered. `test_reimb_authz_census.py` enumerates `app.routes` and
    requires all **32** module routes to carry a declared gate class, route
    permission and exact service rule — a new route with no row **fails** rather
    than being missed. It reads the wiring off the running app rather than out
    of the source, via two new introspection markers (`oc_permission`,
    `oc_feature_flag`) on core's dependency factories; a closure is otherwise
    opaque, and grepping the source would have re-created the hand-list problem
    the file exists to remove. It also replaced the hand-maintained probe tuple
    in `test_reimb_api_flag_gate.py`, which kept only its ordering contracts.
  - **Test hygiene stopped being a matter of memory.** Four recurrences across
    #24–#27, in three costumes (a holiday row, aged `holder_since`, a promoted
    reason), each fixed with a `finally` and a docstring asking the next person
    to remember. R-9 added a session-scoped **`seed_guard`** that snapshots every
    seeded row's mutable columns and **fails the run** if the suite changed one
    without putting it back — proven non-vacuous against a deliberate leaked
    promotion — and turned `_backdate` into a context manager that owns its own
    undo. Live rows only: a properly retired test row (rule 6) is not drift.
  - **Perf budgets are numbers, not adjectives.** Both aggregates ~5 ms
    (§4b). Migration `0023` adds the `created_at` index the Insights window
    filters on — knowingly **unused today**, because the table is append-only
    and grows forever while its window stays fixed at 90 days, so the plan must
    flip eventually and this is the cheapest possible insurance. And
    `verify_chain` got the finding that matters: at 501k rows it is **18.7 s but
    1.47 GiB peak RSS**, so its ceiling is **memory**, not time, at roughly 1M rows
    (database-standards §7a).
  - **The demo fixtures stop at the workflow, deliberately.** `fixtures.py`
    builds spec §14's cast with server-computed money (the worked example
    returns ₱6,500 from the engine, written nowhere in the file) but submits
    nothing. Fabricating approval history would mean writing hash-chained audit
    rows asserting that people made decisions they never made, in the one
    structure whose entire value is that you can believe what it says. The
    manual test guide (§4-M) drives the chain by hand instead.

- **2026-08-06 (session 27 — Stage C R-8: insights + the return-reason learning
  loop)** — spec §11 / Objective 3, and the first feature in the module that
  makes the system get **better** as it is used rather than merely recording
  what happened. Spec §14 grades it on two clauses: *"Promotion creates a
  working warning with no deploy; aggregates only."*
  - **Four kickoff decisions, all user-confirmed.** (1) **A promotion flips
    `promoted_check`** — the column spec §5.6 already put there, reinterpreted
    from the seed's loose "could be promoted" to "IS promoted", with `0022`
    resetting the three rows that shipped `True`. (2) **Insights reads under
    oversight scope**, the queue's and the board's rule unchanged, no new
    permission. (3) **Promotion needs an AGENCY-WIDE review grant.** (4)
    **`RankedBarList` becomes an inventory row**, amending ui-standards §3 first.
  - **The `auto_checks` divergence is semantic, not convenient.** Spec §11 says
    a promotion "writes an `auto_checks` row", and taken literally that would
    have been wrong in a way that looks right: our checks are **item-scoped**,
    their flags set an item to `auto_flagged`, and the checklist engine counts
    `auto_flagged` as **DONE**. Promoting a reason that way would mark a
    document satisfied and put a statistic in the approver's flag list. What
    §11 is actually asking for is *"no code change"*, and that is honoured
    exactly — the promotion is one boolean and `GET /return-reasons` carries it.
  - **The seed defect that would have quietly undone the whole feature.**
    `apply_dataset` writes only the keys a row dict lists, so leaving
    `promoted_check` in the seed would make **every `seed` run demote every
    reason an Admin Officer had promoted** — on the next deployment, with no
    error and no trace but a warning that stopped appearing. The key is removed;
    the column keeps its `server_default` at insert and has one writer after
    that. `test_reimbursement_seeds.py` now asserts "nothing ships promoted",
    which doubles as the canary for a leaked test promotion.
  - **The write rule is narrower than the read rule — a first here.** Reading
    the ranking needs oversight of somebody; promoting warns *everybody*. A
    division-scoped grant reaching a tenant-wide effect is a scope escalation
    that would look exactly like the button working, so promotion requires
    `org_unit IS NULL` and `can_promote` rides the envelope.
  - **The privacy claim is structural, not editorial** (new api-standards §9h).
    The aggregate spans exactly the rows the actor could already open one at a
    time, because it is built on the queue's own `base_query` rather than a
    second predicate that agrees today. That is also why **no minimum-cell
    suppression** was added: in a small division the counts *are* about few
    people, and the actor already oversees precisely those people — suppression
    would protect nobody while making the numbers wrong. The response has no
    person dimension and nowhere to add one; the claimant's advisory carries the
    reason and never a count.
  - **Fail-safe runs backwards on an advisory.** Everywhere else in this module
    the safe answer is to block (the packet gate) or to flag (an auto-check).
    Here it is to **say nothing**: a failed taxonomy fetch renders no warning, a
    retired reason cannot be promoted, and nothing the promotion writes is read
    by the submit gate. A warning nobody authored, or one about a rule nobody
    enforces, spends the credibility of every honest warning beside it.
  - **Two numbers, both true, and the header takes the right one.** A return
    citing three reasons is one packet that came back and three ranked hits. And
    **neither is a rate** — spec §13's return rate needs a submissions
    denominator that stays in Stage H, and a plausible percentage is the number
    people quote.
  - **A reason that fell to zero keeps its row.** It is what a successful
    promotion looks like, on the one surface built to show it.
  - **Test hygiene, third shape.** Dates → counts → **shared seeded rows**: a
    promotion is tenant-wide, so a test that promotes must demote in a
    `finally`. And `reimb_return_events` REVOKEs UPDATE, so a window fixture
    **inserts** a row with an explicit `created_at` rather than backdating one.

- **2026-08-05 (session 26 — Stage C R-7-board: the pipeline board. R-7 CLOSED)**
  — spec §9.6's "module's public face", and the surface spec §14 grades on one
  sentence: *"board totals match DB"*.
  - **Four kickoff decisions, all user-confirmed.** (1) **One request with the
    cards embedded**, not headers-plus-drill-down: a column is a GROUP of
    statuses and `GET /claims` takes one, and Done is entirely terminal which
    the queue excludes — so the "less code" alternative would have had to teach
    the queue about columns *and* terminal claims anyway, at four round-trips on
    a default view. (2) **`GET /board`, not `/claims/board`** — the second is a
    real route-matching collision, not a preference. (3) **ui-standards is
    amended so a card can be clicked**, because spec §9.6 asks for it and the
    inventory forbade it, and standards outrank the reference spec — so the line
    gets rewritten rather than ignored. (4) **Done is bounded** to a config
    window; the live columns are not.
  - **The grouping is the one real design decision, and it lives on the
    `Vocabulary`.** Per kind, mandatory per state, column sets derived. The
    argument is not symmetry with `labels` but a difference in failure mode: an
    unlabelled state renders a raw code **at a user who can see it is wrong**,
    while a state with no column vanishes from a peso total with nothing on
    screen to say so. `None` is an authored declaration (`draft`, `cancelled`),
    not a gap.
  - **Pairwise disjointness is the trap nobody would find twice.** The aggregate
    groups by status across both kinds in ONE statement, so a code two
    vocabularies placed in two different columns would be counted twice and the
    board would total more than the database holds — the exact sentence §14
    grades. Asserted at import, with a test that builds a broken vocabulary to
    prove the assertion bites.
  - **A flag, not a second query builder.** `base_query` is the one definition
    of *which claims may this actor see*; a second builder is a second copy of a
    **security predicate**, and a drifted scope clause leaks where a drifted
    display mapper merely renders wrong.
  - **`GROUP BY status`, not a SQL `CASE`, so an unmapped status stays
    observable** — and therefore no pre-filter on `ALL_BOARD_STATES`, which
    would hide the very rows the warning exists to catch.
  - **The Done column needed its own everything.** Its own sort (`updated_at
    DESC` — a terminal state clears `holder_since`, so "longest waiting" there
    is undefined rather than merely wrong), its own window, and its own meta
    line: `days_in_state` is 0 on every terminal claim, so the queue's wording
    would have printed *"0 days in this step"* on a claim paid three weeks ago.
    Three separate consequences of one fact the queue never had to face, because
    a queue has no terminal rows.
  - **A third instance of the session-#24 test-hygiene disease, and the first
    one that actually failed a run** — in the file that documents the rule. Two
    queue tests aged claims and never undid it; 54 permanently-aged rows
    accumulated over three sessions until a freshly-aged fixture fell off page 1
    and the assertion compared a one-element list. **The rule now generalizes
    from dates to counts:** on an aggregated surface, assert through a scoped
    actor whose org unit the fixture created fresh.

- **2026-08-05 (session 25 — Stage C R-7-events: the FMS journey record)** —
  R-7-queue made FMS-held claims findable; this session made them actionable.
  Three things were true of the codebase at kickoff and all three are now false:
  `reimb_external_events` had never been written to, `paid_closed` recorded
  nothing, and every claim attachment in the system was permanently
  non-disposable.
  - **The arrow in spec §6.1 row 6 is not a sequence, and that is the whole
    design.** The row reads *With Budget → With Accounting → Payment Processing
    (admin, **any order/skips allowed**)*, and the parenthetical is the
    operative half. FMS pays straight out of Budget, sends packets back to desks
    they already left, and answers "still with Accounting" twice in a week —
    every one of those is a legal relay. So `record_external_event` enforces
    MEMBERSHIP of the closed set and never order; repeats are legal; and the 422
    says *"in any order, and skipping any of them is fine"* out loud, because an
    operator who infers a sequence from a three-item list will not relay
    Accounting on a packet that skipped Budget. The FE mirrors it — no option is
    ever disabled by what came before. This is delta row 38 finally built: the
    sub-statuses are **not states**, they ride an append-only table over the
    single `handed_to_fms` state, and a relay moves nothing (asserted, because a
    relay that moved the claim would also reset `holder_since` and silently
    restart R-7-queue's ">10 working days with FMS" clock every time somebody
    phoned FMS — a bug that would have looked like diligence).
  - **`mark_paid` is workflow-standards §12's second instance, and the standard
    held without amendment.** Spec §6.1 row 8 says `paid_closed` is "terminal
    (admin records payout ref)"; it was a bare `approve` that recorded nothing.
    `record_payout` writes the reference and the `paid` event, then drives the
    unchanged verb, all in one transaction; `_assert_payout_recorded` refuses
    the bare verb and names `/mark-paid`; `claim_actions` rewrites the client
    verb rather than dropping it. Both chains now end in a rewritten verb, and
    the rewrite is ONE kind-keyed table rather than two copies — two chains
    answering the same question differently is how they drift.
  - **What FMS hands back was an open question, and the answer is deliberately
    small** (user-confirmed): one reference plus a date. `payout_ref` /
    `paid_on` / `paid_by`, no unique index (one LDDAP-ADA pays many vouchers),
    and the reference REQUIRED — `paid_closed` is read-only with no amendment
    route, so a blank one would recreate the very hole this closed. The refusal
    names the honest alternative: relay *Payment processing* until the reference
    exists.
  - **The retention bug nobody could see.** `services/attachments.py` has parked
    `retention_starts_at=None` since R-2 with a comment promising "final
    settlement, which is `paid_closed` (R-7)". Nothing ever set it, so
    `retain_until()` returned None for every claim attachment in the system and
    the disposal report said "retention clock not started" — forever, and
    correctly, because the clock genuinely had not started. `start_retention`
    went in CORE beside `retain_until` (rule 10): the module names the moment,
    core does the stamping. **Rule 5 caught the first attempt at test time** —
    the bulk UPDATE was refused by `core/audit.py`, and rightly: starting a legal
    retention period is exactly the kind of change that must appear in the
    hash-chained log. `cancelled` deliberately does not stamp, as a recorded
    deferral with a test pinning it.
  - **The live smoke earned its place again.** Every unit test passed and the
    28-check smoke still found a defect: the `paid` external event and
    `notify_paid` were both firing, so a traveller got two notifications about
    one payment — the less informative one ("your claim is now Paid", no
    reference, no amount) arriving first. Both messages were individually
    correct, which is why no assertion caught it. Now suppressed, and pinned.
  - **A test-hygiene defect of exactly the session-#24 kind, one table over.**
    `test_reimb_api_queue.py::_backdate` aged committed claims to 21 days with
    FMS and never undid it — and the suite shares one database, so every run
    left another permanently-over-threshold row until the `external_over` page
    was nothing but old fixtures. Fixed with an `_undo_backdating` in a
    `finally` plus per-claimant scoping. **The rule generalizes past holidays:
    any fixture writing dates relative to TODAY must undo itself.**

- **2026-08-04 (session 24 — Stage C R-7-queue: the oversight queue)** — R-7 is
  about the part of the journey that **isn't ours**. Everything up to
  `handed_to_fms` is the platform's; after that the packet is with FMS, and the
  platform's job is to keep the claim findable, relay what FMS says, and record
  what FMS finally did. Split three ways at kickoff (user-confirmed):
  **R-7-queue → R-7-events → R-7-board**.
  - **The queue goes first because it is a prerequisite, not an afterthought.**
    Spec §14 lists the admin queue last of R-7's four deliverables, but
    `resolve_holder` sets `holder_kind='external_fms'`/`holder_id=NULL` at
    `handed_to_fms` and `/my-work` filters `holder_kind='user'` — so a claim with
    FMS is in **nobody's** inbox and the Admin Officer who handed it over could
    never see it again. Every other R-7 button (the status relay, the
    `fms_returned` hand-back, `mark_paid`) hangs off a claim that was
    unreachable. The holder modelling is right; the product was unusable.
  - **A list may not borrow a row's read rule — the session's one security
    decision.** `reimb.claim.read` is granted GLOBALLY to `staff`, because a
    traveller must read their own claim from anywhere in the tree. Key a list on
    it and every employee gets every colleague's destinations and peso totals.
    The queue is scoped on the OVERSIGHT permissions and the subtree they cover;
    holding none is a 403, not an empty list, because "there is no work" is a
    claim about the world and it would be false. Written up as
    **api-standards §9f** so the next module's first list starts from it.
  - **No column, no migration — the substrate was already right.** The >10-WD
    clock counts Manila working days since `holder_since`, which for a claim
    sitting at `handed_to_fms` IS the hand-off instant and which correctly
    restarts if a bounced claim is re-handed. Deliberately not "days since the
    last external event": §7 rule 5 asks how long FMS has HAD it, and a relay
    saying "still with Budget" is news, not progress.
  - **Core gained the half of its own scope primitive it was missing.**
    `ancestors_or_self` (walk up from a record) had no inverse, so
    `descendants_or_self` was built beside it: per-row filtering with the
    upward walk is a query per row, unbounded by page size. Rule 10 — the module
    does not grow its own org-tree SQL.
  - **A test-hygiene defect found by its own flakiness.** The holiday test seeds
    non-working days in the RECENT PAST, and the suite shares one database, so
    the rows silently shortened every later "working days since…" count in the
    codebase — including this file's own threshold tests, which is how it was
    caught. Eight leftover rows (a whole poisoned week) were retired, and the
    test now cleans up in a `finally`, retiring rather than deleting (rule 6).
    A fixture that writes dates relative to *today* has to undo itself.

- **2026-08-04 (session 23 — Stage C R-6-liq-settle: settlement)** — R-6-liq-chain
  built the liquidation's *chain*; this is its *content*. Before today no advance
  in this system had ever been settled: `reimb_cash_advances.settled_at` had
  existed since migration `0013` and had never once been written, and `settled`
  was reached by a bare `approve` that recorded no money at all.
  - **The money and the terminal state are ONE act, and the reason is a concrete
    failure, not symmetry.** The engine's `approve` carries no payload, so the
    obvious design was "record the settlement, then approve" — two calls. But
    `mark_settled` releases the PD 1445 §89 slot the instant it commits, so a
    settlement whose approve never followed would let the traveller take a NEW
    advance while a live liquidation still stood against the old one — and
    `0020`'s belt index then forbids repairing it. There is no compensating
    transaction anywhere in this codebase. Folded into one service call inside
    one transaction, every failure rolls back together. That generalized into
    workflow-standards §12, because every future module with a money-carrying
    terminal step faces the same fork.
  - **The brief was wrong about `mark_settled`, and finding that out was cheap.**
    `PROGRESS.md` said it existed and had no caller; a repo-wide grep said
    otherwise. Written from scratch — and the one guard that mattered was NOT
    copying `mark_overdue`'s allow-list, which would have made an `overdue`
    advance unsettleable. Overdue advances are precisely the ones Accounting
    needs to close.
  - **The spawn links the same advance, and that overloads a column.** Copying
    the trip, the itinerary AND the `cash_advance_id` is what makes DV-32 print
    the standard GAM shape with the difference on the payee line. The price is
    that `cash_advance_id` now means two things, so three readers had to be
    kind-guarded — and one of them was a defect this increment CREATED: without
    it a settled-but-late advance renders a red Overdue ring and the COA
    interest/salary-deduction copy forever, threatening a traveller who already
    answered.
  - **What GAM App 44 may say about a certification.** `_dv32_body`'s rule
    survives intact but arrives somewhere new: B's clearer is a fact the platform
    genuinely holds, so it is REPORTED beneath a blank rule; C's is not, because
    the platform holds the Admin Officer who recorded the signature rather than
    the accountant who gave it. Box C stays blank forever, and there is now a
    test whose whole job is to stop a future session helpfully filling it in.
  - **Three defects the increment found in code it did not write.**
    `documents/service.py::_bindings` used `.in_([kind, None])`, so the "NULL =
    both kinds" semantic its own model documents was unreachable — silently, with
    a missing government form as the failure mode. `_dv32_body.html.j2` tested
    `{% if totals.advance %}` where `money_str(0)` is the truthy string `"0.00"`,
    so every reimbursement DV printed `Less: cash advance (₱0.00)`. Both fixed
    while the blast radius was still zero.
  - **The live smoke earned its keep, twice.** The suite was green and the smoke
    still failed: the Celery worker held STALE Python while reading templates
    fresh from the bind-mount, so it rendered a new `packet.html.j2` against an
    old context (`'money_labels' is undefined`) and could not resolve
    `reimb.lr44` at all. Not a code defect — but a real deployment invariant, and
    one no test can catch by construction: **restart the worker, not just the
    app.** Recorded in the tech-stack notes.

- **2026-08-04 (session 22 — Stage C R-6-liq-chain: the liquidation workflow)** —
  R-6-clock built the *question* (a pinned COA 30-day deadline with a countdown
  and a reminder ladder); this increment builds the *answer's chain*. Kickoff
  decisions, all four user-confirmed: **split R-6-liq into chain / settle** (the
  fifth such split, after R-2, R-4, R-5 and R-6 — the seam is chain-vs-money, and
  GAM App 44's entire content *is* the settlement figures); **certification A is
  folded into submit**; **CTC-47 belongs to BOTH kinds**; and **liquidations
  reuse the 5-step wizard**, pre-filled from the advance.
  - **Generalized, not forked.** The obvious move was a second
    `liquidation_status.py` and a second lifecycle path. Four state codes are
    genuinely SHARED between the chains, so a fork would have duplicated them and
    drifted the first time one chain gained a state. Instead there is one
    `Vocabulary` per kind, and `_assert_graph_invariants` takes the vocabulary as
    a parameter — checking both graphs against one merged set would have accepted
    a liquidation state authored into the claim graph, which is the exact drift
    the check exists to catch.
  - **The union-terminal trap, and why it is derived.** My-Work's two queries
    span both kinds in ONE statement, so they cannot resolve a per-row
    vocabulary — they filter on `ALL_TERMINAL_STATES`. Had that been a
    hand-written list, `settled` would have been forgotten and every finished
    liquidation would have sat in its claimant's inbox forever. It is derived
    from the vocabularies and asserted as a derivation, so the next kind cannot
    reintroduce the bug.
  - **Certification A has no state, and that absence is the decision.** A
    certifies that the claimant incurred the expenses; the claimant is the MAKER,
    and `enforce_segregation` guards `instance.originator_user_id`. Authoring A
    as a gate would have asked the maker to check themselves. Submitting IS
    certification A — the R-4-app maker/checker decision applied verbatim.
  - **The liquidation chain adds NO engine verb.** Its certifications are
    `approve` at gate states, exactly like the claim chain's approvals — which is
    why the un-gated `api/actions.py` drives it with zero new routes, zero new
    schemas and zero new client code beyond the labels. Rule 10 paying off: the
    second consumer of a shared engine should cost less than the first, and it
    did.
  - **"Director IV" is a SCOPE, not a role.** `reimb.liquidation.certify` is a
    permission granted to `approver`; which person holds it at which org unit is
    grant data, and `resolve_holder` ranks nearest-first from there. Inventing a
    `director` role would have encoded a chain DOH DO 2019-0225 has not
    confirmed — the same reason the amount tiers are still unauthored.
  - **Certification C is a sentence, because that is all we honestly have.** The
    Head of the Accounting Unit is FMS and signs on paper. Its `approve` is the
    only transition in either chain carrying `requires_comment`: the note naming
    whose signature and when is the entire record Office-Connect holds. Binding a
    frozen snapshot to the step is core-service #3's signature half, still
    deferred — but now deferred with a written reason.
  - **`CRT-C` is `{"always": false}` for a structural reason, not a lenient
    one.** A required wet-sign row would block SUBMIT and certification B too,
    because the checklist gate is a PRE-workflow gate: it would demand the
    accountant's signature before the chain that obtains it had started. Delta
    row 67's argument, one level out.
  - **The first seeded `deadline_check`** lands on `LIQ-30` as `data_only`, so it
    flags a late filing without ever blocking it — a late traveller must not be
    trapped unable to file the very liquidation that ends the lateness. Three
    sessions after the check was registered inert, it now has substrate *and* a
    rule.
  - **A real defect found by the gate, not by a test:** `CashAdvancesPage` passed
    `<ErrorSummary items={…}>` where the prop is `errors`, so the record dialog
    would have white-screened on any server error — including the PD 1445 §89 409
    R-6-clock built its named message for. It survived R-6-clock because `tsc -b`
    is incremental and the stale build info never re-checked that file.
  - Verified: pytest **771 passed, 0 failures** (+34), lint-imports 3/3,
    `alembic check` clean with head still `0019` (**no migration** — the kind
    enum, the varchar status column and the on-demand reference-number counter
    all already allowed it), seeds ×2 no-op, FE gate green (tsc + eslint +
    **177 vitest**, +9, + build), and a **23/23 live smoke** through the real
    stack: an authenticated HTTP round-trip (record → refuse Accounting → file →
    409 the second → read back), the liquidation catalog served instead of the
    claim one, and the whole chain walked to `settled`.

- **2026-08-04 (session 21 — Stage C R-6-clock: cash advances + the 30-day
  liquidation clock)** — kickoff decisions (user-confirmed): **R-0 item 1 closed
  as CALENDAR days with `basis` as a live config switch** (COA 97-002's text,
  with DOH working-day practice reachable without a deployment); **R-6 SPLIT
  into R-6-clock / R-6-liq**, the fourth such split after R-2, R-4 and R-5;
  **Accounting records a cash advance**, not the traveller; and **both SLA-ladder
  problems fixed here**, because R-6 owns the clocks and going green before
  adding a second ladder on the same machinery was the cheapest it would ever be.
  - **The 3-session-old test failure was the session-17 production defect all
    along.** `sweep_sla_reminders` took `ORDER BY WorkflowStep.id ASC LIMIT 200`,
    which is a budget that always starts at the same end of the queue: once ~200
    steps are permanently stuck, every newly-overdue item sits behind them
    forever — spec §7.5 inverted. It surfaced as a test failure at session 18
    (the session that added 146 tests) purely because that is when the suite's
    accumulated backlog crossed 200; the dev DB held **450** such steps when
    measured. Fixed by ordering most-overdue-first AND **draining in keyset
    pages**: ordering fixes the priority, but only draining fixes the
    starvation, because the newest overdue item is by definition the *least*
    overdue and would be last in line under either ordering. Exhausting the page
    budget is now logged, never silent. Two regression tests pin it, and the new
    liquidation ladder was written drained from the start rather than inheriting
    the shape.
  - **The deadline is PINNED, not derived** — the practical reasons are the
    sweep's range query and the existing `liquidation_deadline` precedent, but
    the decisive one is that the date a traveller was *told* must not silently
    move when an admin edits a config row. Recomputed on exactly one trigger,
    which is the R-5-gen `purpose` lesson (track which question an edit answers)
    applied to a clock.
  - **Compliance clocks fail SHORT**, the opposite direction to the checklist
    grammar's fail-open for an unparseable rule. A rule failing open produces a
    visible flag someone can action; a deadline failing open quietly grants time
    that does not exist. Same asymmetry, opposite directions, both deliberate.
  - **PD 1445 §89 became a sentence.** The hard-block has been a DB index since
    R-1, which meant an Admin Officer hitting it got a 500. It now names the
    blocking DV and its deadline — §9.1 principle 4 applies to constraints too.
  - **`deadline_check` is live**, three sessions after it was registered inert.
    The seeded RULE waits for R-6-liq's catalog; the substrate and the
    `skipped → passed → flagged` proof ship now.
  - Engineering findings, both real and neither ours: **`created_by`/
    `updated_by` are NULL platform-wide** (0 of ~1,450 live `reimb_claims`) —
    the ownership columns exist on every business table and nothing populates
    them, so standing rule 5 currently rests entirely on the hash-chained
    `core_audit_logs` trail. Recorded, not widened into here: it is a foundation
    change touching every table. And **`FormDialog` now sets `noValidate`** —
    native constraint validation was BLOCKING the submit event on an empty
    required field, so react-hook-form never ran and the user got a browser
    bubble instead of the GOV.UK error ui-standards §3.14 requires to match the
    server's wording.
  - Verified: pytest **737 passed, 0 failures** (+79; the pre-existing failure is
    fixed), lint-imports 3/3, `0019` reversible + `alembic check` clean, seeds ×2
    no-op, FE gate green (tsc + eslint + **168 vitest**, +18, + build), and a
    live smoke through the **real Celery worker**: pinned clock, §89 409,
    D-7 → D-3 → D-0 → overdue → repeat, idempotent re-beats, and an
    authenticated HTTP round-trip returning the server-derived countdown.

- **2026-08-04 (session 20 — Stage C R-5-packet: the printable packet + the §9.2
  preview)** — kickoff decisions (user-confirmed): the manifest **indexes** the
  claimant's uploads rather than embedding them (COA takes the originals, and
  embedding would break the `origin='generated'` born-clean chain that makes the
  preview servable at all); the packet is produced in the **same pass** as the
  three forms (a fourth document, idempotent by fingerprint) rather than on
  demand at `admin_review`; the preview **embeds from `lg` up** with a new-tab
  link at every width. Decided and recorded here rather than asked: the packet is
  a **claim-level artifact**, not a checklist document. Two consequences worth
  remembering — attaching evidence now voids the packet (the manifest is part of
  what the packet asserts), and the generate endpoint grew a second door so an
  approver told to "print packet" is never stranded without one.

- **2026-08-04 (session 19 — Stage C R-5-gen: template auto-assembly)** — kickoff
  decisions (user-confirmed): **WeasyPrint + Jinja2, Drive dropped from the generation
  path entirely** (master-plan §1.1 #8 outranks the reference spec on precedence);
  **draft pre-submit + authoritative regeneration at submit** (the only way to honour
  §9.3 step 4's in-wizard `Generated ✓` cards when `ref_no` is not allocated until
  submit); **snapshot half of core-service #3 now, signature capture at R-6**; and
  **R-5 split into R-5-gen / R-5-packet**, mirroring the R-2 and R-4 splits.
  - **The structural decision:** `core/documents/` is an ENGINE, not a form library.
    Consumers register their own template directory and `DocumentSpec`s, so core
    renders a GAM form without ever learning what a claim is — the same inversion
    `core/attachments/authz.py` and `core/checklist/` already use, and `lint-imports`
    (3/3) is the proof. The renderer is an injected keyword argument with WeasyPrint
    lazy-imported inside it, which is what lets the whole suite run on a Windows host
    with no Pango.
  - **Two hashes, because they answer different questions.** `content_sha256` over the
    PDF bytes is tamper evidence; `source_fingerprint` over the canonical render
    context is change detection. PDF bytes embed a creation timestamp, so identical
    data renders to different bytes — hashing output could never answer "did the data
    move?". The fingerprint is also what makes generation idempotent, so a retry, a
    double-click and a beat sweep all cost nothing.
  - **One new core column doing three jobs:** `core_attachments.origin`. Generated
    bytes are born `clean` (we rendered them in-process from autoescaped templates);
    only generated PDFs are served `Content-Disposition: inline`, which is the only
    reason preview works at all; and `evidence_counts` filters them out so a
    system-produced artifact never counts as evidence a human supplied. Recorded as
    **api-standards §9c**, which knowingly amends §9b's "zero core router change" —
    how a blob is served is a property of the blob, and that is core's to know.
  - **`generated` had no writer.** R-3 shipped the status, but `_states` derives it
    from the column `refresh_checklist` writes, so nothing could ever set it — which
    is exactly why the three items sat inert. `mark_generated` is the entry point;
    `materialize_generated_item` is a deliberately SEPARATE door from
    `_item_for_catalog`, so a claimant still cannot upload an IOT-45 and the generator
    still cannot manufacture a TO-01.
  - **Bug found by the live smoke, not by the unit tests:** invalidation was keyed on
    `_COMPUTE_INPUTS`, but `purpose` is printed on all three documents and moves no
    money — so editing it left an ACTIVE snapshot asserting a purpose the claim no
    longer had. `update_draft_fields` now tracks money-staleness and packet-staleness
    as two separate questions. Regression test added.
  - Verified: **pytest 649 passed / 1 pre-existing failure on a freshly migrated
    scratch database** (+34 tests), lint-imports 3/3, `0018` reversible + `alembic
    check` clean, FE gate green (tsc + eslint + **140 vitest**, +3), and a **23/23
    live smoke** through the real Celery worker and real WeasyPrint.

- **2026-08-03 (session 17 — Stage C R-4-screens: the approver surface)** — kickoff
  choices (user-confirmed): **per-action routes** over a `{action}` envelope;
  **the approval screen folds into `/claims/:id`** rather than a separate
  `/approve` URL; **the whole chain ships** with contextual labels (the graph
  makes `admin_review→handed_to_fms` and `handed_to_fms→paid_closed` the same
  `approve` action, so the endpoints came free); **new `FormDialog` + `ChipGroup`
  inventory rows** rather than stretching `ConfirmDialog`.
  Design: **the flag gates the surface, never a decision on an in-flight
  instance** — one un-gated router carrying exactly the two action POSTs
  (api-standards §9a); the action set + CAS token ride **inside `ClaimDetail`**
  so buttons and record can never disagree; **≥1 reason enforced in the service**,
  not only the wire schema (`reason_ids` is FK-less JSONB and non-HTTP callers
  exist); **due-soon = 1 day**, because §6.3's 7-day window belongs to the R-6
  liquidation clock, not a 3-working-day approval SLA; the wizard resume redirect
  now keys on `available_actions` rather than status, so a reviewer opening a
  returned claim is no longer dragged into a stranger's wizard.
  Engineering: two defects found and fixed en route — (1) core `available_actions`
  offered `approve` to an originator under segregation and to an actor who had
  already filled a slot, i.e. a button certain to 409; fixed in **core** (Rule 10 —
  every module benefits) and recorded as workflow-standards §3 doctrine; (2) an
  idempotent replay of a return appended a phantom second `reimb_return_event` to
  an APPEND-ONLY hash-chained table, because the module's insert sat after
  `execute_action` (which returns the original event verbatim on a key hit).
  `DetailPage.actions` renders **one** node repositioned by breakpoint — the
  first draft rendered two copies behind `lg:hidden`/`hidden lg:block`, which
  duplicated every id and announced every button twice (ui-standards §4).
  **Verified:** pytest 470 (+28), lint-imports 3/3, `alembic check` clean (no
  schema change — head stays `0016`), FE gate green (96 tests, +21), live smoke
  14/14 through `paid_closed`.

- **2026-07-30 (session 16 — Stage C R-2-wizard: the claim wizard + My-Work inbox — the
  module's FIRST HTTP surface)** — kickoff choices (user-confirmed): **dev flag ON**
  (new audited `bootstrap set-flag` subcommand; fail-safe OFF untouched in
  migrations/seeds), **`other_total` as a claim column** (migration `0016` — fixes the
  latent resubmit-resets-other bug; itemized lines are R-3), **4-step wizard** (Documents
  → R-3, delta row). Backend: first module router (`modules/reimbursement/api/`,
  mounted from `main.py`; conventions recorded in **api-standards §9**) behind the new
  core `require_feature` → 404 gate (whole router; revisit at action endpoints);
  `create_draft_claim` stamps status/holder/next-action at birth (§7 rule 1 from the
  first row); `services/drafts.py` owns claimant business-field writes (owner +
  draft/returned guards, legs bulk-replace with soft-deletes + server-assigned seq,
  compute-input edits clear `totals`); read authz = owner-or-scoped
  {approve,review,fms_update} (§3.2 — the staff role's global read grant cannot scope);
  `/submit` routes `returned` → resubmit (one FE flow covers fix-and-resubmit);
  idempotency-key header + pagination envelope stay recorded deferrals. FE:
  react-hook-form 7.83.0 + zod 4.4.3 + resolvers 5.5.7 installed (tech-stack §4;
  zod pinned to dedupe the eslint-chain transitive); FormField widened to
  `ComponentPropsWithRef` + internal FieldChrome; inventory grew to 17 (Select/Textarea/
  Checkbox/RadioGroup family, SummaryList, ConfirmationPanel, WorkItemRow — ui-standards
  §3/§8 amended first); WizardPage gained `asideExtra` (running-totals rail);
  submit-per-step save-and-return + unsaved-changes blocker; task-list state derives
  from field presence (`totals` presence = the Money gate); 422 `loc`→RHF mapper with
  the dots→dashes DOM-id convention; MutationCache 401 handler (me-exists guard);
  step routes render the read-only detail in place for non-editable claims (a
  post-submit redirect would race the confirmation navigation — found by the first
  page-level FE tests). `tests/conftest.py` now exports `CSRF` + `login` (six per-file
  duplicates left untouched). Verified: pytest **442** (+29; a 45-agent adversarial review pass confirmed 13 findings — all fixed pre-commit, incl. a cancelled-claim-resurrection hole in submit_claim, a claim-status oracle in the draft guards, dead ErrorSummary anchors on radio groups), lint-imports 3/3, `0016`
  reversible + `alembic check` clean, seeds ×2 no-op, FE gate green (**75** tests incl.
  the first page-level tests + axe on every new component), live smoke via :5174
  (flag → config, anonymous 401 on the gated API, SPA serves the module routes).
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
