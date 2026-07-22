# Module: DMWIS (Document Management & Workflow Information System)

## 1. Status

**NOT STARTED — requirements/build sessions pending. Phase slots: 4–7.**

## 2. Purpose

Document logging, routing, and workflow (successor to the 16-column DTrak
legacy sheet): incoming/outgoing registry, FOI requests, DPOs, QMS
document-lifecycle evidence. OCR (Tesseract) and PDF export (WeasyPrint)
system libs are pre-staged (commented) in the Dockerfile.

## 3. Source references

- `references/OfficeConnect_Build_Execution_Plan_v1_0.docx` Phases 4–7
- `references/Digital_Transformation_Integration_Blueprint.md` §3/§6
- `references/Source_Grounding_and_Understanding.md` (DTrak 16-column mapping)

## 4. Integration obligations (Blueprint §3/§6)

- Optional multi-tag `activity_id` on documents.
- **FOI and DTrak registry exporters** (list exports in mandated shapes).
- **DPO backfill task** that hardens reimbursement's soft references
  (natural-key text + nullable FK + idempotent backfill — Blueprint §2.3);
  ambiguities go to a review queue.
- Optional document ↔ meeting/booking soft-ref ("minutes of") — Phase 9 link.

## 5. Open decisions

- Table set under `dmwis_*` (pluralized per DB standards §2).
- OCR scope and storage location for scanned documents (Drive driver, S-5).

## 6. Plan

*(Filled at the module's requirements session.)*
