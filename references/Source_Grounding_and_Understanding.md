# Office-Connect — Source Grounding & Understanding

**Companion to:** `OfficeConnect_Build_Execution_Plan_v1_0.docx` (v1.0, the single source of truth)
**Purpose:** Record how the real BLHSD/DOH source documents (held in the project Google Drive) ground the specific decisions in the Build Execution Plan, so the build agent can trace every convention back to real-world evidence rather than assumption.

This document does **not** change any decision in the execution plan. It is a traceability and orientation aid.

---

## 1. What Office-Connect Is (one paragraph)

Office-Connect is a **configurable, multi-tenant government workplace platform** — the coordination/visibility layer for a Philippine government bureau. **BLHSD** (Bureau of Local Health Systems Development, DOH) is the reference tenant and first build; any other agency gets its own isolated deployment via configuration alone. It is built by folding two retired documents into one plan:

- **CSS-IS** (Customer Satisfaction Survey Information System) — *already live in production* (FastAPI + Jinja2 + SQLite). Becomes **Module 1**; migrates SQLite→PostgreSQL and Jinja2→React.
- **DMWIS** (Document Management & Workflow Information System) — *greenfield*, specified to v5.4. Becomes **Module 2**; the full document lifecycle.

Plus **Module 3 (Admin:** rooms + announcements), **Module 4 (Reports & Analytics)**, a **universal landing page + query bar**, and a shared core (auth, RBAC, staff directory, theming, feature flags, audit, backups). Hosted on **Hugging Face Spaces** (single Docker Space, Postgres on persistent storage, files in Google Shared Drive, backups to a private HF Dataset). Built in **11 phases (0–10)** with per-phase QA and an early pilot at the end of Phase 7.

---

## 2. Source Document Inventory → Plan Mapping

The Drive folder holds the primary-source evidence base. Each folder grounds specific plan sections:

| Drive folder | Contents | Grounds these plan sections |
|---|---|---|
| **Operational Trackers** | `2026 INCOMING COMMUNICATIONS.xlsx`, `2026 OUTGOING COMMUNICATIONS.xlsx` | Module 2 data model (§19.1, §19.5); legacy column mapping (§28); the "2,062 documents" evidence base; DTrak numbering; routing defaults |
| **Reference Data** | `dpo2025-2434 BLHSD Updated.pdf` (org structure), `2025 BLHSD AR.pdf` (annual report), `BLHSD Audit Report from EB_IQA 2025.pdf` (ISO 9001 QMS audit) | Org structure & tenant config (§4, §13); DMWIS roles (§19.2); shared Staff Directory seed (§14.3); RBAC role assignments (§29); audit-trail / QMS expectations |
| **Process Documentation** | `12222015-2015-0284.PDF` + `do2015-0284-A.pdf` (issuance rules), reimbursement docs | Document types & hierarchy (§19.7); signatory rules; ARTA compliance; digital-signature & endorsement rules (§19.8); citation/APA requirements |
| **Templates & Forms** | DOH issuance letterhead/format templates (AO/DO/DPO/Joint), `Reimbursement/Liquidation/Foreign Travel` documentary requirements | Document-type templates & Google Docs template links (§19.7); signatory configuration; wet-signature flags; the "print without signatures" path |
| **Planning & Performance** | `WFP2026 BLHSD.xlsx`, `OPCR/DPCR/SPCR/META DATA` performance forms, `2025-2026 Bureau ROA.xlsx`, `CY-2026-BLHSD-CALENDAR-OF-ACTIVITIES.docx` | Parked **WFP module** (§22, Q6); Reports & Analytics KPIs (§21, §19.9); risk/opportunity (ROA); Admin announcements/calendar seed |

---

## 3. Key Grounding Facts (evidence → plan decision)

### 3.1 Organization & roles (from DPO 2025-2434)
The org structure the tenant config must model as **defaults, not hardcoded logic** (§4):

- **Office of the Director** — Dir. Mar Wynn D. Bello (Director IV). Signs "By Authority of the Secretary of Health."
- **HSDD** (Health Systems Development Division), Chief Dr. Kathrine Joyce Flores — **Section 1** (LHS Integration / HCPN), **Section 2** (Local Planning & Financing / LIPH-AOP-SHF), **Section 3** (Leadership & Governance).
- **HSMED** (Health Systems Monitoring & Evaluation Division), Chief Dr. Maria Lourdes Gajitos — **Section 4** (Equity in Health / BHW / PuroKalusugan / IP), **Section 5** (LGU Performance & Monitoring / SGLG).
- **Administrative Unit**, AO IV Alexander Medel.

This confirms the plan's **two-division / five-section** structure (§2.1) and the routing defaults **HSMED, HSDD, DIRECTOR, ADMIN, BOTH DIVISIONS** (§19.1).

