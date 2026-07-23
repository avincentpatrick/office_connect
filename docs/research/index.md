# Research digests — index

Two deep-research rounds conducted 2026-07-22/23 (18 structured digests: key
practices with sources, pitfalls, recommendations). These are **internal working
digests**, not standards — where a digest conflicts with `docs/standards/`, the
standards win; where it corrects `references/`, the correction is recorded in the
consuming module doc's delta register (see `docs/master-plan.md` §MP-5).

> Verification note: claims cite public sources gathered by web research. Before a
> module's build phase freezes its rules, re-verify the load-bearing legal values
> (rates, deadlines, thresholds) against the official issuance text.

## Round 1 — engineering & platform practices (2026-07-22)

| File | Topic | Primary consumers |
|---|---|---|
| [ph-travel-reimbursement-rules.md](round1/ph-travel-reimbursement-rules.md) | EO 77 3-cluster DTE, COA 2012-001/2023-004 checklists, GAM App 32/44/45/46/47, COA 97-002 cash advances, DOH DO 2019-0225 | Reimbursement (Stage C) |
| [approval-workflow-engine-design.md](round1/approval-workflow-engine-design.md) | State-machine-as-data, versioned definitions, CAS + idempotency, delegation/OIC, SLA sweeps | Core workflow engine (Stage C, all modules) |
| [auth-rbac-onprem.md](round1/auth-rbac-onprem.md) | Redis sessions, NIST 800-63B-4, Argon2id, org-unit-scoped RBAC, AD/LDAP, CSRF, MFA | Identity & access (Stage B) |
| [modular-monolith-fastapi.md](round1/modular-monolith-fastapi.md) | Module skeleton, import-linter contracts, interfaces/events, flag gating, Alembic discipline | Foundation / all modules |
| [file-attachments-pdf-generation.md](round1/file-attachments-pdf-generation.md) | Upload pipeline, ClamAV offline, WeasyPrint, retention alignment, fail-closed serving | Core attachments (Stage A), all modules |
| [gov-ui-patterns.md](round1/gov-ui-patterns.md) | GOV.UK/USWDS/MOJ patterns, WCAG 2.2 AA, DICT MC 004-2017, RA 12254 | UI standards, R-2 shell, all screens |
| [onprem-windows-server-ops.md](round1/onprem-windows-server-ops.md) | Hyper-V Ubuntu VM substrate, backups/3-2-1, restore drills, HTTPS via AD CS/GPO, runbooks | Ops (Stage A), deployment |
| [dpa-retention-audit-compliance.md](round1/dpa-retention-audit-compliance.md) | RA 10173/NPC circulars, PIA/registration, GRDS 10-yr retention, RA 9470, COA auditor access, maker-checker | Compliance track (all stages) |
| [gap-critic-round1.md](round1/gap-critic-round1.md) | 15 missing areas (notifications, search, observability, training, e-signature, …) | Master plan cross-cutting tracks |

## Round 2 — PH government standards for modules (2026-07-23)

| File | Topic | Primary consumers |
|---|---|---|
| [csc-spms-performance.md](round2/csc-spms-performance.md) | CSC MC 6 s.2012 + DOH DO 2019-0440/2023-0084: OPCR/DPCR/SPCR/IPCR (Forms 1-8), rating engine, PMT, appeals, adverse-action clocks | Performance (W2-C) |
| [dbm-wfp-bed-bar-far.md](round2/dbm-wfp-bed-bar-far.md) | WFP 3-part structure, BED 1-4, BAR 1, FAR 1-6 (JC 2013-1/2014-1/2019-1), GAA cascade, MRR = ISO 9.3 | Planning & Budget (W2-A), Reports |
| [ppmp-app-procurement-ra12009.md](round2/ppmp-app-procurement-ra12009.md) | RA 12009 + 2025 IRR + GPPB Res 03-2025 forms: PPMP/APP/APP-CSE/PMR, modes, EPA, deadlines | Planning & Budget (W2-A) |
| [supply-property-management-gam.md](round2/supply-property-management-gam.md) | GAM Vol II form chain (PR/PO/IAR/RIS/ICS/PAR + counts + disposal), ₱50k threshold, perpetual inventory, PD 1445 §73 | Supply Management (W2-B) |
| [iso-controlled-documents-qms.md](round2/iso-controlled-documents-qms.md) | ISO 9001 §7.5, EO 605/GQMC, DCR workflow, watermarking, master lists, NAP RDS/Forms | QMS module (Stage F) |
| [risk-registry-management-review.md](round2/risk-registry-management-review.md) | ISO 9001 §6.1/§9.3/§10.2, ISO 31000, NGICS/PGIAM, MR input packs, NC/CAPA | QMS module (Stage F) |
| [arta-csm-foi-nap-records.md](round2/arta-csm-foi-nap-records.md) | ARTA MC 2022-05/2023-05 instrument + scoring + CSMR Annex B; FOI EO 2 s.2016 corrected clocks; RA 9470/NAP Forms 1-3, GRDS 2023 | CSS-IS (Stage G), DTWIS (Stage E) |
| [uacs-prexc-coding-spine.md](round2/uacs-prexc-coding-spine.md) | UACS segments, PREXC hierarchy, code lifecycle rules, object codes, GAD/CCET tags, DOH FY2025 tree | core_pap_codes / core_activity (Stage A), W2-A |
| [gap-critic-round2.md](round2/gap-critic-round2.md) | 20 missing areas (GAD JMC 2022-01, Transparency Seal, Citizen's Charter/CoC, PhilGEPS, APCPI, budget call, COA findings lifecycle, 8888, annual report, …) | Master plan Wave 2 + cross-cutting |
