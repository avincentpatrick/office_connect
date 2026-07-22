# Office-Connect — Digital Transformation & Integration Blueprint

**Companion to:** `OfficeConnect_Build_Execution_Plan_v1_0.docx` (the single source of truth), `Reimbursement_First_Dependency_Analysis.md`, `Reimbursement_Module_Build_Spec_v1.md`
**Status:** Enhancement blueprint — deepens the whole plan; proposes three Day-1 additions for the author to fold into the execution plan (§8). Contradicts nothing locked.
**Purpose:** Make the platform's *integration architecture* explicit so that, once fully implemented, **every module that must link, links — and every government output the bureau owes is generated seamlessly** from work already captured.

---

## 1. The Transformation Thesis

The execution plan's principle "capture, don't log" (§3.1) has a logical end-state this blueprint names and designs for:

> **Reports are byproducts of work, not work.**

Today the bureau does the work *and then* compiles the evidence of the work — CSMR spreadsheets, FOI logs, DTrak sheets, OPCR accomplishment columns, WFP financial accomplishment, annual-report inputs — by hand, from memory, across scattered files. Digital transformation is achieved when the *doing* (logging a document, running an activity, taking a survey, filing a travel claim, booking a room) produces the data, and the *reporting* is a one-click generation.

**The seamlessness test (binding design test for every module):** *for each mandated output, can it be generated — not compiled?* If generating it would require a human to re-enter, cross-reference, or reconcile data the platform already touched, a link is missing and this blueprint is the place to add it.

---

## 2. The Data Spine — What Everything Joins On

The platform already locks four shared spine entities; this blueprint adds one and formalises two patterns.

### 2.1 Existing spine (locked in the execution plan)
| Entity | Where | Joins |
|---|---|---|
| **Staff** (plantilla-authoritative) | `core_*` Staff Directory (§14.3, Decision 10) | who did/approved/signed everything |
| **Org units** (division/section) | tenant config (§4, §13) | where work belongs; report drill-downs |
| **Audit chain** | core audit (§14.8, S-2) | tamper-evident provenance for every record |
| **Signatures** | frozen-snapshot service (§19.8) | one signing model for documents, claims, certifications |
| plus: reference numbers (S-4), feature flags (§14.5), notifications (§14.8), holiday calendar (§19.7), Drive storage (S-5) — shared services all modules consume | | |

### 2.2 NEW — `core_activity`: the missing join key (proposed Day-1 item #15)

**Finding.** No shared entity answers *"what work was this for?"* Travel claims carry a free-text purpose; CSS surveys measure activities; room bookings host activities; DPOs authorize activities; WFP lines **are** activities (PPAs); OPCR/DPCR accomplishments roll them up; the Annual Report narrates them. The join key was implicitly parked when the WFP module was parked (Q6) — but the *key* is cheap and the *module* is not, and free text can never be joined retroactively.

**Fix — a minimal registry, not a planning system:**

`core_activity`: `id PK · title · ppa_code text nullable (WFP alignment, filled later) · division_id · section_id nullable · date_start · date_end nullable · venue text nullable · status ENUM(planned, ongoing, done, cancelled) · created_by · custom JSONB`.

Rules:
- **Creation is lightweight.** Chiefs and Admin staff create activities; every module's capture screen offers **"pick or create activity"** (type-ahead; creating takes one field — the title). Ease of use governs: linking must never cost more than a few seconds, and `activity_id` is **nullable everywhere** — an unlinked record is always allowed, just less reportable.
- **The WFP module enriches, never duplicates.** When WFP arrives, it attaches targets/budget lines to these same rows (via `ppa_code`), rather than creating a rival activity table.
- **Coverage is a visible metric.** The Government Outputs screen (§5) shows per-report source coverage (e.g. "82% of Q2 claims are activity-linked"), making unlinked work visible without blocking anyone.

### 2.3 NEW — the soft-reference pattern (proposed Day-1 item #16)

Reimbursement ships before DMWIS, yet a claim's DPO *is* a DMWIS document. Binding pattern for any module that references a not-yet-built module's entity:

1. Store the **natural key as text** (e.g. `dpo_no`) **plus a nullable FK** (e.g. `dpo_document_id`).
2. When the target module ships, an idempotent **backfill task** matches natural keys and fills the FKs; ambiguities go to a review queue (same pattern as the Sheets-sync conflict queue, §19.10).
3. UI renders the soft ref as plain text until the FK exists, then as a link — no redesign.

No module ever blocks on another's existence; links accrue as the platform grows.

### 2.4 NEW — report lineage (proposed Day-1 item #17)