**Named role designations that map directly onto DMWIS roles (§19.2) and RBAC (§29):**
- **Records Officer / Admin Staff** (primary loggers): the incoming/outgoing workbooks show **Eric (Delmendo), Jay-R, Nora (Sabello)** as receiving/encoding staff — matching the plan's "3 receiving staff handle all logging" insight (§19.1).
- **Ms. Arlina Tibig** — FOI Receiving Officer + DOH Records Management Committee → grounds the **FOI deadline model** (3/15/30 working days, §19.7) and Records Officer funnel.
- **Mr. Alexander Medel** — ARTA Point Person → grounds **ARTA complexity/deadline** presets (Simple 3d / Complex 7d / Highly Technical 20d, §19.7).
- **Mr. Ray Justin Ventura** — **Data Protection Officer** → grounds the **Data Privacy Act** governance gate (§24 #6) and privacy-preserving query log (§14.7, S-7).
- **Mr. Roland Javier** — CSS Focal Person; **Rustom Cañares, Gilbert Canoy** — CSS Data Encoders → grounds CSS-IS (Module 1) ownership.

### 3.2 Document types & hierarchy (from DO 2015-0284 + amendment 2015-0284-A)
Confirms the **controlled document-type dropdown** (§19.7). The seven-type DOH hierarchy: **AO → DO → DPO → DM → DC → MC → Memo**. The amendment adds three build-relevant rules:
- **Electronic endorsement** is legally equal to traditional endorsement; the DMAS Workflow module is the electronic-processing vehicle → validates DMWIS's digital routing/endorsement model.
- **Max 3 signatories** before the final signatory (RA 11032 / Ease of Doing Business) → constrains **signatory configuration** per document type (§19.7).
- **Digital signatures allowed & recognized** → directly grounds the **frozen-snapshot signature model** (§19.8).
- **Citation (APA) in annexes** → a document-type field/template consideration.

### 3.3 The 2,062-document evidence base (from the 2026 Communications workbooks)
The incoming/outgoing trackers are the literal source for **§19.1 real-world insights** and **§28 legacy column mapping**. Observed structure confirms the 16-column mapping:
`Date Received · DTrak No. · Originating Office · Type of Document · Subject · Receiving Staff · Forwarded To · Date of Director's Notation · Director's Note · Division/Unit · Date of Admin Response · Action Taken by Admin · Date Responded by PO · Action Taken by PO · Scanned Copy · Remarks`.
Real patterns visible in the data validate the design: short patterned Director notes ("Dr. Malou, FYA"), messy overlapping document types (drives the standardized dropdown), informal staff cycling in remarks (drives the formal Staff Queue), and the revision-tracking columns (drives version history).

### 3.4 ISO 9001 QMS context (from the 2025 IQA Audit Report)
BLHSD runs a **live ISO 9001:2015 Quality Management System** (MOPs, SOPs, WIs, WFP, PPMP, OPCR/DPCR/IPCR, ROA, RFA registry, Management Reviews). Commendations note: controlled document masterlist, real-time communications tracker, RFA registry, Management Reviews. **Implication:** the platform's **tamper-evident audit trail (§14.8, §17)**, controlled document lifecycle, and reporting standards must satisfy an existing QMS the bureau is already audited against — this is not greenfield process, it is digitizing an audited one.

### 3.5 WFP / performance forms (Planning & Performance folder)
`WFP2026` (PPAs, quarterly targets, budget line items, SAA sub-allotments), `OPCR/DPCR/SPCR` (cascading office→division→individual commitment & review), `META DATA 2026` (KPI formulas/rating scales), `ROA` (risk & opportunity). These ground:
- The **parked WFP module** (§22, Q6) — deliberately out of first build, needs its own requirements session. These files are its future input.
- **Reports & Analytics** KPI conventions (§21, §19.9) — the OPCR/metadata rating scales show the real KPI shape (efficiency/timeliness formulas, quarterly targets, baseline-first target-setting) the dashboards must eventually mirror.

### 3.6 Reimbursement / travel documentary requirements (Templates & Forms + Process Docs)
FMS documentary-requirement checklists (Local/Foreign Travel reimbursement & liquidation; Itinerary Appendix A, Certificate of Travel Completed Appendix B, Certificate of Appearance). These are **not in the first build** but confirm the *kind* of structured, checklist-driven, signatory-bound administrative process the platform will eventually absorb — reinforcing the "capture, don't log" and configurable-workflow principles (§3.1).

---

## 4. What This Confirms About the Plan

1. **The plan is well-grounded, not speculative.** Every major DMWIS design choice (roles, routing defaults, document types, the 30-second logging target, the 16-column legacy mapping, ARTA/FOI deadlines, signatory limits, digital-signature legality) traces to a specific real document in the Drive.
2. **BLHSD-specific facts must stay as configuration.** The org chart, section names, routing destinations, ARTA presets, document types, and signatory rules above are exactly the values the multi-tenant commitment (§4, §14.5) requires to live in **tenant config**, never in code.
3. **Governance gate is real and named.** A designated **Data Protection Officer** exists (R.J. Ventura) and the bureau operates under an audited QMS — the **DOH hosting clearance / Data Privacy Act** pre-flight gate (§24 #6) is a genuine institutional requirement, not a formality.

---

## 5. Open Items Carried From the Plan (unchanged)

- **DOH hosting clearance** (governance) — binding pre-flight gate; build may start, real official documents may not be loaded until it closes (§9, §24 #6).
- **HF hosting architecture** — least-proven part; multi-service-in-one-Docker-Space, persistent-storage Postgres, keep-alive, Dataset backups need durability pressure-testing (§5B).
- **WFP module** — deferred and unscoped; the Planning & Performance folder is its future input (§22).
- **Free-tier load realism** — Phase 10 load test must prove one free Space (2 vCPU) holds ~40 concurrent users (§5B, Phase 10).

---

*Prepared as an orientation/traceability companion to the Build Execution Plan. If any fact here conflicts with the execution plan, the execution plan governs.*
