# Module: Planning & Budget (WFP · BED/BAR/FAR · PPMP/APP)

## 1. Status

**NOT STARTED — added by owner 2026-07-22 (WFP promoted from EXEC PLAN §22/Q6;
PPMP new). Wave slot: W2-A (first Wave-2 module — W2-B and W2-C depend on it).**
Prefix `plan_` · flag `module.planning` (fail-safe OFF).

## 2. Purpose

The office's planning-to-accountability loop as one connected flow: WFP crafting →
BED generation → allotment/obligation/disbursement ledger → BAR/FAR reporting —
plus procurement planning (PPMP → APP → APP-CSE → PMR) under RA 12009, and GAD
plan/report attribution. Targets set here feed OPCR/DPCR (W2-C); APP lines gate
PRs (W2-B); actuals roll into the Government Outputs screen.

## 3. Source research (docs/research/)

- `round2/dbm-wfp-bed-bar-far.md` — DOH WFP structure (3 parts, HPDPB two-tier),
  BED 1–4, BAR 1, FAR 1–6 (COA-DBM JC 2013-1/2014-1/2019-1), GAA cascade
  (GAARD/SARO/NCA), signatory chains, transparency postings.
- `round2/ppmp-app-procurement-ra12009.md` — RA 12009 + 2025 IRR + GPPB Res
  03-2025 forms (12-column PPMP, APP variants, APP-CSE, PMR), modes/thresholds,
  EPA, market-scoping gate, deadlines.
- `round2/uacs-prexc-coding-spine.md` — PREXC/UACS coding, per-FY PAP trees,
  continuing appropriations, object codes.
- `round2/gap-critic-round2.md` — GAD JMC 2022-01/GMMS, budget call/BP forms/
  OSBPS, APCPI inputs.

## 4. Scope highlights (detailed at the module's R-0 session)

**WFP** — one per office per FY per the annual DOH WFP Manual (DM series): physical
plan (indicators + quarterly targets) + monthly obligation program + monthly
disbursement program; lines keyed to `core_pap_codes` (PREXC leaf) + allotment
class + `core_object_codes`; **server-side tie-outs on approval** (lines sum to
ceiling per PAP/class; cumulative disbursement ≤ obligation; every target row has
indicator + 4 quarters); approved versions immutable (realignments = adjustment
columns on a new version, never overwrites); two-tier flow: bureau → HPDPB
consolidation exports (direct-to-DBM BED/BAR/FAR annexes behind a tenant flag).

**Budget execution & accountability** — allotment releases (GAARD / SARO / GARO /
sub-allotment) + obligations (linked to WFP line and to source records —
reimbursement claims, POs) + disbursements as first-class events, so FAR 1's
appropriation→allotment→obligation→disbursement→balance columns are pure queries
and no obligation exceeds its allotment; BED 1–4 generated from the approved WFP
(XLSX matching DBM annex layouts for URS encoding — the URS remains the legal
submission channel; this module prepares and tracks); BAR 1 quarterly workflow
(frozen BED-2 targets → actuals → computed variance → **mandatory remarks on
deviation** → prepare → certify (Planning Officer) → approve); FAR 1/1-A/1-B/
(1-C)/2/2-A/3/4/5/6 applicability-flagged per fund cluster; budget-prep lifecycle
starts at the National Budget Call (BP forms, Tier 1/2, OSBPS), not at GAA
enactment; utilization + disbursement rate families computed server-side with the
physical-vs-financial mismatch flag (DBM catch-up-plan trigger).

**Procurement planning (RA 12009 + GPPB Res 03-2025 forms — mandatory since
21 Sep 2025)** — PPMP: 12-column official form; lot-level rows; MM/YYYY schedule
precision; by-administration items retained (mode = N/A); indicative→final
transition flips Estimated Budget → Authorized Budgetary Allocation; **submission
blocked without a Market Scoping Checklist attachment** (IRR §7.7.1(g)/§10);
version chain per PPMP number. APP: indicative / final / **updated (versioned,
complete record, computed diff → highlighted rows + bolded changed values in
exports)**; CSE items split to the **APP-CSE workbook → mPhilGEPS (~Aug 31 of the
prior year)** with summary-only totals in the main APP; Final APP HoPE-approved by
**end of January** + website posting + Certificate of Posting; PMR semestral;
modes (11) + negotiated instances (13) + thresholds (SVP ₱2,000,000; Direct
Acquisition ₱200,000) as effective-dated lookups; EPA flags with award-blocking
guards until funding effectivity; per-record `procurement_regime`
(RA_12009 | RA_9184_transitional, IRR §113); exports as .xls/.xlsx + signed .pdf
per GPPB/mPhilGEPS file rules (both channels are manual portals — track submission
evidence, no API).

**GAD** — GAD Plan & Budget (≥5 % attribution, HGDG scores per attributed
activity) + GAD Accomplishment Report each January per PCW-DBM-NEDA JMC 2022-01,
via GMMS (tracked as submission evidence); GAD attribution via `core_activity_tags`.

**APCPI** — accumulate the indicator inputs (lead times, failed-bidding rates,
APP-vs-actual variance, PMR timeliness) so the self-assessment is a report; the
FY2025 tool is suspended pending an NGPA update (GPPB Advisory 04-2026).

## 5. Integration obligations

- Keys everything to `core_pap_codes` (per-FY, year-rollover wizard) +
  `core_object_codes` + `core_activities` (WFP activity grain is finer than GAA
  PAP lines — many-to-one roll-up).
- OPCR/DPCR (W2-C) pull targets/budget lines from here — never retyped.
- Supply PRs (W2-B) validate against approved APP lines via this module's
  interface.
- Reimbursement obligations (object code 5-02-01-010-00) feed utilization.
- Compliance calendar: BEDs mid-Nov (per-year override), BAR/FAR set quarterly,
  FAR 4 monthly, FAR 3 annual, APP end-Jan/end-Jul, APP-CSE ~Aug 31, PMR
  semestral, GAD-AR Jan; transparency-seal render pack per closed period.

## 6. Open decisions

- `plan_*` table set at R-0 (schemas sketched in the research digests).
- Confirm the bureau's fund clusters and whether FAR 2/2-A/5/6 apply.
- DOH online WFP system export shape (get the current DM/manual at R-0).
- CSE catalogue reference-data source and refresh cadence (PS-DBM template).
- Whether budget-prep (BP forms/OSBPS) is in the first slice or a fast-follow.

## 7. Plan

*(Filled at the module's R-0 requirements session; sequence per master-plan §2
W2-A.)*
