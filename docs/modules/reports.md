# Module: Reports & Government Outputs

## 1. Status

**NOT STARTED. Phase slot: 9 (Report Factory surface); lineage convention is
Day-1 (Phase 0).**

## 2. Purpose

The Report Factory: one card per mandated government output (CSMR, FOI
registry, DTrak registry, OPCR/DPCR rollups, WFP/BED/BAR/FAR set, APP/PMR,
supply count reports, ISO evidence pack, Calendar of Activities, consolidated
**Annual Report**) with legal basis, deadline countdown (working-day aware,
fed by `core_compliance_deadlines` — master plan §3.4), source coverage %,
lineage-traceable Generate button, and the platform download standard (agency
header, period, generated-by, page numbers). Also owns the **Transparency
Seal posting pack** (per-period render set of BAR/FAR + APP + annual-report
items per GAA General Provisions) and **XLSX-first exports** for DBM/COA
matrix annexes (URS encoding needs Excel; PDF second).

## 3. Source references

- `references/Digital_Transformation_Integration_Blueprint.md` §2.4 (lineage),
  §4 (mandated outputs table), §5 (Government Outputs screen)

## 4. Integration obligations (Blueprint §2.4/§5)

- **Every generated report records lineage**: source filter + config version,
  archived with the output — the submission trail is QMS evidence.
- Deadlines use the holiday calendar (working-day aware).
- Query bar routes report intents here (with `landing.md`).
- The travel-spend-per-PPA query (Blueprint §4 row 6) becomes servable once
  claims carry `activity_id` from R-1 — "cost per activity per division".

## 5. Open decisions

- **Table prefix:** default per master plan §4 #7 — fold lineage into core
  (`core_report_lineages`); no `rpt_` tables until a real table need appears.
  Final registration in `database-standards.md` §2 at Stage H.
- CSMR: one consolidated DOH report vs bureau-own filing (affects exporter
  output destination only).
- Whether the consolidated Annual Report generator lives here (default) or in
  the performance module (which supplies the data).

## 6. Plan

*(Filled at the module's requirements session.)*
