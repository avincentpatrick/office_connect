# Records of Processing Activities (Processing Register)

Input to **NPC Data Processing System (DPS) registration** and the ongoing record
required of a Personal Information Controller (RA 10173; NPC Circular 2022-04
governs registration renewal — see the `npc_registration_renewal` compliance
deadline). One row per processing activity; keep current as modules ship.

| # | Processing activity | Module | Purpose & lawful basis | Data subjects | Personal data / SPI | Recipients / disclosures | Retention class | Safeguards |
|---|---|---|---|---|---|---|---|---|
| 1 | _(example)_ Local travel reimbursement | reimbursement | Process & liquidate travel claims (legal obligation / official function) | Employees | Name, position, itinerary, bank/GCash, DV support | COA, GSIS (as required) | `financial_dv_10y` | RBAC, audit chain, attachment scan, retention |
| … | | | | | | | | |

## Maintenance
- Add a row when a module begins processing personal data (before real data — the
  PIA gate).
- Cross-reference each row's PIA and the module doc.
- Registration renewal is tracked as a statutory compliance deadline
  (`core_compliance_deadlines.code = 'npc_registration_renewal'`, annual, 30 days
  before expiry).
- The **DPO** owns this register.
