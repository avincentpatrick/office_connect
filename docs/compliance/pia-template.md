# Privacy Impact Assessment (PIA) — Template

Per **NPC Advisory 2017-03**. Complete one PIA **per module** before that module
processes real personal data in ANY environment (the per-module governance gate,
master-plan §3.1). File the completed PIA alongside the module doc.

> **Module:** _____   **PIC/PIP:** BLHSD / DOH (reference tenant)
> **Assessor:** _____   **Date:** _____   **Version:** _____

## 1. Description of the processing
- Purpose(s) of processing and lawful basis (RA 10173 §12/§13).
- Personal data / sensitive personal information (SPI) collected — list each field.
- Data subjects (employees, clients, suppliers, …).
- Data flow: collection → storage → use → disclosure → retention → disposal.
- Systems/actors involved (this platform + any integration).

## 2. Necessity & proportionality
- Is each field necessary for the stated purpose? Remove anything not needed.
- Retention period per field/record class (see `retention-schedule.md`).
- Disclosures / data sharing (recipients, basis, safeguards).

## 3. Risks to data subjects
| Risk | Likelihood | Impact | Existing control | Residual | Action |
|---|---|---|---|---|---|
| Unauthorized access | | | RBAC (Stage B) + least-privilege DB role | | |
| Excessive collection | | | field minimization | | |
| Loss of integrity | | | hash-chained audit + backups | | |
| Improper retention | | | retention schedule + legal_hold | | |
| Breach in transit/at rest | | | TLS at edge + encrypted volume | | |

## 4. Controls mapped to this platform
- **Access control**: least-privilege `oc_app` role (no DELETE); RBAC (Stage B).
- **Auditability**: hash-chained `core_audit_logs`; `verify_chain()`.
- **Attachments**: magic-byte allowlist, ClamAV, EXIF strip, auth-checked downloads.
- **Retention**: `retention_class` / `retention_starts_at` / `legal_hold`; no
  auto-purge; disposal-eligibility report.
- **SPI in logs**: excluded from the immutable audit payload.
- **Breach readiness**: `breach-runbook.md`.

## 5. Sign-off
- Residual risk acceptable? (Y/N + rationale)
- DPO / HoPE approval: _____   Date: _____
- Review date (re-assess on material change): _____
