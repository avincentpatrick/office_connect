# Module: Supply Management

## 1. Status

**NOT STARTED — added by owner 2026-07-22 (promoted from EXEC PLAN §22 "parked").
Wave slot: W2-B (post-pilot; order swappable with W2-C).** Prefix `supply_` ·
flag `module.supply` (fail-safe OFF).

## 2. Purpose

Government supply/property/inventory management per GAM for NGAs: the full
acquisition-to-disposal document chain, dual-card records, physical counts,
custodian accountability, and the COA compliance calendar that goes with them.

## 3. Source research (docs/research/)

- `round2/supply-property-management-gam.md` — GAM Vol II form chain with appendix
  numbers, COA 2022-004/2024-006 thresholds, COA 2020-006 counts, COA 89-296
  disposal, PD 1445 §73 loss/relief, COA 2009-001/2018-002 transmittals.
- `round2/uacs-prexc-coding-spine.md` — object codes (5-02-03 supplies group),
  ₱50 k classification branch.
- `round2/gap-critic-round2.md` — PhilGEPS evidence, year-end COA schedules.

## 4. Scope highlights (detailed at the module's R-0 session)

- **Form chain (GAM Vol II appendices, print-faithful):** PR (App 60) → PO (App 61;
  conforme date; **copy to COA within 5 working days**, tracked) → IAR (App 62;
  inspection and acceptance as two distinct sign-offs; partial deliveries;
  liquidated damages 1/10 of 1 %/day, rescission at 10 %) → issue via RIS (App 63,
  consumables) / **ICS (App 59, semi-expendable < ₱50 k)** / **PAR (App 71, PPE
  ≥ ₱50 k)** with 3-year renewal clocks; RSMI (App 64) bridges issuances to
  Accounting.
- **Dual-card discipline:** Stock/Property/Semi-expendable cards (Supply unit,
  quantities) vs Supplies Ledger Card / PPELC (Accounting, quantities + value) —
  separate record sets with reconciliation views; never merged.
- **Costing:** perpetual inventory, server-side moving-average on every receipt;
  issues post at current average (no client-side money math).
- **Classification:** ₱50,000-per-unit threshold as effective-dated config
  (COA 2022-004; semi-expendable journal logic checked against COA 2024-006);
  branch drives custody form, cards, and count-report membership.
- **Physical counts:** freeze-as-of-date count mode → RPCI + RPCSP (semestral,
  due Jan 31 / Jul 31) and RPCPPE (annual, due Jan 31) per COA 2020-006 (property
  numbering/tagging, found-at-station intake, shortage/overage computation,
  Inventory Committee + Head of Agency + COA signature workflow).
- **Disposal pipeline (never a single action):** declare unserviceable → IIRUP
  (App 74) / WMR (App 65) → appraisal → mode per COA 89-296 → COA witnessing →
  proceeds → derecognition **only** via the approved document (soft-delete rule
  extended: no disposed status without authorizing document FK).
- **Custody & accountability:** PTR (App 76) as the only custody-transfer
  mechanism; per-employee accountability ledger (active PARs/ICSs + total value —
  feeds clearance, bonding-adequacy checks); loss → RLSDDP with the **30-day
  PD 1445 §73 relief countdown** (item stays on the officer's balance until COA
  relief or restitution).
- **Compliance calendar entries:** counts (Jan 31/Jul 31), PIF → GSIS + COA by
  Apr 30 (COA 2018-002), PO→COA 5 WD, PAR/ICS renewals, year-end reconciliation
  schedules for the Feb 14 FS submission (PPE vs RPCPPE vs PPELC; inventory vs
  RPCI vs ledger cards).
- **Extras:** months-of-stock indicator (~3-month excessive-inventory watch),
  reorder points, PhilGEPS posting-evidence fields on PRs/POs (reference numbers
  as COA audit evidence — no API integration).

## 5. Integration obligations

- **PR gate:** every PR line references an approved APP line (RA 12009 IRR §7.8) —
  via the Planning & Budget module's interface; manual unvalidated APP-reference
  field until W2-A ships.
- Core services: workflow engine (every document's signatory chain), attachments,
  reference numbers (per form type + fund cluster + year), compliance calendar,
  template→PDF/XLSX generation, holiday calendar.
- Object codes from `core_object_codes` (5-02-03 supplies group, CO accounts).
- Custodians/org units from the staff directory; resource-adequacy flags feed the
  QMS Management Review input pack.

## 6. Open decisions

- `supply_*` table set at R-0 (working list in research digest §Recommendations).
- Fund-cluster scoping and whether the bureau transacts multiple clusters.
- Fidelity-bond tracking depth (thresholds, Treasury interface = manual records).
- Whether Accounting-side ledger cards are in-module or an export contract to the
  DOH accounting system (two-tier reality — confirm with FMS).

## 7. Plan

*(Filled at the module's R-0 requirements session; sequence per master-plan §2
W2-B.)*
