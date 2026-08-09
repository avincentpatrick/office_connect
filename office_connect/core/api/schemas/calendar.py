"""Calendar of Activities wire models (Stage D-2). api-standards §9k."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class CalendarEventOut(BaseModel):
    """One agenda row."""

    #: WHICH source produced this row — the registry key, ``<owner>.<thing>``.
    #: The page uses it for a source badge only; every human-readable string on
    #: the row is server-authored, so the client never maps a module's codes.
    source: str
    ref: str
    title: str
    #: A **Manila** calendar date — the agenda groups on it.
    date_start: date
    date_end: date | None = None
    detail: str | None = None
    status: str | None = None
    status_label: str | None = None
    #: ui-standards §2's semantic set, translated BY THE SOURCE.
    tone: str | None = None
    #: ``None`` | ``due_soon`` | ``overdue`` — server-computed for the same reason
    #: ``sla_state`` is: a browser with a wrong clock must not be able to tell
    #: somebody they still have time to liquidate.
    urgency: str | None = None
    href: str | None = None
    activity_id: int | None = None


class CalendarDayOut(BaseModel):
    """One agenda group. Only days that HAVE something are emitted."""

    date: date
    is_today: bool
    is_nonworking: bool
    nonworking_label: str | None = None
    events: list[CalendarEventOut]


class CalendarSourceOut(BaseModel):
    """What one contributor put on this page — and what it withheld.

    This block is **how a viewer is told about rows they cannot see**, and it
    carries a SENTENCE rather than a count. "3 more you cannot see" would tell a
    scoped officer how much travel a sibling division booked — a disclosure they
    could not have assembled by opening records one at a time, which is precisely
    what api-standards §9h forbids an aggregate to add. ``total`` below is the
    count of rows **this actor may see** before the cap (§9f), and discloses
    nothing about the rest.
    """

    key: str
    label: str
    #: Rows from this source on this page.
    count: int
    #: This source's window count BEFORE ``source_cap``.
    total: int
    bounded_note: str | None = None


class CalendarOut(BaseModel):
    days: list[CalendarDayOut]
    #: Events in the window before any cap (§9f) — the sum of ``sources[].total``.
    total: int
    start: date
    end: date
    #: The window ceiling the server applied, always stated: a bound the client
    #: cannot see is a bound the client will eventually contradict (§9g).
    window_max_days: int
    #: True when the caller asked for a wider window than they were given.
    window_clamped: bool
    source_cap: int
    #: One row per CONTRIBUTING source, key-sorted. A source whose feature flag is
    #: OFF is **absent** — an OFF module is indistinguishable from an absent one
    #: here too (api-standards §9 / §9k).
    sources: list[CalendarSourceOut]
    #: Manila today as the SERVER computed it, so the page's "Today" divider is
    #: the server's day and not the browser's.
    today: date


__all__ = [
    "CalendarDayOut",
    "CalendarEventOut",
    "CalendarOut",
    "CalendarSourceOut",
]
