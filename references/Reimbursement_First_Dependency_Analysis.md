# Office-Connect — Reimbursement-First (Local) Dependency Analysis & Handoff

**Companion to:** `OfficeConnect_Build_Execution_Plan_v1_0.docx` (v1.0, the single source of truth) and `Phased_Rollout_Assessment.md`
**Deepened by:** `Reimbursement_Module_Build_Spec_v1.md` — the end-to-end build specification (data model, status machine, work-management rules, checklist engine, UX/screens, computation, phases + QA). Where the spec is more specific than this handoff, the spec governs the module build.
**Status:** Locked handoff plan — pending the R-0 requirements session (below)
**Purpose:** Record the decision to make **Local Travel Reimbursement** the first module bureau staff use and test, and map its dependencies before any code is written. Grounded in the real DOH FMS source documents in the project Drive. This document does **not** change a locked decision in the execution plan; it sequences a new module on top of it. If any fact here conflicts with the execution plan, the execution plan governs.

---

## 1. Decision Record

The author redirected the first user-facing build away from the plan's "CSS-IS + DMWIS documents first" pilot (Q7) to a **Travel Reimbursement module**. Reimbursement is otherwise out of scope in the plan (named only in the grounding companion §3.6 as future FMS-family work). The following are locked this round:

| # | Decision | Value |
|---|---|---|
| 1 | **Scope** | **Local travel only** — local reimbursement + local cash-advance liquidation. Foreign travel is a parked follow-on (also sidesteps the missing foreign-liquidation checklist). |
| 2 | **Build approach** | **Standalone module** on the foundation floor, reconciled with DMWIS later (chosen over the shared-kernel-first option). |
| 3 | **Requirements gate** | **Yes** — a dedicated scoping session (R-0) before build, the way the plan gates WFP (Q6/§22). |
| 4 | **Pilot cohort** | **Finance/Admin unit + a few frequent travellers**, released behind a feature flag. |
| 5 | **Foundation floor** | Unchanged and non-negotiable: build Phases 0–2 + the DOH governance gate precede any user-facing feature. |

---

## 2. The Module's Purpose — Four Objectives (design north star)

Every design and build choice serves these four, in this priority order:

1. **Automate the documentary requirements.** Generate and assemble the required forms (Itinerary of Travel *Appendix A*, Certificate of Travel Completed *Appendix B*, Liquidation Report, JO/COS Certification) from claim data, so staff stop hand-building the packet.
2. **Check documents against the standard.** Validate every submission against the `FS-BD-01` checklist and rules; flag missing or non-compliant items **before** the claim moves up the approval chain. *This is the core value.*
3. **Learn from the usual comments.** Capture the recurring reviewer return-reasons, categorise them, and feed them back — so common rejections become automated pre-checks and inline guidance over time.
4. **Monitor progress.** Show where every reimbursement is in the pipeline (status, current holder, overdue), with dashboards and notifications.

---

## 3. What "Reimbursement" and "Cash-Advance Liquidation" Mean (shared spine)

Two mirror-image processes, one paperwork spine:

- **Reimbursement — "I paid, pay me back."** Staff spends their own money on an authorized local trip, then files a claim to be repaid. The disbursement voucher carries the note *"no cash advance for this travel."* No government money went out first.
- **Cash-advance liquidation — "You paid me first, now I account for it."** The office releases money before the trip; afterward staff must **liquidate** (prove where every peso went) and **settle**: refund the excess via a DOH Official Receipt, or be reimbursed the shortfall.

**Shared by both:** authorization up front (Travel Order/DPO + Itinerary *Appendix A*); proof of travel (*Appendix B*, Certificate of Appearance, boarding passes, tickets, terminal fee, receipts); an approval/signature chain (prepared by claimant → approved at least by Division Chief; liquidation certified by Claimant, Director IV, and Head of Accounting); and COA auditing rules throughout.

*Source basis (project Drive, `FS-BD-01` Rev. 6, June 2025): Reimbursement–Local (24 items), Liquidation–Local (28 items), plus the Appendix A/B, Liquidation Report, and JO-COS Certification templates and a per-receipt tracking sheet.*

---

## 4. Central Finding

Delivering the four objectives means **most of the workflow machinery is DMWIS-class and reused** (routing, signatures, deadlines, configurable types + Google-Docs templates), while the **genuinely net-new** work concentrates exactly where the objectives live: the **checklist-validation engine** (obj. 2), **template auto-assembly** (obj. 1), the **comment-learning loop** (obj. 3), and **progress monitoring** (obj. 4). Because the build is **standalone**, that machinery is built inside the module now and reconciled with DMWIS later (§7).

