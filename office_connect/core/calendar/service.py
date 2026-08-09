"""Window resolution + the source fan-out, merge and day grouping.

Every function here takes an injected ``now``/``today``. The router is the only
caller of ``utc_now()`` in the calendar, which is what makes a surface whose
entire subject is dates testable without a clock library (this repository has
none, by convention — services take the time, tests supply it).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.calendar.sources import (
    CalendarEvent,
    CalendarSource,
    SourceResult,
    registered_sources,
)
from office_connect.core.features import feature_enabled
from office_connect.core.time import to_manila
from office_connect.core.workdays import WEEKEND, load_nonworking_labels

log = logging.getLogger(__name__)

#: The window a caller gets when they ask for none.
DEFAULT_WINDOW_DAYS = 30
#: The ceiling. ~a quarter — long enough to plan against, short enough that the
#: per-source queries stay indexed range scans.
MAX_WINDOW_DAYS = 92
#: Per source, per window. Stated on the wire (§9g): a bound the client cannot see
#: is a bound the client will eventually contradict.
SOURCE_CAP = 200


@dataclass(frozen=True, slots=True)
class Window:
    start: date
    end: date
    #: True when ``end`` was pulled in to ``start + MAX_WINDOW_DAYS``. The caller
    #: asked a wider question than we answered, and must be told so.
    clamped: bool


@dataclass(frozen=True, slots=True)
class Day:
    day: date
    is_today: bool
    is_nonworking: bool
    nonworking_label: str | None
    events: tuple[CalendarEvent, ...]


@dataclass(frozen=True, slots=True)
class SourceReport:
    key: str
    label: str
    count: int
    total: int
    bounded_note: str | None


@dataclass(frozen=True, slots=True)
class Agenda:
    days: tuple[Day, ...]
    total: int
    window: Window
    sources: tuple[SourceReport, ...]
    today: date


class CalendarWindowError(ValueError):
    """``start`` is after ``end``. Raised, never silently swapped."""


def manila_today(now: datetime) -> date:
    """The server's Manila calendar day for ``now``."""
    return to_manila(now).date()


def resolve_window(
    *, start: date | None, end: date | None, now: datetime
) -> Window:
    """Fill in and bound the requested window.

    Defaults come from the **server's** Manila today, never a browser's idea of
    it: two people asking "what is on this week" from different timezones must
    get the same week.
    """
    first = start if start is not None else manila_today(now)
    last = end if end is not None else first + timedelta(days=DEFAULT_WINDOW_DAYS)
    if last < first:
        raise CalendarWindowError(
            "The start date must be on or before the end date."
        )
    ceiling = first + timedelta(days=MAX_WINDOW_DAYS)
    if last > ceiling:
        return Window(start=first, end=ceiling, clamped=True)
    return Window(start=first, end=last, clamped=False)


async def _usable_sources(
    session: AsyncSession, sources: Iterable[CalendarSource]
) -> list[CalendarSource]:
    """Drop sources whose feature flag is OFF.

    Dropped, not emptied: a flag-OFF module must be indistinguishable from a
    module that was never built (api-standards §9 / §9k), and an empty
    ``reimb.travel`` block on the wire announces a module the tenant has not
    bought.
    """
    usable: list[CalendarSource] = []
    for source in sources:
        if source.feature_flag is None:
            usable.append(source)
            continue
        if await feature_enabled(session, source.feature_flag):
            usable.append(source)
    return usable


def _sort_key(event: CalendarEvent) -> tuple[date, str, str]:
    # (date, source, ref) — total and stable. Never the DB's row order: two runs
    # of the same query may differ, and an agenda that reshuffles between
    # refreshes reads as data changing when nothing did.
    return (event.date_start, event.source, event.ref)


async def collect(
    session: AsyncSession,
    *,
    actor_user_id: int,
    window: Window,
    now: datetime,
    cap: int = SOURCE_CAP,
) -> Agenda:
    """Fan out to every registered source, merge, and group by day.

    A source that raises is **not** swallowed. A partial calendar that renders
    as a normal one is §9f's failure mode — a short list that looks complete is
    worse than a number — and this is a surface people plan against.
    """
    today = manila_today(now)
    reports: list[SourceReport] = []
    merged: list[CalendarEvent] = []

    for source in await _usable_sources(session, registered_sources()):
        result: SourceResult = await source.fetch(
            session,
            actor_user_id=actor_user_id,
            start=window.start,
            end=window.end,
            cap=cap,
            now=now,
        )
        events = list(result.events)
        if result.capped:
            log.warning(
                "calendar source %s hit its cap of %d in %s..%s "
                "(total %d) — the window is the paging control",
                source.key,
                cap,
                window.start,
                window.end,
                result.total,
            )
        merged.extend(events)
        reports.append(
            SourceReport(
                key=source.key,
                label=source.label,
                count=len(events),
                total=result.total,
                bounded_note=result.bounded_note,
            )
        )

    merged.sort(key=_sort_key)

    # ONE holiday load for the whole window, never one per row (rule 10's engine,
    # used the way it was built to be used).
    labels = await load_nonworking_labels(session, window.start, window.end)

    grouped: dict[date, list[CalendarEvent]] = {}
    for event in merged:
        grouped.setdefault(event.date_start, []).append(event)

    days = tuple(
        Day(
            day=day,
            is_today=day == today,
            # A weekend is non-working by arithmetic; a holiday is non-working by
            # a row, and only the row has a name.
            is_nonworking=day.weekday() in WEEKEND or day in labels,
            nonworking_label=labels.get(day),
            events=tuple(events),
        )
        # Days with nothing on them are OMITTED. An agenda is a list of days that
        # have something; 92 empty rows is a month grid wearing a list's markup,
        # and it gives a screen reader 92 headings with nothing under them.
        for day, events in sorted(grouped.items())
    )

    return Agenda(
        days=days,
        # The count BEFORE any cap (§9f), summed across contributors.
        total=sum(report.total for report in reports),
        window=window,
        sources=tuple(reports),
        today=today,
    )


__all__ = [
    "DEFAULT_WINDOW_DAYS",
    "MAX_WINDOW_DAYS",
    "SOURCE_CAP",
    "Agenda",
    "CalendarWindowError",
    "Day",
    "SourceReport",
    "Window",
    "collect",
    "manila_today",
    "resolve_window",
]