Every generated government output records: report type, period, generated-by, generated-at, config version, and the **source-row filter used** — so any figure in any submitted report can be traced to its underlying records (an ISO 9001 and COA expectation, and cheap if done from the first generator).

---

## 3. Cross-Module Link Registry

The single authoritative map of "everything that must link." Each link appears once, with its pattern. Integration invariants follow.

| From → To | Link | Pattern | When live |
|---|---|---|---|
| Reimb claim → DMWIS document (DPO/Travel Order) | `dpo_no` text + `dpo_document_id` nullable | soft-ref → hardens | claim: R-1; hardens Phase 4–7 |
| Reimb claim → Activity | `activity_id` nullable | spine | R-1 |
| Reimb itinerary → Staff (claimant, approvers) | FKs to directory | spine (exists) | R-1 |
| CSS Activity/RP surveys → Activity | `activity_id` nullable | spine | CSS-IS migration (Phase 1/8) |
| Room booking → Activity | `activity_id` nullable | spine | Phase 9 |
| DMWIS document → Activity | optional tag (multi) | spine | Phase 4–7 |
| DMWIS document → meeting/booking | optional link ("minutes of") | soft-ref | Phase 9 |
| WFP line (future) → Activity | `ppa_code` enrichment | spine owner (future) | WFP module |
| OPCR/DPCR (future) → Activity roll-up | success indicators ↔ `ppa_code` | spine consumer (future) | WFP module |
| Module 4 → all modules | read-only KPI queries + Report Factory | consumer | Phase 9 |
| Landing query bar → modules **and reports** | NAV_GROUPS `intent_keywords`, incl. report intents ("generate CSMR", "FOI report") | exists + extension | Phase 3+ |

**Integration invariants (binding):**
1. **No cross-module writes.** Modules touch each other's data only through core services (auth, directory, activity, audit, signatures, notifications). Enforced by the import linter (Q11).
2. **Joins go through spine keys only** — staff, org unit, activity, document ref. No module invents a rival identity for a spine concept.
3. **Every cross-module link is nullable/soft.** A missing link degrades reporting coverage, never blocks work — adoption risk (§3.1) always wins.
4. **Every generated report is lineage-traceable** (§2.4).

---

## 4. The Report Factory — Mandated Outputs → Generation Map

The concrete meaning of "seamless": each output below becomes a **generator** — a one-click, download-standard (PDF/Excel, §19.9) export whose data is already in the platform because work was captured where it happened. Grounded in the Drive evidence base and online research (§10).

| # | Government output | Mandated by / cadence | Source data (module) | Generator lives in | Available from |
|---|---|---|---|---|---|
| 1 | **Client Satisfaction Measurement Report (CSMR)** — harmonized ARTA format, Annex B outline | ARTA MC 2022-05 (amended 2023-05); **annually, last working day of January** | All three survey types + response stats (CSS-IS) | CSS-IS reports → Module 4 | **NEW small deliverable:** a CSMR Annex-B exporter over existing CSS-IS data (Phase 8/9) |
| 2 | **FOI registry & compliance summary** | eFOI/PCOO practice; R.A.-based | FOI-typed documents + 3/15/30-day deadline outcomes (DMWIS §19.7) | DMWIS admin reports → Module 4 | Phase 4–7 |
| 3 | **Communications registry (DTrak)** — incoming/outgoing | Bureau records practice (replaces the Google Sheet) | Full document log (DMWIS) | DMWIS list exports; Sheets sync until cutover | Phase 4–7 |
| 4 | **ISO 9001 QMS evidence pack** — audit trail extracts, controlled-document lifecycle, management-review data pack | ISO 9001:2015 (live, audited — 2025 IQA) | Core audit chain + DMWIS lifecycle + cross-module KPIs | Module 4 | accrues from Phase 0; pack assembled Phase 9 |
| 5 | **OPCR / DPCR / IPCR accomplishment columns** | CSC SPMS cascade (office → division → individual) | Activity registry + per-module outputs (documents completed, activities run, satisfaction scores, TA delivered) | Module 4 | **partial** from Phase 9 (actuals); **full** when WFP module adds targets |
| 6 | **WFP quarterly physical & financial accomplishment** | DBM/DOH planning cycle (WFP2026 structure in Drive) | WFP targets/budget (future module) **× reimbursement actuals per `ppa_code`** × activity completion | WFP module → Module 4 | at WFP module — *enabled now* by the spine (§2.2) |
| 7 | **Liquidation Report + full claim packets** | COA 97-002 / FMS FS-BD-01 | Reimbursement module | Reimbursement (already specified) | first module shipped |
| 8 | **Calendar of Activities (CY)** | Bureau planning (CY-2026 calendar in Drive) | Activity registry + room bookings + announcements | Module 4 / Admin | Phase 9 |
| 9 | **Annual Report data pack** | Bureau AR (2025 AR in Drive) | Everything: volumes, compliance rates, satisfaction, spend per division/PPA, activity roster | Module 4 | accrues continuously; full at Phase 9+ |

