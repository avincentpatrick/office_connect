"""The ``auto_checks`` runners — core-service #7's second half (master-plan §1.1).

Pure and total, like ``grammar``. Spec §5.3 enumerates six check types; §2 calls
them "the engine of Objective 2" — *"every auto-checkable rule runs before a human
sees the claim; reviewers see a pre-checked packet."*

.. code-block:: json

    {"type": "file_present"}
    {"type": "amount_threshold", "field": "fare", "max_key": "receipts.cenrr_max",
     "on_exceed": "require_item:RER"}
    {"type": "date_within_trip"}
    {"type": "sum_matches", "of": "legs.fare", "vs": "totals.transport", "tolerance": 0}
    {"type": "keyword_absent", "keywords": ["business class"], "source": "ocr",
     "flag": "fare.class"}
    {"type": "deadline_check", "key": "liquidation.deadline_working_days"}

**A check NEVER blocks.** Spec §5.3: *"Auto-checks set auto_passed / auto_flagged —
a flag never blocks alone; it surfaces to the reviewer with the reason."* That is
why an unknown check type yields ``skipped`` rather than the fail-closed treatment
``grammar`` gives an unknown rule operator: a rule decides whether a document is
*required* (a compliance fact), while a check only decides what to *tell* the
reviewer. Failing an unrecognized check closed would produce a flag nobody can
action — noise on the approval screen, not safety. The two asymmetries are one
decision, made in opposite directions for opposite reasons.

R-3 implements four types over data that exists today. ``keyword_absent`` needs OCR
text (R-9) and ``deadline_check`` needs the liquidation clock (R-6); both are
*registered and implemented*, returning ``skipped`` with a named reason when their
substrate is absent — so a catalog row using one is visibly inert rather than
silently passing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Mapping, Sequence

from office_connect.core.checklist import errors
from office_connect.core.checklist.grammar import (
    MISSING,
    Facts,
    _as_decimal,
    resolve_field,
)

CHECK_TYPES = frozenset(
    {
        "file_present",
        "amount_threshold",
        "date_within_trip",
        "sum_matches",
        "keyword_absent",
        "deadline_check",
    }
)

PASSED = "passed"
FLAGGED = "flagged"
SKIPPED = "skipped"


@dataclass(frozen=True)
class CheckResult:
    """One auto-check's verdict.

    ``reason`` is the machine slug a consumer branches on; ``message`` is the
    plain-language sentence a reviewer reads, and it must say what to do next
    (spec §9.1 principle 4 — "never block without a path"). ``remedy`` carries a
    catalog directive such as ``"require_item:RER"`` verbatim, for *display*.
    """

    type: str
    outcome: str
    reason: str
    message: str
    detail: Mapping[str, Any] = field(default_factory=dict)
    remedy: str | None = None

    @property
    def flagged(self) -> bool:
        return self.outcome == FLAGGED


def _skip(check_type: str, reason: str, message: str, **detail: Any) -> CheckResult:
    return CheckResult(
        type=check_type, outcome=SKIPPED, reason=reason, message=message, detail=detail
    )


# --------------------------------------------------------------------------
# Individual checks
# --------------------------------------------------------------------------


def _check_file_present(spec: Mapping[str, Any], facts: Facts) -> CheckResult:
    """Is there usable evidence on this item?

    The per-item overlay (``facts["item"]``) is assembled by the engine from the
    consumer's ``ItemState``. A ``pending`` scan **passes**: the file is stored
    and counted, and blocking a claimant because the virus scanner is behind
    would be a self-inflicted outage. An ``infected`` file flags — the bytes are
    quarantined, so the requirement is genuinely unmet.
    """
    item = facts.get("item")
    if not isinstance(item, Mapping):
        return _skip(
            "file_present",
            "no_item_context",
            "This item's attachments could not be read.",
        )

    infected = int(item.get("evidence_infected") or 0)
    usable = int(item.get("evidence_count") or 0)
    pending = int(item.get("evidence_pending") or 0)

    if infected:
        return CheckResult(
            type="file_present",
            outcome=FLAGGED,
            reason="evidence_infected",
            message=(
                f"{infected} uploaded file(s) failed the security check and were "
                "removed. Upload a different copy."
            ),
            detail={"infected": infected},
        )
    if usable == 0:
        return CheckResult(
            type="file_present",
            outcome=FLAGGED,
            reason="no_evidence",
            message="No file has been attached to this item yet.",
        )
    if pending:
        return CheckResult(
            type="file_present",
            outcome=PASSED,
            reason="evidence_scan_pending",
            message=(
                f"{pending} file(s) are still being checked for viruses. They are "
                "saved and count towards your packet."
            ),
            detail={"pending": pending, "usable": usable},
        )
    return CheckResult(
        type="file_present",
        outcome=PASSED,
        reason="evidence_present",
        message=f"{usable} file(s) attached.",
        detail={"usable": usable},
    )


def _config_amount(facts: Facts, max_key: Any) -> Decimal | None:
    """Resolve ``max_key`` to a money ceiling, or ``None``.

    Looked up **flat** in ``facts["config"]``, never by dotted path — config keys
    themselves contain dots (``receipts.cenrr_max``), so a dotted resolver would
    hunt for a nested ``receipts`` object that does not exist. A mapping value is
    unwrapped via ``["amount"]``, which is the shipped seed's shape
    (``{"amount": "300.00"}``); a bare scalar is taken as-is.
    """
    config = facts.get("config")
    if not isinstance(config, Mapping) or not isinstance(max_key, str):
        return None
    if max_key not in config:
        return None
    value = config[max_key]
    if isinstance(value, Mapping):
        value = value.get("amount", MISSING)
    return _as_decimal(value)


def _check_amount_threshold(spec: Mapping[str, Any], facts: Facts) -> CheckResult:
    """Flag when a claimed amount exceeds a config ceiling (e.g. the ₱300 CENRR limit).

    ``field`` may resolve to a scalar OR a list: there is no claim-level ``fare``,
    so ``facts["fare"]`` is per-leg and the check flags if ANY leg exceeds,
    naming the offenders in ``detail``.
    """
    max_key = spec.get("max_key")
    ceiling = _config_amount(facts, max_key)
    if ceiling is None:
        return _skip(
            "amount_threshold",
            "config_unavailable",
            f"The limit '{max_key}' is not configured, so this check did not run.",
            max_key=max_key,
        )

    raw = resolve_field(facts, spec.get("field", ""))
    values = (
        list(raw)
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes))
        else [raw]
    )
    amounts = [amount for amount in (_as_decimal(v) for v in values) if amount is not None]
    if not amounts:
        return _skip(
            "amount_threshold",
            "no_amount",
            "There is no amount to check yet.",
            field=spec.get("field"),
        )

    over = [amount for amount in amounts if amount > ceiling]
    remedy = spec.get("on_exceed") if isinstance(spec.get("on_exceed"), str) else None
    if not over:
        return CheckResult(
            type="amount_threshold",
            outcome=PASSED,
            reason="within_threshold",
            message=f"Every amount is within the ₱{ceiling} limit.",
            detail={"ceiling": str(ceiling), "max_seen": str(max(amounts))},
        )
    return CheckResult(
        type="amount_threshold",
        outcome=FLAGGED,
        reason="amount_over_threshold",
        message=(
            f"₱{max(over)} is over the ₱{ceiling} limit set by '{max_key}'. "
            "Attach the receipt the higher amount requires."
        ),
        detail={
            "ceiling": str(ceiling),
            "over": [str(amount) for amount in over],
            "max_key": max_key,
        },
        remedy=remedy,
    )


def _as_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _check_date_within_trip(spec: Mapping[str, Any], facts: Facts) -> CheckResult:
    """Do the claimed dates fall inside the trip window?

    Spec §5.3 says "receipt/leg dates inside depart..return". Receipt dates need
    OCR (R-9), so R-3 checks the dates that exist today: ``facts["evidence_dates"]``
    when populated, plus every itinerary leg date. That is real work now and
    widens for free when OCR lands.
    """
    trip = facts.get("trip")
    if not isinstance(trip, Mapping):
        return _skip("date_within_trip", "no_trip", "The trip dates are not set yet.")
    depart, ret = _as_date(trip.get("depart")), _as_date(trip.get("return"))
    if depart is None or ret is None:
        return _skip(
            "date_within_trip", "no_trip", "The trip dates are not set yet."
        )

    candidates: list[tuple[str, date]] = []
    legs = facts.get("legs")
    if isinstance(legs, Sequence) and not isinstance(legs, (str, bytes)):
        for leg in legs:
            if not isinstance(leg, Mapping):
                continue
            leg_date = _as_date(leg.get("leg_date"))
            if leg_date is not None:
                candidates.append((f"leg {leg.get('seq', '?')}", leg_date))
    evidence_dates = facts.get("evidence_dates")
    if isinstance(evidence_dates, Sequence) and not isinstance(
        evidence_dates, (str, bytes)
    ):
        for raw in evidence_dates:
            parsed = _as_date(raw)
            if parsed is not None:
                candidates.append(("receipt", parsed))

    if not candidates:
        return _skip(
            "date_within_trip", "no_dates", "There are no dates to check yet."
        )

    outside = [
        (label, value) for label, value in candidates if not depart <= value <= ret
    ]
    if not outside:
        return CheckResult(
            type="date_within_trip",
            outcome=PASSED,
            reason="dates_within_trip",
            message=(
                f"Every date falls between {depart.isoformat()} and {ret.isoformat()}."
            ),
        )
    listed = ", ".join(f"{label} ({value.isoformat()})" for label, value in outside)
    return CheckResult(
        type="date_within_trip",
        outcome=FLAGGED,
        reason="date_outside_trip",
        message=(
            f"{listed} falls outside the trip dates "
            f"({depart.isoformat()} to {ret.isoformat()}). Fix the dates, or "
            "explain the difference to your approver."
        ),
        detail={"outside": [value.isoformat() for _, value in outside]},
    )


def _check_sum_matches(spec: Mapping[str, Any], facts: Facts) -> CheckResult:
    """Does a list of amounts add up to a stated total, within tolerance?"""
    raw_of = resolve_field(facts, spec.get("of", ""))
    values = (
        list(raw_of)
        if isinstance(raw_of, Sequence) and not isinstance(raw_of, (str, bytes))
        else [raw_of]
    )
    parts = [amount for amount in (_as_decimal(v) for v in values) if amount is not None]
    total = _as_decimal(resolve_field(facts, spec.get("vs", "")))
    if total is None:
        return _skip(
            "sum_matches",
            "no_total",
            "The total to compare against has not been computed yet.",
            vs=spec.get("vs"),
        )

    tolerance = _as_decimal(spec.get("tolerance", 0)) or Decimal("0")
    summed = sum(parts, Decimal("0"))
    delta = abs(summed - total)
    if delta <= tolerance:
        return CheckResult(
            type="sum_matches",
            outcome=PASSED,
            reason="sum_matches",
            message=f"The parts add up to ₱{total}.",
            detail={"sum": str(summed), "total": str(total)},
        )
    return CheckResult(
        type="sum_matches",
        outcome=FLAGGED,
        reason="sum_mismatch",
        message=(
            f"The parts add up to ₱{summed} but the total says ₱{total} "
            f"(a difference of ₱{delta}). Check the amounts."
        ),
        detail={"sum": str(summed), "total": str(total), "delta": str(delta)},
    )


def _check_keyword_absent(spec: Mapping[str, Any], facts: Facts) -> CheckResult:
    """Flag forbidden wording (e.g. "business class") in scanned document text.

    Implemented, but inert until OCR ships (R-9): with no ``ocr_text`` the honest
    answer is "not checked", never "passed".
    """
    text = facts.get("ocr_text")
    if not isinstance(text, str) or not text.strip():
        return _skip(
            "keyword_absent",
            "ocr_unavailable",
            "This document's text has not been read yet, so this check did not run.",
            flag=spec.get("flag"),
        )

    keywords = spec.get("keywords")
    if not isinstance(keywords, Sequence) or isinstance(keywords, (str, bytes)):
        return _skip(
            "keyword_absent", "no_keywords", "No keywords are configured to look for."
        )

    haystack = text.lower()
    hits = [
        keyword
        for keyword in keywords
        if isinstance(keyword, str) and keyword.lower() in haystack
    ]
    if not hits:
        return CheckResult(
            type="keyword_absent",
            outcome=PASSED,
            reason="keywords_absent",
            message="None of the flagged wording appears in this document.",
        )
    return CheckResult(
        type="keyword_absent",
        outcome=FLAGGED,
        reason="keyword_found",
        message=(
            f"This document mentions {', '.join(repr(hit) for hit in hits)}. "
            "Above-economy fare needs a Head-of-Agency certification."
        ),
        detail={"hits": hits, "flag": spec.get("flag")},
    )


def _check_deadline_check(spec: Mapping[str, Any], facts: Facts) -> CheckResult:
    """Flag a passed statutory deadline. Inert until the liquidation clock ships (R-6).

    Note the spec's example key (``liquidation.deadline_working_days``) does not
    exist in the config pack — the seeded key is ``liquidation.deadline``, and
    whether it counts calendar or working days is still an open R-0 item. Do not
    seed a ``deadline_check`` until R-6 resolves that.
    """
    key = spec.get("key")
    deadlines = facts.get("deadlines")
    due = _as_date(deadlines.get(key)) if isinstance(deadlines, Mapping) else None
    if due is None:
        return _skip(
            "deadline_check",
            "deadline_clock_unavailable",
            f"The '{key}' deadline is not tracked yet, so this check did not run.",
            key=key,
        )

    today = _as_date(facts.get("today"))
    if today is None:
        return _skip("deadline_check", "no_today", "This check did not run.", key=key)
    if today <= due:
        return CheckResult(
            type="deadline_check",
            outcome=PASSED,
            reason="within_deadline",
            message=f"Still within the {due.isoformat()} deadline.",
        )
    return CheckResult(
        type="deadline_check",
        outcome=FLAGGED,
        reason="deadline_passed",
        message=(
            f"The {due.isoformat()} deadline has passed ({(today - due).days} days "
            "ago). Explain the delay to your approver."
        ),
        detail={"due": due.isoformat(), "days_late": (today - due).days},
    )


_RUNNERS = {
    "file_present": _check_file_present,
    "amount_threshold": _check_amount_threshold,
    "date_within_trip": _check_date_within_trip,
    "sum_matches": _check_sum_matches,
    "keyword_absent": _check_keyword_absent,
    "deadline_check": _check_deadline_check,
}


# --------------------------------------------------------------------------
# Public surface
# --------------------------------------------------------------------------


def run_auto_checks(checks: Any, facts: Facts) -> tuple[CheckResult, ...]:
    """Run every check in ``checks``. Never raises; an unrunnable check is ``skipped``."""
    if not isinstance(checks, Sequence) or isinstance(checks, (str, bytes)):
        return ()

    results: list[CheckResult] = []
    for spec in checks:
        if not isinstance(spec, Mapping):
            results.append(
                _skip("unknown", "malformed_check", "This check could not be read.")
            )
            continue
        check_type = spec.get("type")
        runner = _RUNNERS.get(check_type) if isinstance(check_type, str) else None
        if runner is None:
            results.append(
                _skip(
                    str(check_type),
                    "unknown_check_type",
                    "This automatic check is not available in this version.",
                )
            )
            continue
        results.append(runner(spec, facts))
    return tuple(results)


def checks_outcome(results: Sequence[CheckResult]) -> str:
    """Roll a set of results up: any flag wins, else any pass, else skipped."""
    if any(result.outcome == FLAGGED for result in results):
        return FLAGGED
    if any(result.outcome == PASSED for result in results):
        return PASSED
    return SKIPPED


def validate_auto_checks(checks: Any) -> None:
    """Raise unless ``checks`` is a well-formed list of known checks (authoring time)."""
    if checks is None:
        return
    if not isinstance(checks, Sequence) or isinstance(checks, (str, bytes)):
        raise errors.invalid_auto_check(
            f"expected a list, got {type(checks).__name__}"
        )
    for spec in checks:
        if not isinstance(spec, Mapping):
            raise errors.invalid_auto_check(
                f"expected an object, got {type(spec).__name__}"
            )
        check_type = spec.get("type")
        if not isinstance(check_type, str):
            raise errors.invalid_auto_check("every check needs a string 'type'")
        if check_type not in CHECK_TYPES:
            raise errors.unknown_check_type(check_type)
        for required_key in _REQUIRED_KEYS.get(check_type, ()):
            if required_key not in spec:
                raise errors.invalid_auto_check(
                    f"'{check_type}' needs a '{required_key}'"
                )


_REQUIRED_KEYS: Mapping[str, tuple[str, ...]] = {
    "amount_threshold": ("field", "max_key"),
    "sum_matches": ("of", "vs"),
    "keyword_absent": ("keywords",),
    "deadline_check": ("key",),
}
