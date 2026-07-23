# Compliance (Data Privacy Act + records governance)

Scaffolds backing the compliance gates in `docs/master-plan.md` §3.1. These are
**templates and runbooks**, not filled records — the governance gate blocks
loading **real** personal data until the per-module PIA is done, but it does not
block the build.

| Document | What it is | Trigger |
|---|---|---|
| [`pia-template.md`](pia-template.md) | Privacy Impact Assessment template (NPC Advisory 2017-03) | completed **per module** before real personal data in ANY environment |
| [`processing-register.md`](processing-register.md) | Records of processing activities (NPC DPS registration input) | maintained continuously; updated per module |
| [`breach-runbook.md`](breach-runbook.md) | Personal-data-breach response (72-hour notify / 5-day report) | on any suspected breach |
| [`retention-schedule.md`](retention-schedule.md) | NAP/GRDS retention + disposal (no auto-purge) | per records class; drives the attachments disposal-eligibility report |

Key platform facts these rely on:
- **Hash-chained audit** (`core_audit_logs`) — every state change is attributable
  and tamper-evident (`verify_chain()`), and the "what did account X touch
  between T1–T2" query pack draws on it.
- **Soft delete ≠ disposition** — `deleted_at` is data integrity only; disposal
  follows retention law (database-standards §8).
- **No SPI in immutable logs** — the audit payload policy keeps sensitive values
  out of the hash-chained log (master-plan §3.1).
