# Records Retention & Disposal Schedule

Per **NAP General Records Disposition Schedule (GRDS, 2023)** and COA rules.
**Soft delete is not records disposition** (database-standards §8): `deleted_at`
is a data-integrity flag; disposal follows retention law and is a deliberate,
authorized, **never automated** action.

## Retention classes (in code)
`office_connect/core/attachments/retention.py` defines `RETENTION_CLASSES`; each
attachment/record carries `retention_class`, `retention_starts_at`, and
`legal_hold`.

| Class | Meaning | Retention | Basis |
|---|---|---|---|
| `financial_dv_10y` | Disbursement-voucher supporting records | **10 years** from final settlement | GRDS 2023 / COA |
| `default` | General office record | 10 years | GRDS (conservative default) |
| `permanent` | Permanent record | indefinite (never disposal-eligible) | GRDS |
| `transitory` | Transitory / convenience copy | 3 years | GRDS |

## Rules
- **`retention_starts_at`** is the authoritative clock start (e.g. final
  settlement date). `retain_until` is *derived* (class + start), not stored.
- **`legal_hold = true`** blocks disposal unconditionally, regardless of the clock.
- **No automated purge, ever.** The platform produces a **disposal-eligibility
  report** (`attachments.disposal_eligibility_report`) listing records whose
  retention has elapsed and that are not on hold; a human authorizes disposal via
  the NAP process (Form 3 / records disposition), which is when — and the only
  time — physical bytes are removed. The row is kept (status change + audit), not
  hard-deleted.
- Soft-deleted records **still appear** in the disposal report (disposition is
  orthogonal to soft delete).

## Cadence & ownership
- The **Records Officer / DPO** owns this schedule.
- GRDS revisions and peso-threshold changes are refreshed **on revision** (the
  seed framework records this cadence).