**The ripple that pays for the spine:** row 6. WFP *financial* accomplishment is today the hardest number to compile (receipts → SAA lines by hand). With `activity_id` on every claim from R-1 and `ppa_code` on activities later, **travel spend per PPA is a query** — one nullable column now buys an unbuildable-retroactively capability later. The same join gives the Director "cost per activity per division" from the first quarter of reimbursement data.

---

## 5. The Government Outputs Screen (Module 4 — new surface)

The user-visible embodiment of the Report Factory: one screen where the bureau *sees* its reporting obligations and generates them.

- **One card per mandated output** (rows in §4): name, legal basis, period covered, **deadline countdown** (e.g. "CSMR due Jan 30 — 45 days"), **source coverage %** (how much of the period's data is linked/complete), last generated (with lineage), and a **Generate** button.
- Coverage below a threshold shows *what's missing and where to fix it* ("18 claims unlinked to activities — open list"), turning data quality into a visible, assignable task instead of a year-end surprise.
- Generated files follow the platform download standard (agency header, period, generated-by, page numbers) and are archived with lineage (§2.4) — the submission trail *is* QMS evidence.
- Deadlines use the holiday calendar (working-day aware); the query bar routes report intents here ("generate CSMR", "FOI report") via NAV_GROUPS `intent_keywords`.

---

## 6. Module-by-Module Link Pass

What each module already contributes, and the *small additions* each needs to plug into the spine. No module's locked scope changes; additions are one-column or one-exporter sized.

### Module 1 — CSS-IS (surveys)
- **Contributes:** satisfaction data for CSMR (#1), OPCR quality indicators (#5), annual report (#9).
- **Add:** `activity_id` on Activity-SERVQUAL and RP-SERVQUAL surveys (survey creation gains "pick or create activity"); the **CSMR Annex-B exporter**. ARTA Walk-in surveys need no activity link (transaction-based).

### Module 2 — DMWIS (documents)
- **Contributes:** FOI registry (#2), DTrak registry (#3), controlled-document QMS evidence (#4), turnaround KPIs (#5, #9).
- **Add:** optional multi-tag `activity_id` on documents; FOI and DTrak registry exporters (list exports in mandated shapes); DPO backfill task that hardens reimbursement's soft refs (§2.3).

### Module 3 — Admin (rooms + announcements)
- **Contributes:** utilisation KPIs (#9), calendar inputs (#8).
- **Add:** `activity_id` nullable on bookings ("what is this room for?" — one optional picker); bookings feed the Calendar of Activities generator.

### Module 4 — Reports & Analytics
- **Contributes:** the consolidation layer (Q4).
- **Add:** the **Government Outputs screen** (§5) and the cross-module joins it needs; management-review data pack assembly (#4); OPCR actuals roll-up (#5). This is the largest addition of the pass and lands in its existing Phase 9 slot.

### Reimbursement module (first vertical — already specced)
- **Contributes:** liquidation packets (#7), spend-per-activity/PPA (#6, #9), liquidation-compliance KPI.
- **Add (spec edit, done alongside this blueprint):** `activity_id` + `dpo_document_id` soft-ref on claims; travel-spend-per-PPA feed noted in its KPI section.

### Parked modules (architecture must not block — §22)
- **WFP:** becomes the spine's *enricher* (targets/budget per `ppa_code`) → completes #5 and #6. Its future requirements session should start from `core_activity`, not a blank page.
- **Meetings/Calendar:** deepens #8; meetings become activities natively; minutes link documents↔bookings.
- **TA tracking:** TA deployments are activities; links RP-SERVQUAL feedback (already in CSS-IS) to the TA activity it measured — closing the loop the plan's pain-point table asks for.

---

## 7. Phase-by-Phase Integration Accrual

How the transformation assembles across the (reimbursement-first) sequence — each stage lists the links that exist when it closes:

| Stage | Links & Report Factory state |
|---|---|
| **Phases 0–2 (floor)** | Spine complete: identity, org units, audit, tokens, flags, ref numbers, **`core_activity` registry**. Report Factory: lineage convention in place, no outputs yet. |
| **Reimb R-1…R-9** | Claims ↔ staff ↔ activities ↔ money; DPO soft refs accruing. **Output #7 live.** Spend-per-activity data starts accumulating from day one of the pilot. |
| **Phase 3 (landing)** | Query bar routes module + report intents; query log accrues the unmet-need dataset. |
| **Phases 4–7 (DMWIS)** | Documents ↔ activities; FOI + DTrak registries live (**#2, #3**); DPO backfill hardens claim links; QMS document-lifecycle evidence accrues (**#4 partial**). |
| **Phases 1/8 (CSS-IS)** | Surveys on the shared store; surveys ↔ activities; **CSMR exporter (#1)** — the January deadline is servable from the platform. |
| **Phase 9 (Admin + Module 4)** | Bookings ↔ activities; **Government Outputs screen** unifies #1–#4, #7–#9; OPCR actuals partial (**#5**); leadership cross-view (compliance × satisfaction × utilisation × spend). |
| **Phase 10 (hardening)** | SIT adds **cross-module join tests** (a claim's activity appears in the activity's cost roll-up; a survey's activity links back; lineage resolves for every generator). |
| **Future (WFP, Meetings, TA)** | WFP enriches activities with targets/budget → **#5 full, #6 live**. The transformation end-state: every §4 row generated, none compiled. |

---

## 8. Proposed Additions to the Execution Plan (for the author to fold in)

The `.docx` governs; these are amendment candidates, each one paragraph:

1. **Day-1 checklist #15 — `core_activity` registry** (§2.2): minimal schema in core at Phase 0; nullable `activity_id` convention for all operational tables; "pick or create" UX affordance rule.
2. **Day-1 checklist #16 — soft-reference convention** (§2.3): natural-key text + nullable FK + idempotent backfill, for any reference to a not-yet-built module.
3. **Day-1 checklist #17 — report lineage** (§2.4): every generated mandated output records its source filter and config version.
4. **Module 4 scope note:** add the **Government Outputs screen** (§5) to Phase 9's Reports & Analytics build.
5. **CSS-IS scope note:** add the **CSMR Annex-B exporter** to Phase 8/9.
6. **DMWIS scope note:** add FOI/DTrak registry exporters and the DPO backfill task to Phases 4–7/10.
7. **§22 note:** future WFP requirements session starts from `core_activity` (enrich, don't duplicate).

---

## 9. Gaps Found & Filled / Open Confirmations

**Found and filled by this blueprint:** the missing activity join key (§2.2); no defined pattern for cross-module references across build order (§2.3); no lineage rule for submitted reports (§2.4); mandated outputs never enumerated against their generators (§4); no user-facing surface making reporting obligations visible (§5); parked-module sessions unanchored to the spine (§6).

**Open (small, non-blocking):**
- Exact FOI report format/recipient practice for DOH bureaus — confirm at DMWIS requirements time.
- OPCR/DPCR/IPCR current form versions & rating formulas — the Drive's META DATA file is the seed; confirm at WFP session.
- Whether activity creation is open to all staff or Chiefs+Admin only (default: Chiefs+Admin create, everyone links).
- CSMR: confirm the bureau files one consolidated DOH report vs its own — affects only where the exporter's output goes.

---

## 10. Sources

- ARTA MC 2022-05 — harmonized CSM guidelines: [arta.gov.ph MC 2022-05](https://arta.gov.ph/wp-content/uploads/2022/09/MC-2022-05-GUIDELINES-ON-THE-IMPLEMENTATION-OF-THE-HARMONIZED-CLIENT-SATISFACTION-MEASUREMENT.pdf), [Annex B CSM Report Outline](https://arta.gov.ph/wp-content/uploads/2022/09/ARTA-MC-2022-05_Annex-B_CSM-Report-Outline.pdf)
- CSC SPMS (OPCR/DPCR/IPCR): [SPMS Guidebook (PAGBA)](https://www.pagba.com/wp-content/uploads/2015/07/SPMS-GUIDEBOOK.pdf), [CSC on SPMS](https://www.csc.gov.ph/assessing-performance-of-gov-t-workers-necessary-csc), [DOH-adopted SPMS guidelines example](https://armmc.doh.gov.ph/wp-content/uploads/2024/02/ARMMC_SPMS-Guidelines_Adoption-of-DOH-Guidelines.pdf)
- COA Circular 97-002 & EO 77 s. 2019 — carried from `Reimbursement_Module_Build_Spec_v1.md` §16
- Drive evidence base: 2026 Incoming/Outgoing workbooks, WFP2026, OPCR/DPCR/META DATA forms, 2025 BLHSD AR, 2025 IQA audit report, CY-2026 Calendar of Activities (per `Source_Grounding_and_Understanding.md`)

---

*This blueprint makes the plan's integration architecture explicit and proposes seven small amendments (§8). The Execution Plan remains the single source of truth; module specs govern their modules; where this blueprint assigns a link or generator, it is the authoritative map for cross-module work.*
