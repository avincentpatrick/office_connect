# Office-Connect — Reimbursement Module Build Specification v1.0

**Companion to:** `OfficeConnect_Build_Execution_Plan_v1_0.docx` (single source of truth for the platform) and `Reimbursement_First_Dependency_Analysis.md` (the locked handoff this spec deepens)
**Status:** BUILD-READY pending the short R-0 confirmations listed in §15
**Build target:** A Sonnet-class build agent. This document is written so the builder **never has to guess** — every screen, table, rule, status, and check is specified. Where a value could vary, it is a **config default**, not a hardcode.
**Scope:** Local travel only — Local Reimbursement + Local Cash-Advance Liquidation. Foreign travel is parked.

Two priorities are binding throughout: **ease of use** (a first-time traveller completes a claim without training) and **design/layout quality** (calm, consistent, token-driven). One rule is **non-negotiable: the work-management flow** — at every moment, every claim has exactly one holder and one next action, and nothing stalls silently (§7).

---

## 1. How to Build From This Document

Follow the platform's per-phase execution loop (Execution Plan §1): build a phase → run its automated QA until green → deliver a plain-language manual test guide → author tests → phase closes. Phases for this module are §14. The platform foundation floor (Phases 0–2 + governance gate) precedes everything here; this spec assumes core auth, RBAC registry, staff directory, theming tokens, feature flags, audit, notifications, Drive storage, and the reference-number strategy exist as specified in the Execution Plan (§14 there).

Namespace: all module tables are `reimb_*`. Feature flag: `module.reimbursement` (fail-safe OFF). Reference numbers: `RB-YYYY-NNNN` (claims) and `LQ-YYYY-NNNN` (liquidations) via the pluggable per-module strategy (S-4), yearly reset.

---

## 2. The Four Objectives → Acceptance Criteria

| # | Objective | The module passes when… |
|---|---|---|
| 1 | **Automate the documentary requirements** | A traveller enters trip facts once; the system generates Appendix A (Itinerary), Appendix B (Certificate of Travel Completed), Liquidation Report, and the JO/COS Certification as filled Google Docs → frozen PDFs. No re-typing between forms. |
| 2 | **Check documents against the standard** | A claim physically cannot be submitted with a missing required item; every auto-checkable rule (economy fare, CENRR/RER thresholds, date coherence, receipt totals) runs before a human sees the claim; reviewers see a pre-checked packet. |
| 3 | **Learn from the usual comments** | Every return carries a structured reason from the taxonomy; an admin dashboard ranks recurring reasons; a top reason can be promoted to a pre-submission warning without a code change. |
| 4 | **Monitor progress** | Any traveller answers "where is my money?" in one glance; any approver sees their queue ordered by urgency; the Director sees pipeline totals; liquidation deadlines count down visibly from day one. |

---

## 3. People, Roles & Permissions

### 3.1 Personas
- **Traveller (Staff)** — files their own claims via the wizard. Desktop-first, must work on phone.
- **Division Chief / Section Chief** — approves itineraries and claims for their division/section. Phone-first approval.
- **Director** — final in-bureau approver where the type's signatory config requires; sees office-wide pipeline. Phone-first.
- **Admin Officer (Records/Admin Staff)** — the shepherd: reviews packets after chief approval, hands them to FMS, and updates the external statuses. Desktop.
- **System Admin** — configures checklists, rates, signatories, taxonomy, holiday calendar.

### 3.2 RBAC registry rows (registered into the shared §29 registry at module startup)

| Action | Allowed roles |
|---|---|
| Create/edit own claim (Draft/Returned) | Staff, all roles except Viewer |
| Edit any claim | Admin Officer, System Admin |
| Submit claim (checklist gate) | Claim owner; Admin Officer on behalf |
| Approve / return at a chain step | The role configured for that step, for their own scope (own division/section) |
| Apply digital signature / certification | Configured signatory for that step only |
| Waive a checklist item (reason mandatory) | Admin Officer, System Admin |
| Set external FMS statuses | Admin Officer, System Admin |
| Record settlement (refund OR / payout) | Admin Officer, System Admin |
| Cancel/void a claim (reason mandatory) | Owner while Draft; Admin Officer/System Admin any time |
| Configure checklists, rates, taxonomy, signatories | System Admin |
| View all claims + amounts | Owner sees own; Admin Officer/Director/System Admin see all; Chiefs see their division. **Claims are NOT bureau-public** (unlike DMWIS documents) — they carry personal financial data. |