Reimbursement is therefore **not a thin module** — but with local-only scope and heavy reuse, it is a tractable first vertical on the floor.

---

## 5. Dependency Map (grounded, local-only)

### Tier 1 — Foundation floor (hard prerequisites; accepted)
- **Phase 0** — HF Docker Space + persistent-storage Postgres; deploy/backup with a proven restore; append-only hash-chained **audit** (§14.8); **UTC-store / Manila-display** timezone; **theming tokens** (§14.4); **feature-flag `/api/v1/config`** (§14.5); **pluggable reference-number strategy** (S-4); Google **Shared Drive** storage driver (S-5); email driver.
- **Phase 2** — **unified auth** (§14.1); **shared RBAC permission registry** (§14.2, §29); **shared Staff Directory** (§14.3); **NAV_GROUPS** navigation (§14.6).
- **`core_activity` mini-registry** — joins the floor per `Digital_Transformation_Integration_Blueprint.md` §2.2: the shared "what work was this for" join key that claims (and later surveys, bookings, documents, WFP lines) stamp via nullable `activity_id`. Minimal table, Phase-0-sized; the full WFP module remains parked.
- **Sequencing wrinkle.** Phase 2 auth + directory are *promoted from CSS-IS* (§14.3, C-3). Reimbursement needs staff and approvers in the directory, so a **directory-data slice of Phase 1 (CSS-IS → PostgreSQL) stays on the path**, even though the full CSS-IS feature migration and React refresh can be deferred. The alternative — building core auth/directory greenfield — forfeits a production-tested asset. **→ decide at R-0.**
- **Governance gate (§24 #6)** — DOH hosting clearance under the Data Privacy Act; binds harder here because claims carry **financial + personal data**. Real claims cannot be loaded until it closes.

### Tier 2 — DMWIS-class machinery reimbursement reuses (built standalone, reconciled later)

| Capability | Plan ref | Serves |
|---|---|---|
| Configurable record model + JSONB custom fields + admin field config | §19.5 | claim = configurable record |
| Controlled claim **types** + signatory config + **Google-Docs template link** | §19.7 | obj. 1 |
| **Routing / approval chain** + status model + status-transition authority | §19.3, §19.6, §29 | obj. 4 |
| **Two-dimensional state** (workflow status vs derived overdue badge) | §19.6 | obj. 4 |
| **Frozen-snapshot signatures** (export → PDF → SHA-256, manifest, re-sign flag, ordered signers) | §19.8 | approvals + A/B/C certifications |
| **Working-day deadline calc + Holiday Calendar** | §19.7 | obj. 4 (COA period, not ARTA) |
| File upload + **OCR** + Drive storage + auto-rename | §19.5 g7, §16, S-5 | obj. 2 (read + check uploads) |
| **Rule engine + feedback loop** ("every suggestion + override logged") | §19.7 | obj. 3 seed |
| Notifications (bell, WebSocket, polling fallback) | §14.8, §17.2 | obj. 4 |
| KPI / reports + download standard (WeasyPrint / openpyxl) | §19.9 | obj. 4 |
| Query-log privacy-preserving learning pattern | §14.7 | obj. 3 pattern |
| Admin config areas (types, fields, signatories, holiday calendar, rules) | §19.11 | all |

**Refinement from the source docs:** **ARTA deadline machinery is not needed** (no ARTA reference in any FMS document). What is needed is the working-day/Holiday-Calendar engine keyed to the **COA local liquidation period (~30 days; COA Circular 97-002 / 2016-011)** — which the checklists themselves **do not quote**, so the exact SLA is an **open item for R-0**.

### Tier 3 — Reimbursement-specific net-new (where the four objectives live)
- **Documentary-checklist + validation engine (obj. 2 — biggest net-new).** The 24-item (reimbursement) / 28-item (liquidation) local `FS-BD-01` checklists modelled as controlled, **submission-gating** rules, with the local conditional (**JO/COS** claimant → extra Head-of-Office certification per DM 2025-0202/-0202A). Validates completeness and correctness (e.g. economy-fare per EO 77; taxi receipt vs **CENRR ≤₱300 / RER >₱300–₱1,000** per COA Circular 2021-001) and blocks or flags before routing. DMWIS has no checklist-gating model.
- **Template auto-assembly (obj. 1).** Fill Appendix A (itinerary legs → transport allowance + per diem → totals), Appendix B, Liquidation Report, and JO/COS Certification from claim data via the Google-Docs template path (§19.7) → frozen PDF snapshot (§19.8).
- **Comment-learning loop (obj. 3).** A structured **return-reason / reviewer-comment taxonomy** captured on every rejection, built on the instructions/discussion log (§19.5 g8), the override-logging feedback loop (§19.7), and the privacy-preserving learning model (§14.7). Aggregate recurring comments → surface as inline guidance and, over time, promote the most common into automated pre-checks (feeding obj. 2).
- **Money model + settlement (supporting).** Itinerary totals; Actual vs Cash Advance; Amount to Reimburse / Refund; fund source **ORS (GF) / BUR (TF) / DV Box A**; JEV No.; the *"no cash advance"* note on reimbursement vouchers. Cash-advance → liquidation linkage (DV No./date; refund via DOH Official Receipt).
- **Multi-party certification blocks.** Liquidation Report **A = Claimant / B = Director IV / C = Head, Accounting Unit** — fixed certification roles over the reused signature engine.
- **New RBAC actors.** The FMS flow routes **Originating Office → Budget Division → Accounting Division (Head, Accounting Unit)** — added to the §29 registry beyond DMWIS's document roles.

### Tier 4 — External / organisational
DOH hosting clearance (financial-data emphasis); the R-0 requirements session; Finance/Admin pilot onboarding.

---

## 6. Build Sequence (standalone module, local-only, organised around the four objectives)

**Pre-flight:** Phase 0 → Phase 1 *(directory-data slice)* → Phase 2 → governance gate. Then the reimbursement module as a flag-gated vertical:

| Step | What it builds | Objective |
|---|---|---|
| **R-0 — Requirements session** | Lock fields; the checklist + local conditional rules; the Budget/Accounting approval chain; the A/B/C certification blocks; the **COA local liquidation SLA** (fills the source-doc gap); and the Phase-1-directory-slice vs greenfield-auth call. | gate |
| **R-1 — Claim model + local types + fields** | Record model; Local Reimbursement + Local Liquidation types; itinerary + money fields. | foundation |
| **R-2 — Approval chain + status + new roles** | Routing/assignment reused; Budget/Accounting roles into §29. | obj. 4 |
| **R-3 — Documentary-checklist + validation engine** | Submission-gating; JO/COS conditional; standards checks. | **obj. 2** |
| **R-4 — Template auto-assembly** | Appendix A/B, Liquidation Report, Certification → Google Docs → frozen PDF. | **obj. 1** |
| **R-5 — Money model + certifications + signatures** | Itinerary totals, actual-vs-CA, refund/top-up; A/B/C certs on frozen snapshots. | supporting |
| **R-6 — Cash-advance → liquidation + COA deadline** | CA linkage; working-day/holiday calc. | supporting + obj. 4 |
| **R-7 — Comment-learning loop** | Return-reason taxonomy → aggregation → guidance → promote to pre-checks. | **obj. 3** |
| **R-8 — Progress monitoring** | Dashboards, KPIs (turnaround, compliance rate), notifications, overdue pipeline. | **obj. 4** |
| **R-9 — Hardening → flag ON** | Security/resilience; enable for the Finance/Admin cohort → soak → widen. | release |

*Foreign travel is a parked follow-on module once local proves out.*

**Reconciliation-debt note (standalone accepted).** Build R-2 / R-5 / R-6 workflow logic as **module-internal services behind narrow interfaces** (a routing service, a signature service, a deadline service), not tangled into reimbursement UI — so the eventual DMWIS reconciliation is a re-pointing job, not a rewrite. This is the cheapest insurance against the divergence that "configurable, not customised" (§3.1) warns against.

---

## 7. Open Items Routed to R-0
- **COA local liquidation SLA** — the exact deadline is not written on the `FS-BD-01` checklists; confirm (~30 days) before wiring the deadline engine.
- **Phase-1 directory slice vs greenfield auth** — cheapest way to get staff/approvers into the shared directory without the full CSS-IS migration.
- **Return-reason taxonomy** — seed the initial comment categories from real reviewer history so obj. 3 has data on day one.
- **Budget/Accounting roles** — confirm the exact plantilla roles and who signs each certification block.

---

*Prepared as a locked handoff for the reimbursement-first (local) build. It sequences and depends; it does not supersede the Build Execution Plan.*
