# Module: QMS (Controlled Documents · Risk Registry · Management Review)

## 1. Status

**NOT STARTED — added by owner 2026-07-22. Stage slot: F (after DTWIS, before
CSS-IS convergence).** Prefix `qms_` · flag `module.qms` (fail-safe OFF).

## 2. Purpose

The bureau's ISO 9001:2015 instruments as one connected module (EO 605/GQMC makes
QMS certification a standing obligation tied to PBB):

- **Controlled Document Management** (owner feature): repository of controlled
  templates, issuances, guidelines, memos, and forms with version/revision history,
  effectivity dating, and **configurable view/download permissions**. Distinct from
  DTWIS, which *tracks correspondence*; this module *controls documents*.
- **Risk & Opportunity Registry** (ISO §6.1 / ISO 31000 / DBM NGICS).
- **Management Review** (ISO §9.3) — the bureau's MRR, with the input pack
  auto-assembled from other modules.
- **NC/CAPA register + internal-quality-audit program support** (ISO §10.2/§9.2).

## 3. Source research (docs/research/)

- `round2/iso-controlled-documents-qms.md` — ISO §7.5, EO 605/GQMC, DOH/DILG/COA
  document-control conventions, DCR workflow, NAP disposition.
- `round2/risk-registry-management-review.md` — §6.1/§9.3/§10.2, ISO 31000,
  NGICS/PGIAM, MR minutes format, PBB linkage.
- `round2/arta-csm-foi-nap-records.md` — GRDS 2023 retention, NAP Forms 1–3.

## 4. Scope highlights (from research; detailed at the module's R-0 session)

**Controlled documents** — 4-level hierarchy (QM → procedures → WIs/SOPs →
forms/templates); document codes `<OFFICE>-<TYPE>-<UNIT>-<SEQ>`; Rev. n from 0 +
effectivity date distinct from approval date (Approved→Effective flip is
time-triggered; exactly one effective revision per document, enforced by partial
unique index); **DCR-only mutations** (creation/revision/obsolescence) routed
originator → process owner → QMR → approver → document controller on the core
workflow engine; MASTER / CONTROLLED / UNCONTROLLED copy discipline — ad-hoc
downloads watermarked "UNCONTROLLED WHEN PRINTED OR DOWNLOADED" + downloader +
timestamp; controlled-copy issuance with copy numbers, distribution list, and
retrieval tasks on supersession; **download is a separate permission from view,
default deny, every download audit-logged**; live Master Lists (internal +
external documents) generated from the register; external-issuance register
(DOH AO/DO/DM/DC, COA/CSC/DBM circulars, `YYYY-NNNN` validation, superseded-by
chains); obsolete stamping + restricted access; periodic-review clocks
("reconfirmed without change" action); **documents vs records are distinct
lifecycles** (blank form = revisable document; accomplished form = immutable
record with GRDS retention).

**Risk registry** — versioned criteria matrices (3×3/4×4/5×5, tenant-configurable;
assessments pinned to criteria version); server-computed likelihood×impact with
band thresholds; top bands require treatment plan + owner + target date;
opportunities included (exploit/enhance); residual re-scoring + effectiveness
evaluation; review cadence engine; ICQ/controls export (NGICS component 2, PGIAM).

**Management review** — per-cycle record (default semestral); 9.3.2 input pack
auto-pulled: CSM scores (css), audit findings, process KPIs (dtwis/reimb), NC/CAPA
trends, risk-action effectiveness, resource flags, prior matrix of agreements;
inputs frozen as an immutable snapshot when marked conducted; 9.3.3 outputs typed
(improvement / QMS change / resource need) spawning tracked actions that carry into
the next cycle; "conducted" blocked until every input is populated or explicitly
N/A-with-reason.

## 5. Integration obligations

- Runs entirely on core services: workflow engine (DCR + MR approval), attachments
  + frozen snapshots (rendered PDFs with control blocks), document-type taxonomy,
  reference numbers (`RR-YYYY-NNNN` risks, DCR series), compliance calendar
  (review clocks, ISO surveillance), notifications.
- MR input pack reads css/dtwis/reimb/perf/supply via read-only interfaces — never
  direct imports.
- COA audit findings (perf module, W2-C) feed the risk registry and MR inputs.
- Stores all official platform templates (CSM questionnaire versions, FOI notices,
  NAP forms) so form updates are content changes, not deployments.
- Records-series rows link platform records to GRDS-2023 items; disposal generates
  NAP Form 3 and requires uploaded NAP written authority before status can change.

## 6. Open decisions

- `qms_*` table set finalized at R-0 (working list: qms_documents,
  qms_document_revisions, qms_change_requests, qms_external_documents,
  qms_distribution_copies, qms_records_series, qms_risks, qms_risk_assessments,
  qms_risk_actions, qms_risk_criteria_versions, qms_management_reviews + child
  tables, qms_nonconformities, qms_quality_objectives).
- Document Responsibility Matrix shape (type × unit → reviewer/endorser/approver).
- Confirm "MRR" = ISO 9.3 Management Review Report with the bureau (master plan §4 #6).
- Whether quality-objectives monitoring lives here or in Reports.

## 7. Plan

*(Filled at the module's R-0 requirements session; sequence per master-plan §2
Stage F.)*
