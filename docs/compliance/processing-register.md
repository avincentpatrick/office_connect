# Records of Processing Activities (Processing Register)

Input to **NPC Data Processing System (DPS) registration** and the ongoing record
required of a Personal Information Controller (RA 10173; NPC Circular 2022-04
governs registration renewal — see the `npc_registration_renewal` compliance
deadline). One row per processing activity; keep current as modules ship.

| # | Processing activity | Module | Purpose & lawful basis | Data subjects | Personal data / SPI | Recipients / disclosures | Retention class | Safeguards |
|---|---|---|---|---|---|---|---|---|
| 1 | _(example)_ Local travel reimbursement | reimbursement | Process & liquidate travel claims (legal obligation / official function) | Employees | Name, position, itinerary, bank/GCash, DV support | COA, GSIS (as required) | `financial_dv_10y` | RBAC, audit chain, attachment scan, retention |
| 2 | Identity, directory & access management | foundation (identity/auth/RBAC) | Authenticate & authorize personnel; maintain the plantilla person directory modules join (legal obligation / public-authority function, RA 10173 §12(b)/(e)) | Employees / plantilla persons; login-account holders | Name, work email, position, plantilla item, employee no., employment status, org unit; login email, Argon2id hash, TOTP secret, auth flags; login-attempt metadata (no SPI category) | Internal (RBAC-gated); read-only auditor (COA Res. 2020-034); no external sharing | `default` (10y) | Least-privilege `oc_app` (no DELETE), RBAC, server-side sessions + MFA, hash-chained audit + verify_chain, person-field SPI redaction, privacy-preserving query log, TLS — PIA: `pia-stage-b-identity.md` |
| … | | | | | | | | |

## Maintenance
- Add a row when a module begins processing personal data (before real data — the
  PIA gate).
- Cross-reference each row's PIA and the module doc.
- Registration renewal is tracked as a statutory compliance deadline
  (`core_compliance_deadlines.code = 'npc_registration_renewal'`, annual, 30 days
  before expiry).
- The **DPO** owns this register.
