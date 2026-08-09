"""The single working-day math engine — every deadline on the platform uses it.

Master-plan §1.1 #6: FOI, COA, ARTA, SPMS, liquidation, RA 11032 tiers all count
in *working days*, excluding weekends and the PH holiday / work-suspension
calendar. The math is kept **pure** (takes a ``nonworking`` set, no DB) so it is
trivially unit-testable; ``load_nonworking_dates`` is the thin DB-backed adapter
over ``core_holidays``.

Convention: ``weekday()`` gives Mon=0 … Sun=6, so weekends are ``{5, 6}``. A
``special_working`` holiday is informational and is *not* added to ``nonworking``
(offices are open); a weekend is always non-working (a special-working day that
lands on a weekend is not promoted — a documented Phase-0 simplification).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sqlalchemy.ext.asyncio import AsyncSession

WEEKEND = frozenset({5, 6})  # Saturday, Sunday

# core_holidays.holiday_type values the engine treats as non-working.
NON_WORKING_HOLIDAY_TYPES = frozenset(
    {"regular", "special_non_working", "work_suspension", "local"}
)


def is_working_day(day: date, nonworking: frozenset[date] | set[date]) -> bool:
    """True when ``day`` is a weekday and not in the ``nonworking`` set."""
    return day.weekday() not in WEEKEND and day not in nonworking


def next_working_day(day: date, nonworking: frozenset[date] | set[date]) -> date:
    """The first working day on or after ``day``."""
    cursor = day
    while not is_working_day(cursor, nonworking):
        cursor += timedelta(days=1)
    return cursor


def previous_working_day(day: date, nonworking: frozenset[date] | set[date]) -> date:
    """The first working day on or before ``day``."""
    cursor = day
    while not is_working_day(cursor, nonworking):
        cursor -= timedelta(days=1)
    return cursor


def add_working_days(
    start: date, n: int, nonworking: frozenset[date] | set[date]
) -> date:
    """The date that is ``n`` working days after ``start`` (``n<0`` counts back).

    ``n == 0`` returns ``start`` unchanged. For ``n > 0`` the count begins the
    day *after* ``start`` (so ``add_working_days(x, 1)`` is the next working day
    strictly after ``x``); ``working_days_between(x, add_working_days(x, n)) == n``.
    """
    if n == 0:
        return start
    step = 1 if n > 0 else -1
    remaining = abs(n)
    cursor = start
    while remaining:
        cursor += timedelta(days=step)
        if is_working_day(cursor, nonworking):
            remaining -= 1
    return cursor


def working_days_between(
    start: date, end: date, nonworking: frozenset[date] | set[date]
) -> int:
    """Count working days in the half-open interval ``(start, end]``.

    Positive when ``end > start``, negative when ``end < start``, ``0`` when
    equal. Pairs with :func:`add_working_days`.
    """
    if end == start:
        return 0
    lo, hi = (start, end) if end > start else (end, start)
    count = 0
    cursor = lo + timedelta(days=1)
    while cursor <= hi:
        if is_working_day(cursor, nonworking):
            count += 1
        cursor += timedelta(days=1)
    return count if end > start else -count


def adjust_to_working_day(
    day: date,
    nonworking: frozenset[date] | set[date],
    *,
    direction: str = "forward",
) -> date:
    """Roll a fixed calendar deadline onto a working day if it lands off one."""
    if direction == "backward":
        return previous_working_day(day, nonworking)
    return next_working_day(day, nonworking)


async def load_nonworking_dates(
    session: "AsyncSession", start: date, end: date
) -> set[date]:
    """Read active non-working ``core_holidays`` rows in ``[start, end]``.

    Kept import-local to avoid a module-load cycle (models import Base which
    imports time, etc.); the pure math above needs none of this.
    """
    from sqlalchemy import select

    from office_connect.core.models import Holiday

    result = await session.execute(
        select(Holiday.calendar_date).where(
            Holiday.calendar_date >= start,
            Holiday.calendar_date <= end,
            Holiday.is_active.is_(True),
            Holiday.holiday_type.in_(NON_WORKING_HOLIDAY_TYPES),
        )
    )
    return set(result.scalars())


async def load_nonworking_labels(
    session: "AsyncSession", start: date, end: date
) -> dict[date, str]:
    """``{calendar_date: name}`` for the same rows ``load_nonworking_dates`` returns.

    A calendar can say *"Araw ng Kagitingan"* where a deadline engine only needs
    to know the day does not count. Same filter, deliberately — a sibling here
    rather than a second holiday query in the calendar package, because
    ``core_holidays`` has exactly one reader (rule 10) and the day a
    ``special_working`` rule changes, both answers must move together.

    Weekends carry no label: they are non-working by arithmetic
    (``WEEKEND``), not by a row, so there is no name to give them.
    """
    from sqlalchemy import select

    from office_connect.core.models import Holiday

    result = await session.execute(
        select(Holiday.calendar_date, Holiday.name)
        .where(
            Holiday.calendar_date >= start,
            Holiday.calendar_date <= end,
            Holiday.is_active.is_(True),
            Holiday.holiday_type.in_(NON_WORKING_HOLIDAY_TYPES),
        )
        # Deterministic winner when two rows share a date (a national holiday and
        # a local suspension can coincide) — otherwise the label would depend on
        # PG's row order, which is the same non-determinism D-1's `sorted()` fixed.
        .order_by(Holiday.calendar_date, Holiday.name)
    )
    labels: dict[date, str] = {}
    for day, name in result.all():
        labels.setdefault(day, name)
    return labels
