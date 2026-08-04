"""The liquidation deadline — pure, no I/O (the same shape as ``per_diem.py``).

COA Circular 97-002 gives a traveller **30 days after return to official station**
to liquidate a cash advance; past it, unliquidated advances may accrue 6% interest
and be deducted from salary. The clock therefore decides money, and it is the one
number every liquidation surface in the module renders (spec §6.2: *"the 30-day
countdown starts at ``cash_advance.date_return`` and shows on every liquidation
surface from CA creation"*).

**R-0 item 1, closed 2026-08-04 (session 21): CALENDAR days, with ``basis`` as a
live switch.** COA's text says "days" with no working-day qualifier, and the
research digest reads that as calendar days — so ``liquidation.deadline`` seeds
``{"days": 30, "basis": "calendar"}``. But the R-0 question was always whether DOH
*practice* counts working days, and that is a question about an agency, not about
the arithmetic. So the basis is read from config and honoured here: if the resident
COA auditor confirms working days, it becomes a config edit, not a code change plus
a data migration of every deadline in flight. The two-line ``working`` branch is the
entire cost of not having to guess.

Fail direction: an unreadable basis falls back to **calendar**, the shorter of the
two, and says so in the returned reason. This is the opposite of
``core/checklist/grammar.py``'s fail-OPEN for an unparseable rule, and deliberately
so — the asymmetry is the same one recorded in the module's delta register. A rule
that fails open produces a *visible flag* a reviewer can act on; a deadline that
failed open would quietly hand a traveller extra time they do not legally have, and
nobody would ever see it. Compliance clocks fail short.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Mapping

from office_connect.core.workdays import add_working_days

#: The config key holding ``{"days": n, "basis": "calendar" | "working"}``.
#:
#: Spec §5.3's example names ``liquidation.deadline_working_days``; that key has
#: never existed. The seeded key is this one, and it carries the basis as data
#: rather than baking an answer into the key's NAME — which is what made the
#: spec's key unable to express the calendar case at all.
DEADLINE_KEY = "liquidation.deadline"

CALENDAR = "calendar"
WORKING = "working"
BASES = frozenset({CALENDAR, WORKING})

#: COA Circular 97-002. Used when the config row is absent or unreadable.
DEFAULT_DAYS = 30
DEFAULT_BASIS = CALENDAR

#: Spec §6.3 — "Due Soon (≤ 7 days)". This is the clock that window was written
#: for; R-4-screens deferred it here rather than applying 7 days to a
#: 3-working-day approval SLA, where every item would be born amber.
DUE_SOON_DAYS = 7

ON_TRACK = "on_track"
DUE_SOON = "due_soon"
OVERDUE = "overdue"


@dataclass(frozen=True, slots=True)
class DeadlineRule:
    """The effective ``liquidation.deadline`` config, already validated."""

    days: int
    basis: str
    #: Why this rule is what it is — ``configured`` when the row was read
    #: cleanly, else the named fallback. Carried so a surface can say *"using
    #: the COA default"* instead of silently presenting a guess as a fact.
    reason: str = "configured"


def read_rule(config: Mapping[str, Any] | None) -> DeadlineRule:
    """Parse the effective config pack's ``liquidation.deadline`` value.

    Total: never raises. ``config`` is the whole effective pack (the mapping
    ``checklist_facts.effective_config`` returns), so callers pass what they
    already have rather than digging one key out at every call site.
    """
    value = (config or {}).get(DEADLINE_KEY)
    if not isinstance(value, Mapping):
        return DeadlineRule(DEFAULT_DAYS, DEFAULT_BASIS, "no_config_row")

    try:
        days = int(value["days"])
    except (KeyError, TypeError, ValueError):
        return DeadlineRule(DEFAULT_DAYS, DEFAULT_BASIS, "unreadable_days")
    if days <= 0:
        return DeadlineRule(DEFAULT_DAYS, DEFAULT_BASIS, "non_positive_days")

    basis = value.get("basis", DEFAULT_BASIS)
    if basis not in BASES:
        # Keep the CONFIGURED day count — only the basis was unreadable, and
        # discarding a legitimate "45" because someone typoed the basis would
        # be a second wrong answer on top of the first.
        return DeadlineRule(days, DEFAULT_BASIS, "unknown_basis")
    return DeadlineRule(days, basis)


def liquidation_deadline(
    *,
    date_return: date | None,
    rule: DeadlineRule,
    nonworking: frozenset[date] | set[date] | None = None,
) -> date | None:
    """The date a cash advance must be liquidated by, or ``None``.

    ``None`` when there is no return date — a trip that has not happened has no
    clock, and inventing one would put a countdown on a surface that should be
    showing "not started yet".

    ``nonworking`` is only consulted on the ``working`` basis; on ``calendar``
    the caller need not hit ``core_holidays`` at all, which is why the DB read
    is conditional in ``services/cash_advance.py``.
    """
    if date_return is None:
        return None
    if rule.basis == WORKING:
        return add_working_days(date_return, rule.days, nonworking or frozenset())
    return date_return + timedelta(days=rule.days)


def days_remaining(*, deadline: date | None, today: date) -> int | None:
    """Calendar days from ``today`` to ``deadline`` — negative once past.

    Always CALENDAR days, whatever the basis that produced the deadline: this
    is what a countdown ring shows a human, and "3 working days left" rendered
    beside a date three weekends away is a countdown nobody can read. The basis
    decides *when* the deadline falls; it does not change how long a day is.
    """
    if deadline is None:
        return None
    return (deadline - today).days


def deadline_state(*, deadline: date | None, today: date) -> str | None:
    """``on_track`` / ``due_soon`` / ``overdue`` (spec §6.3), or ``None``.

    Server-derived, never client-computed — the same rule as ``sla_state`` and
    for the same reason (delta register): a browser with a wrong clock, or in a
    non-Manila timezone, must not be able to tell a traveller they still have
    time. Money and deadlines are the server's to state.
    """
    remaining = days_remaining(deadline=deadline, today=today)
    if remaining is None:
        return None
    if remaining < 0:
        return OVERDUE
    if remaining <= DUE_SOON_DAYS:
        return DUE_SOON
    return ON_TRACK