That last row is a deliberate divergence from DMWIS's "all staff see all documents" default, and it is the reason the module's list endpoints must filter by scope server-side, never client-side.

---

## 4. Regulatory Config Pack (defaults, never hardcodes)

All values live in `reimb_config` (tenant config), editable by System Admin, displayed with their legal source. Confirmed by online research 2026-07 (§16 sources):

| Key | Default | Source |
|---|---|---|
| `per_diem.metro_manila_huc` | ₱2,200 /day | EO 77 s. 2019 |
| `per_diem.other_areas` | ₱1,800 /day | EO 77 s. 2019 |
| `per_diem.apportionment` | 50% lodging / 30% meals / 20% incidentals | EO 77 |
| `per_diem.departure_day_rate` | 50% of daily rate (day of departure back to station, if not arrival day) | EO 77 |
| `per_diem.radius_km` | 50 km — inside radius: no lodging component unless justified | EO 77 |
| `liquidation.deadline_working_days` | 30 days after return to official station | COA Circular 97-002 |
| `liquidation.accountant_verify_days` | 10 days (informational display) | COA 97-002 |
| `liquidation.overdue_note` | "Unliquidated advances may accrue 6% interest and salary deduction" (warning copy) | COA 97-002 |
| `receipts.cenrr_max` | ₱300 (no-receipt fares → CENRR) | COA Circular 2021-001 |
| `receipts.rer_range` | >₱300–₱1,000 (→ RER) | COA Circular 2021-001 |
| `fare.class` | Economy only; above-rate needs Head-of-Agency certification | EO 77 |
| `jo_cos.extra_requirements` | ON — JO/COS claimants require Head-of-Office certification + approval | DM 2025-0202/-0202A |

R-0 confirms whether the 30-day liquidation clock counts calendar or working days at DOH practice (default: **calendar days**, per COA text) — a single config value either way.

---

## 5. Domain Model

All timestamps `timestamptz` UTC; display Asia/Manila. Money is `numeric(12,2)` PHP. JSONB for flexible payloads. Indexes on every status/holder/deadline column.

### 5.1 `reimb_claim`
`id PK · ref_no (RB-YYYY-NNNN) · kind ENUM(reimbursement, liquidation) · claimant_id FK core_staff · activity_id FK nullable → core_activity (data-spine link; wizard step 1 offers "pick or create activity") · dpo_no · dpo_date · dpo_document_id nullable (soft reference — backfilled to the DMWIS document record when Module 2 ships; see the Integration Blueprint §2.3) · purpose text · destination text · destination_class ENUM(metro_manila_huc, other) · date_depart date · date_return date · fund_source ENUM(GF_ORS, TF_BUR) · is_jo_cos bool (auto from directory employment status) · cash_advance_id FK nullable → reimb_cash_advance · status (§6) · holder_kind ENUM(user, external_fms) · holder_id nullable FK · holder_since timestamptz · next_action text (auto-set per status) · liquidation_deadline date nullable · totals JSONB {per_diem, transport, other, grand, advance, to_reimburse, to_refund} · custom JSONB · created/updated`.

### 5.2 `reimb_itinerary_leg`
`id · claim_id FK · seq · leg_date · place · time_depart · time_arrive · transport_mode ENUM(plane, bus, boat, taxi, ride_hail, gov_vehicle, other) · fare numeric · per_diem_pct smallint (100/50/0, auto-suggested, editable with reason) · per_diem_amount numeric (computed) · leg_total numeric (computed)`.

