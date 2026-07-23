"""Records retention — NAP/GRDS. Report only; **no automated purge ever**.

Soft delete is a data-integrity mechanism, not records disposition (database-
standards §8). Government records follow retention law: a class maps to a
retention period; ``retain_until`` is *derived* from the class + the clock start;
``legal_hold`` blocks disposal unconditionally. The disposal-eligibility report
tells a human what is *eligible*; physical purge stays a manual, authorized action.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from office_connect.core.time import utc_now


@dataclass(frozen=True)
class RetentionRule:
    label: str
    years: int | None  # None = indefinite → never disposal-eligible


# GRDS 2023: DV-supporting records = 10 years from final settlement.
RETENTION_CLASSES: dict[str, RetentionRule] = {
    "default": RetentionRule("General office record", years=10),
    "financial_dv_10y": RetentionRule("Disbursement-voucher support (GRDS)", years=10),
    "permanent": RetentionRule("Permanent record", years=None),
    "transitory": RetentionRule("Transitory/convenience copy", years=3),
}


def retain_until(
    retention_class: str, retention_starts_at: datetime | None
) -> datetime | None:
    """The date on/after which a record may be disposed, or None if it never can.

    None when: the clock has not started, the class is indefinite/permanent, or
    the class is unknown (fail-safe → treated as never-eligible).
    """
    if retention_starts_at is None:
        return None
    rule = RETENTION_CLASSES.get(retention_class)
    if rule is None or rule.years is None:
        return None
    return retention_starts_at + timedelta(days=365 * rule.years)


@dataclass(frozen=True)
class DisposalCandidate:
    attachment_id: int
    sha256: str
    retention_class: str
    retention_starts_at: datetime | None
    retain_until: datetime | None
    legal_hold: bool
    eligible: bool
    reason: str


def evaluate_candidate(row, *, as_of: datetime | None = None) -> DisposalCandidate:
    """Compute one attachment's disposal eligibility. Never mutates or deletes."""
    as_of = as_of or utc_now()
    until = retain_until(row.retention_class, row.retention_starts_at)
    if row.disposed_at is not None:
        eligible, reason = False, "already disposed"
    elif row.legal_hold:
        eligible, reason = False, "legal hold"
    elif until is None:
        eligible, reason = False, "retention clock not started or indefinite"
    elif until > as_of:
        eligible, reason = False, f"retained until {until.date()}"
    else:
        eligible, reason = True, f"retention elapsed {until.date()}"
    return DisposalCandidate(
        attachment_id=row.id,
        sha256=row.sha256,
        retention_class=row.retention_class,
        retention_starts_at=row.retention_starts_at,
        retain_until=until,
        legal_hold=row.legal_hold,
        eligible=eligible,
        reason=reason,
    )
