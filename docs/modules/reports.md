# Module: Reports & Government Outputs

## 1. Status

**NOT STARTED. Phase slot: 9 (Report Factory surface); lineage convention is
Day-1 (Phase 0).**

## 2. Purpose

The Report Factory: one card per mandated government output (CSMR, FOI
registry, DTrak registry, OPCR/DPCR rollups, WFP financial accomplishment,
Calendar of Activities, Annual Report inputs) with legal basis, deadline
countdown (working-day aware), source coverage %, lineage-traceable Generate
button, and the platform download standard (agency header, period,
generated-by, page numbers).

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

- **Table prefix (user decision):** dedicated `rpt_` prefix vs folding lineage
  into core (`core_report_lineages`) — reports is mostly a consumer of other
  modules' data. Register the outcome in `database-standards.md` §2.
- CSMR: one consolidated DOH report vs bureau-own filing (affects exporter
  output destination only).

## 6. Plan

*(Filled at the module's requirements session.)*