### 5.3 Checklist — catalog and instance
- **`reimb_checklist_catalog`** (System Admin-editable, seeded from FS-BD-01): `id · claim_kind · code (e.g. LR-06) · label (verbatim checklist wording) · group ENUM(authority, itinerary, proof_of_travel, transport, lodging_meals, report, financial) · required_rule JSONB · evidence ENUM(upload, generated_doc, external_wet_sign, data_only) · auto_checks JSONB[] · sort · active bool`.
- **`reimb_checklist_item`** (per claim): `id · claim_id · catalog_id · status ENUM(missing, attached, generated, auto_passed, auto_flagged, waived) · attachment_ids int[] · waiver_reason text nullable · checked_at/by`.

`required_rule` JSON grammar (evaluated server-side; the builder implements exactly these operators):
```json
{"always": true}
{"if": {"field": "is_jo_cos", "eq": true}}
{"if": {"field": "transport_modes", "contains": "taxi"}}
{"if": {"field": "totals.other", "gt": 0}}
{"any": [ {...}, {...} ]}   {"all": [ {...}, {...} ]}
```

`auto_checks` entries (the engine of Objective 2):
```json
{"type": "file_present"}
{"type": "amount_threshold", "field": "fare", "max_key": "receipts.cenrr_max", "on_exceed": "require_item:RER"}
{"type": "date_within_trip"}                       // receipt/leg dates inside depart..return
{"type": "sum_matches", "of": "legs.fare", "vs": "totals.transport", "tolerance": 0}
{"type": "keyword_absent", "keywords": ["business class", "first class"], "source": "ocr", "flag": "fare.class"}
{"type": "deadline_check", "key": "liquidation.deadline_working_days"}
```
Auto-checks set `auto_passed` / `auto_flagged` — a flag never blocks alone; it surfaces to the reviewer with the reason. **Missing required items DO block submission.**

### 5.4 `reimb_cash_advance`
`id · claimant_id · dv_no · dv_date · amount · dpo_no · date_return date (drives the 30-day clock) · status ENUM(open, liquidation_started, settled, overdue) · settled_at`.

### 5.5 Approvals & signatures
`reimb_approval_step`: `id · claim_id · seq · step_kind ENUM(approve, certify_A, certify_B, certify_C, sign) · role_required · assignee_id (resolved at activation) · status ENUM(pending, active, done, returned, skipped) · acted_at/by · snapshot_id FK (frozen-PDF signature record, reusing §19.8 core service)`.
Chains are **per claim-kind config** (`reimb_signatory_config`), seeded: Reimbursement → Division Chief approve → Admin Officer review → (Director sign if type requires) → hand to FMS. Liquidation → Certification **A = claimant → B = Director IV → C = Head, Accounting Unit (external wet-sign capture: Admin Officer uploads the signed page and checks the step)**.

### 5.6 Returns & learning loop
`reimb_return_reason_catalog`: `id · code · label · category ENUM(missing_doc, wrong_amount, wrong_form, no_signature, late, policy, other) · promoted_check bool · active`.
`reimb_return_event`: `id · claim_id · step_id · reason_ids int[] (≥1 mandatory) · free_comment text · returned_to ENUM(claimant, previous_step) · created_at/by`.

### 5.7 Supporting
`reimb_attachment` (Drive file id, magic-byte type, OCR text, auto-renamed `[RefNo]_[YYYYMMDD]_[HHMMSS]`); `reimb_status_history` (every transition: from, to, actor, note — feeds the tracker UI); `reimb_external_event` (FMS journey updates: status, noted_by, note, date).

---

## 6. Status Machine (explicit and closed)

Two-dimensional state everywhere (per §19.6): `status` is the workflow position; **Overdue is a derived badge**, never a status. Transitions outside this table are rejected server-side.

