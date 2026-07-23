# Module: DTWIS (Document Tracking & Workflow Information System)

> **Renamed from "DMWIS (Document Management & Workflow Information System)" by
> owner decision 2026-07-22** — this module *tracks* correspondence and its
> workflow; controlled document *management* is the separate QMS module
> (`docs/modules/qms.md`). References keep the old name (read-only); the rename
> and prefix change are recorded in the delta register below.

## 1. Status

**NOT STARTED — requirements/build sessions pending. Stage slot: E (old phases
4–7).** Prefix `dtwis_` · flag `module.dmwis` key retained until Stage E schema
lands (renaming the seeded flag key is part of this module's first migration).

## 2. Purpose

Full incoming/outgoing official-communications lifecycle (successor to the
16-column DTrak legacy sheet): logging (≤30 s), routing/assignment, status
tracking, FOI requests, 8888/complaint referrals, deadlines, signatures,
search, dashboards — grounded in 2,062 real 2026 documents. OCR (Tesseract) and
PDF export (WeasyPrint) system libs are pre-staged (commented) in the Dockerfile.

## 3. Source references & research

- `references/OfficeConnect_Build_Execution_Plan_v1_0.docx` §19 + Phases 4–7
- `references/Digital_Transformation_Integration_Blueprint.md` §3/§6
- `references/Source_Grounding_and_Understanding.md` (DTrak 16-column mapping)
- `docs/research/round2/arta-csm-foi-nap-records.md` (FOI corrected clocks, NAP)
- `docs/research/round1/approval-workflow-engine-design.md` (engine it consumes)

## 4. Delta register

| # | Reference says | Implementation | Why |
|---|---|---|---|
| 1 | Module name "DMWIS", prefix `dmwis_` | **DTWIS**, prefix `dtwis_` | Owner rename 2026-07-22 — avoid conflict with the QMS controlled-document module |
| 2 | FOI deadlines "3/15/30 days" | **15 working days + one ≤20-WD extension** (written notice before day 15), deemed denial on lapse; appeal **15 calendar days** → decision **30 WD** (EO 2 s.2016 practice) | Research correction — the "3" belongs to RA 11032's 3/7/20-WD transaction tiers, modeled as a separate SLA dimension |
| 3 | Builds own routing/status machinery (§19.3/19.6) | Runs on the **core workflow engine** (versioned definitions, parallel routing via `join_type`, delegation/OIC, CAS + idempotency) | Owner connectedness directive; Rule 10 |
| 4 | DMWIS-owned Contacts Directory (§19.5) | **`core_contacts`** shared registry (merged with CSS-IS resource persons) | Rule 10 — one external-contacts service |
| 5 | Document types + signatory config per module (§19.7) | Core document-type/signatory/template taxonomy | Rule 10 |
| 6 | (not in references) | **8888 hotline referrals** as a document type with a 72-hour clock (EO 6 s.2016); CCB/ARTA complaint referrals tracked | Gap-critic round 2 |
| 7 | (not in references) | **NAP records layer**: per-year incoming/outgoing control numbers, record-series links to **GRDS series of 2023**, NAP Forms 1/2/3 generation, disposal gated on uploaded NAP written authority (RA 9470) | Compliance research |
| 8 | Singular table names in spec | Pluralized per DB standards §2 | Standing rule 7 |

## 5. Integration obligations (Blueprint §3/§6 + master plan §1.3)

- Optional multi-tag `activity_id` on documents (spine).
- **FOI and DTrak registry exporters** (FOI-PMO quarterly template with identity
  masking + annual summary; communications registry replacing the Sheet).
- **DPO backfill task** that hardens reimbursement's `dpo_document_id` soft
  references (natural-key + nullable FK + idempotent backfill; ambiguities to a
  review queue) — Blueprint §2.3.
- Optional document ↔ meeting/booking soft-ref ("minutes of") — Stage H link.
- Tracked documents may cite QMS controlled-document codes (reference only).
- Turnaround KPIs feed the QMS Management Review input pack.
- RA 11032 3/7/20-WD tiers + ARTA three-deadline model on the core holiday
  calendar; Overdue is always a derived badge, never a status.

## 6. Open decisions

- `dtwis_*` table set (pluralized) at the Stage E requirements session.
- OCR scope and storage location for scanned documents (per the Stage A storage
  decision).
- Google Sheets sync + DTrak cutover mechanics (deferred to Stage I per master
  plan).

## 7. Plan

*(Filled at the module's requirements session; scope per master-plan §2 Stage E.)*
