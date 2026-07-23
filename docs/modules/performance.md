# Module: Performance & Deliverables (SPMS · Accomplishments · COA Findings)

## 1. Status

**NOT STARTED — added by owner 2026-07-22. Wave slot: W2-C (depends on W2-A for
targets; order swappable with W2-B by bureau priority).** Prefix `perf_` ·
flag `module.performance` (fail-safe OFF).

## 2. Purpose

The bureau's performance-management and accountability deliverables: SPMS
(OPCR/DPCR/SPCR/IPCR + Forms 5–8), accomplishment reports, the PBB ranking feed,
and the COA audit-findings lifecycle (AOM/AAPSI/NS-ND-NC). Risk Registry and
Management Review live in the QMS module (master-plan §4 #9); this module feeds
them.

## 3. Source research (docs/research/)

- `round2/csc-spms-performance.md` — CSC MC 6 s.2012 + DOH DO 2019-0440 /
  DO 2023-0084: form structures, rating math, calendar, PMT, appeals,
  consequences.
- `round2/dbm-wfp-bed-bar-far.md` — BAR 1 feed, accomplishment-vs-target loop.
- `round2/gap-critic-round2.md` — PBB/AO 25 machinery, COA findings lifecycle,
  leave/DTR data contract, annual report.

## 4. Scope highlights (detailed at the module's R-0 session)

**SPMS cascade** — configurable tiers per tenant: OPCR → DPCR → (SPCR — a DOH form
for hospital sections; BLHSD default 3-tier) → IPCR, rendered as pixel-faithful
**DOH-SPMS Forms 1–8** (the printable, signature-complete PDF is the compliance
artifact; forms are QMS-controlled documents). Four-stage cycle as workflow states
(planning/commitment → monitoring/coaching → review/evaluation → rewarding/IDP)
with signature gates matching the forms: commitments signed **before** the period
(ratee → supervisor → head); assessment "discussed with" ratee acknowledgment;
final rating by Head of Office. No self-rating — supervisors rate on evidence.

**Rating engine (server-side, config-driven)** — Q/E/T applicability set at
target-setting; NULL-aware A-average; DOH percentage tempo (≥130 %=5 · 115–129=4 ·
100–114=3 · 51–99=2 · ≤50=1) and category weights (Strategic 40 / Core 50 /
Support 10; fallback 80/20) as effective-dated tenant config traceable to the
CSC-approved SPMS manual; all-or-nothing exception (met=5 / missed=2); written
justification required on any 5 or 2; DPCR accomplishment-rate column
(actual÷target×100) with anomaly warnings (>130 % under-targeting, >100 % on
universe denominators).

**Hard validations** — **MOV required per rated line ("no proof → not rated →
excluded from averages")**, MOVs as attachments or links to platform records;
individual/division ratings blocked until the office final assessment exists;
Summary List (Form 5) generation blocks/hard-warns when avg(individual finals) >
office rating; 90-day minimum rating period; detail/secondment/travel edge cases
per DO 2019-0440.

**Calendar & consequences** — DOH SPMS date ladder (Jan/Jul) seeded into the
compliance calendar (tenant-configurable, next-working-day rule); adverse-action
clocks as scheduled tasks: Unsatisfactory notice ≤30 days after semester end,
Poor preliminary rating ≤15 days after month 3, IDP required before closure;
two-consecutive-US / single-Poor flags for HR; non-submission flags
(PBB/promotion disqualification, supervisor liability).

**Committees & appeals** — PMT and PRAISE as committee entities with queues
(OPCR calibration, Outstanding-rating validation, appeals, top performers);
appeal windows: individual 10 calendar days → PMT decision 30 days; office rating
immutable after the annual review conference; separation appeals to CSC (15 days)
as external-case metadata.

**Accomplishments & feeds** — quarterly OPCR monitoring (Form 6) + coaching
journal (Form 7); accomplishment entries keyed to `core_activities` feed **BAR 1**
(W2-A) and the consolidated **Annual Report** (Government Outputs); PBB
delivery-unit ranking export per the annual AO 25 MC + per-year accountability
checklist.

**COA audit-findings lifecycle** — AOM register with management responses;
**AAPSI within 60 days of AAR receipt** + periodic status reporting; NS/ND/NC
records with 6-month appeal windows; findings feed the QMS Risk Registry and
Management Review inputs; all on the compliance calendar.

## 5. Integration obligations

- Targets/success indicators/allotted budget pulled from W2-A WFP/BED lines and
  `core_pap_codes` — never retyped.
- MOVs via core attachments; signature gates via the core workflow engine +
  frozen snapshots; forms via core PDF generation.
- Ratings API for step-increment ranking (CSC-DBM JC 1 s.2012) and PBB snapshots.
- Feeds QMS: findings → risk registry; performance/NC trends → MR input pack.
- Leave/DTR data contract (IPCR 90-day rule, calendar): owner and shape decided at
  R-0 (master-plan §4 #11) — the module consumes, never owns, attendance data.

## 6. Open decisions

- `perf_*` table set at R-0 (perf_commitments/perf_commitment_items/ratings/
  appeals/committees sketched in the research digest).
- Confirm BLHSD tier count and the bureau's PMT hierarchy/delegations.
- SPCR tier: enabled only for tenants that need it (hospital sections).
- Where the consolidated agency Annual Report generator lives (Reports vs here) —
  default: Reports/Government Outputs, this module supplies the data.

## 7. Plan

*(Filled at the module's R-0 requirements session; sequence per master-plan §2
W2-C.)*