### 6.1 Reimbursement claim
| # | Status | Holder | Next action (auto-copy) | Allowed transitions (by) |
|---|---|---|---|---|
| 1 | Draft | Claimant | "Complete your packet" | → Submitted (owner; gate: all required items non-missing) · → Cancelled (owner) |
| 2 | Submitted | System (instant) | — | auto → For Approval (activates step 1) |
| 3 | For Approval | Current step assignee | "Approve or return" | → next step / → Admin Review (chain end) (assignee) · → Returned (assignee; reason mandatory) |
| 4 | Returned | Claimant | "Fix and resubmit" | → Submitted (owner; re-runs gate + auto-checks) · → Cancelled |
| 5 | Admin Review | Admin Officer | "Final check & print packet" | → Handed to FMS (admin) · → Returned |
| 6 | Handed to FMS | **external_fms** | "Waiting on FMS — update status" | → With Budget → With Accounting → Payment Processing (admin, any order/skips allowed) · → FMS Returned |
| 7 | FMS Returned | Admin Officer | "Relay FMS comments" | → Returned (to claimant, with taxonomy reasons) |
| 8 | Paid / Closed | — | — | terminal (admin records payout ref) |
| 9 | Cancelled/Void | — | — | terminal, excluded from KPIs, reason mandatory |

### 6.2 Liquidation
`CA Open → Liquidation Draft → Submitted → Certifications (A→B→C in order) → Handed to FMS → …external… → Settled`, plus `Refund Recorded` side-step when actual < advance (captures DOH OR no./date) and `Reimbursement Due` when actual > advance (spawns linked reimbursement of the difference — one tap, pre-filled). The 30-day countdown starts at `cash_advance.date_return` and shows on every liquidation surface from CA creation.

### 6.3 Derived badges
`On Track / Due Soon (≤ 7 days) / Overdue` computed by the 15-min Celery beat + on-view, keyed to: liquidation deadline (claimant-facing) and per-step holder SLA (§7) (approver-facing).

---

## 7. Work-Management Flow — NON-NEGOTIABLE

These six rules are binding on every screen and endpoint; QA tests each one explicitly:

1. **One holder, always.** Every claim in a non-terminal status has exactly one `holder` (a user, or `external_fms`). There is no state where `holder` is null. Handoffs are atomic (same transaction as the status change).
2. **One next action, always.** Every status carries an auto-set, plain-language `next_action` shown wherever the claim appears. Nobody ever wonders what happens next or whose move it is.
3. **My Work is the home surface.** Every user's module landing is a **My Work inbox**: "Waiting on you" (holder = me, urgency-ordered) above "Your claims in flight" (owner = me, with holder + next action + days-in-state). Zero-state: "Nothing waiting on you 🎉".
4. **Holder SLA + reminder ladder (holder only — no escalation).** Config `sla.approval_working_days` (default 3). At SLA: item turns Due Soon and the holder gets one notification. Every `sla.reminder_repeat_days` (default 2 working days) after: one repeat nudge **to the holder only**. Per the author's decision, superiors are never auto-notified — but overdue items are plainly visible on the division/office dashboards, so visibility does the escalating passively.
5. **Stalls are visible, not silent.** The pipeline board (§9.6) shows days-in-state on every card; anything Overdue sorts to top with the red badge. The Admin Officer's queue includes an "External > 10 working days" filter for FMS follow-ups.
6. **Returns never orphan.** A return always sets holder back to a person (claimant or previous step) with reasons attached; a resubmission always re-enters the same chain at step 1 (fresh approvals — signatures bind to frozen snapshots and a changed packet must be re-approved, per §19.8 logic).

---

## 8. Computation Spec (with worked example)

Per-diem calculator (pure function, unit-tested):
- Day of arrival at destination and each full working day there: **100%** of the class rate.
- Day of departure back to the official station (if a different day): **50%**.
- Inside the 50-km radius: 0% lodging component by default (config), justification field unlocks it.
- Rate class from `destination_class`; amounts from config keys.

**Worked example (fixture + QA case):** 3-day trip, Manila (HUC), depart Jul 1 arrive same day, work Jul 2, return Jul 3 → Jul 1: ₱2,200 · Jul 2: ₱2,200 · Jul 3: ₱1,100 → **per-diem total ₱5,500**. Transport actuals sum from legs; grand total = per diem + transport + other. Liquidation settlement: `advance − actual` → positive = refund (record OR no.), negative = "Reimbursement Due" spawn. All arithmetic server-side; the UI displays, never computes.

---

## 9. UX & Design/Layout Specification

### 9.1 Design principles (in priority order)
1. **One thing per screen-moment.** The wizard asks one cluster at a time (GOV.UK form-structure guidance); never a 40-field page.
2. **The checklist is the interface.** The packet screen IS the FS-BD-01 checklist rendered as a **GOV.UK-style task list**: grouped tasks, a status chip per item (`To do / Attached / Generated / Checked ✓ / Flagged ⚠ / Waived`), completable in any order, with an always-visible progress line ("9 of 12 required items done").
3. **Plain language everywhere.** Item labels carry the legal wording as secondary text; the primary label is human ("Upload your boarding pass" over item 10's formal text). English interface (M-3); tooltips explain *why* an item is required, citing the rule.
4. **Never block without a path.** Every validation message says what to do next ("Fare is over ₱300 — upload an RER instead of a CENRR. [What's an RER?]").
5. **Tokens only.** All colours/spacing/type from the platform CSS custom properties (§14.4); status colours: green=done, amber=due soon/flagged, red=overdue/blocked, grey=waiting-external. Empty states and skeleton loaders on every list (M-1).

### 9.2 Screen inventory (React, route-split under `/reimbursement`)
| Screen | Layout | Device priority |
|---|---|---|
| My Work inbox (module home) | Two stacked card lists; urgency chips | Both |
| New Claim wizard | 5 steps, stepper top, autosave every step | Desktop-first |
| Claim packet (task list) | Left: grouped checklist; right rail: totals + status + deadline | Desktop-first |
| Claim tracker (owner view) | Vertical timeline of §6 statuses w/ dates + holder + next action | Both |
| Approval screen | Single card: summary, computed totals, flags, packet PDF preview; sticky Approve / Return buttons | **Phone-first** |
| Return dialog | Reason picker (taxonomy chips, multi) + optional comment | Phone-first |
| Pipeline board (Admin/Director) | Columns = status groups (In Bureau / With FMS / Done); cards show ref, name, ₱, days-in-state | Desktop-first |
| Liquidation tracker | Same as claim tracker + 30-day countdown ring | Both |
| Insights (learning loop) | Ranked return-reasons bar list, trend, "promote to pre-check" action | Desktop |
| Module admin | Checklist catalog editor, rates, signatory chains, taxonomy, SLAs | Desktop |

### 9.3 Wizard steps (exact)
1. **Trip** — DPO no./date, purpose, destination (+ auto HUC/other classification with override), dates. *If a matching open cash advance exists → offer "Liquidate that instead?"*
2. **Itinerary** — leg table with add-row; per-diem % auto-suggested per §8, running totals live in the rail.
3. **Money** — transport actuals per leg, other expenses (each spawns its conditional checklist items), fund source GF/TF.
4. **Documents** — the task-list; generated docs (Appendix A/B) show as `Generated ✓` cards with preview; uploads drag-drop, phone camera capture allowed.
5. **Review & submit** — full packet summary, all auto-check results, the gate. Submit disabled until required items clear, with the blocking items listed inline.

### 9.4 Approval screen behaviors (phone)
Approve = one tap + confirm sheet. Return = must pick ≥1 taxonomy reason (chips), comment optional. Flagged auto-checks render as amber callouts above the buttons — an approver can approve past a flag (logged) but never past a missing required item. Queue swipes advance to the next waiting claim.

### 9.5 Copy & accessibility
Sentence case; no jargon in primary labels; dates always "Jul 20, 2026"; money always "₱2,200.00". WCAG AA contrast via tokens; all actions keyboard-reachable; touch targets ≥44px; the task list is a semantic list with status announced to screen readers.

### 9.6 The pipeline board is the module's public face
Director/Admin default view. Counts + peso totals per column header; overdue cards float to top; clicking a card opens the tracker. This is Objective 4 made visible.

---

## 10. Template Auto-Assembly (Objective 1)

Mapping table (config `reimb_template_map`) binds claim fields → Google Docs template placeholders (`{{claimant_name}}`, `{{legs_table}}`, `{{total}}`, `{{dpo_no}}`…). Flow: claim data → copy template in Shared Drive → placeholder merge → export PDF → SHA-256 → store as frozen snapshot (§19.8 core service) → checklist item flips to `Generated`. Templates seeded from the real Drive files (Appendix A `Itinerary.docx`, Appendix B, Liquidation Report, JO/COS Certification, Certificate of Appearance blank). Regeneration after any edit voids prior snapshots and re-flags signature steps. Celery task, idempotent, 3 retries; Google-down → claim saves anyway, generation queues, user sees a non-blocking notice (§19.12 pattern).

---

## 11. Comment-Learning Loop (Objective 3)

Seed taxonomy (from FS-BD-01 failure modes; System Admin editable): `missing_appearance_cert · missing_boarding_pass · fare_needs_rer · thermal_receipt_no_copy · wrong_per_diem_computation · dates_dont_match_dpo · no_meals_certification · unsigned_appendix_b · late_liquidation · wrong_fund_source · other`.
Every return event stores reasons (§5.6). **Insights** ranks reasons by 90-day count with trend. "Promote to pre-check": one click creates a warning-level auto-check shown at wizard step 5 ("Claims like yours are often returned because…"), no code change — it writes an `auto_checks` row. Privacy: aggregates only, mirroring the §14.7 pattern; per-person return counts are visible only to the person themselves.

---

## 12. Notifications Matrix

| Event | → Recipient | Note |
|---|---|---|
| Claim lands in your queue | New holder | bell + WebSocket |
| Holder SLA reached / repeats | Holder only | §7.4 ladder |
| Returned to you | Claimant | includes reasons verbatim |
| External status updated | Claimant | "Your claim is now With Accounting" |
| Paid / Settled | Claimant | terminal, celebratory tone |
| Liquidation D-7 / D-3 / D-0 / overdue | Claimant (CA holder) | COA warning copy at D-0 |
| Certification step ready | That signatory | in-order chain |
All through the core engine (§14.8); email only for liquidation D-3/D-0 (transactional).

---

## 13. KPIs & Reports (feeds Module 4 later)

Turnaround (submit→handed-to-FMS; handed→paid), first-touch time per step, return rate + top reasons, liquidation compliance % (settled within 30 days), overdue CAs count + ₱, pipeline totals by status, per-division volume. Time filters + deltas per §19.9 dashboard rules; exports per the platform download standard (WeasyPrint/openpyxl, agency header, generated-by).

**Data-spine feed:** because every claim carries a nullable `activity_id`, **travel spend per activity — and later per PPA — is a query, not a compilation**. This feeds the future WFP module's financial-accomplishment reporting and the Director's cost-per-activity view (Integration Blueprint §4 row 6). The wizard therefore treats the activity picker as a first-class (though skippable) field, and the pipeline board exposes an "unlinked to activity" filter so coverage stays high.

---

## 14. Build Phases (Sonnet-sized, each with QA gate)

Supersedes the R-1…R-9 sketch in the dependency analysis with tighter slices; every phase ends with automated QA green + a plain-language manual test guide.

| Phase | Builds | Automated QA must prove |
|---|---|---|
| **R-0 Confirmations** (session, not code) | §15 items | — |
| **R-1 Model + config pack** | §5 tables, §4 config, ref numbers, seed catalogs (FS-BD-01, taxonomy, signatory chains) | Migrations idempotent; seeds load; config editable; rates render with sources |
| **R-2 Wizard + computation** | Screens §9.3 steps 1–3, per-diem engine §8, autosave | Worked example computes ₱5,500; HUC/other switch; 50-km rule; autosave survives refresh |
| **R-3 Checklist engine + uploads** | Catalog/instance, rule grammar, auto-checks, task-list UI, waivers | JO/CO conditional appears only for JO/COS; taxi >₱300 demands RER; submit blocked on missing; flag ≠ block; waiver logged |
| **R-4 Approval chain + work management** | §6 machine, §7 rules, My Work, approval screen, return dialog, reminders | No null holders (property test across all transitions); return requires reason; resubmit restarts chain; SLA reminder fires to holder only, never superior; phone viewport passes |
| **R-5 Templates + signatures** | §10 assembly, frozen snapshots, certification steps A/B/C, wet-sign capture | Placeholder merge exact; edit-after-sign voids + re-flags; C-step upload path works; Google-down degrades non-blocking |
| **R-6 Liquidation + settlement** | CA records, 30-day clock, liquidation flow, refund/spawn math, countdown UI | Deadline from date_return incl. holiday calendar; refund path records OR; over-advance spawns pre-filled claim; D-notifications fire |
| **R-7 External tracking + pipeline board** | FMS statuses, external events, board, admin queue | Statuses skip/reorder legally; board totals match DB; >10-day external filter |
| **R-8 Insights + learning loop** | §11 dashboard, promote-to-pre-check | Promotion creates a working warning with no deploy; aggregates only |
| **R-9 Hardening + pilot flag** | Security suite (scope filters!), resilience, perf budgets, fixtures polish | Scoped visibility enforced per §3.2 (owner cannot read others' claims via API); flag ON for pilot cohort only |

**Fixtures (built in R-1, used everywhere):** 6 synthetic travellers (1 JO/COS), 10 trips incl. the §8 worked example, an open cash advance aged 25 days (near-overdue), receipt images incl. a >₱300 taxi fare and a thermal receipt, and the real blank templates from Drive.

---

## 15. R-0 Confirmations (short list — nothing else blocks)

1. **30-day clock:** calendar days (COA default) or DOH working-day practice? → one config value.
2. **Signatory chain per kind:** confirm seeded chains in §5.5 against actual BLHSD practice (esp. when the Director signs reimbursements vs delegating to chiefs).
3. **Head, Accounting Unit (certification C):** confirm external wet-sign capture (Admin uploads signed page) is acceptable — they are FMS, outside the platform.
4. **Phase-1 directory slice** (from the dependency analysis): confirm seeding staff/approvers from CSS-IS data vs manual entry for the pilot cohort.
5. **Per-diem rate class list:** confirm the destination→HUC classification list to seed.

---

## 16. Online Sources Used to Close Gaps

- COA Circular 97-002 (liquidation: 30 days local, accountant 10-day verification): [coa.gov.ph circular](https://www.coa.gov.ph/wpfd_file/coa-circular-no-97-002-february-10-1997/), [liquidation procedures commentary](https://www.respicio.ph/commentaries/procedures-for-liquidation-processing-in-government-offices-in-the-philippines), [UPM RGAO copy](https://rgao.upm.edu.ph/wp-content/uploads/2023/10/COA-C97-002-Cash-Advances-2-months-cash-flow.pdf)
- EO 77 s. 2019 (₱2,200/₱1,800 rates; 50/30/20 apportionment; 50% departure day; 50-km rule): [Official Gazette PDF](https://www.officialgazette.gov.ph/downloads/2019/03mar/20190315-EO-77-RRD.pdf), [CS Guide entry](https://www.csguide.org/items/show/1358), [GABOTAF DTE guide](https://gabotaf.com/eo-77-a-quick-comprehensive-guide-to-the-grant-of-daily-travel-expenses-dte/), [PAGBA presentation](https://www.pagba.com/wp-content/uploads/2019/08/Travel-Allowances-and-Expenses-for-Official-Local-and-Foreign-Travels.pdf)
- Task-list / form-structure UX patterns: [GOV.UK task list component](https://design-system.service.gov.uk/components/task-list/), [Complete multiple tasks pattern](https://design-system.service.gov.uk/patterns/complete-multiple-tasks/), [GOV.UK form structure](https://www.gov.uk/service-manual/design/form-structure)

---

*This spec deepens, and where more specific supersedes, the build sequence in `Reimbursement_First_Dependency_Analysis.md`. The Execution Plan remains the platform's single source of truth; this document governs the reimbursement module's build.*
