"""The calendar source registry — how one agenda reads many modules.

Master-plan §1.1 #17; the binding contract is `docs/standards/api-standards.md`
**§9k**. The Calendar of Activities shows `core_activities` (core), travel claims
and liquidation clocks (reimbursement), and — as later stages ship — room
bookings, document deadlines and SPMS dates. But the rule that decides *whose*
travel an actor may see (``oversight_scope``) lives inside the reimbursement
module, and the import-linter contracts forbid **both** ``core -> modules`` and
``module <-> module``. There is no import that reaches it, and there was never
meant to be.

So the calendar inverts. Core owns the value types and this registry; each module
implements a source in its own package, where its own scope rule is a plain local
import; and ``main.py`` — the composition root that already mounts module routers
for exactly this reason — registers them. Precedent:
``core/notifications/outbox.py::register_enqueuer``, whose docstring says the same
sentence about the Celery worker.

**This is not a workaround for the contracts — it is the shape they were
protecting.** A join written here would have hard-coded one module's org-placement
rule into the platform floor, and contributor number two would have had to match
it or fork it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime

#: Urgency vocabulary, borrowed verbatim from
#: ``modules/reimbursement/services/deadline.py`` rather than re-invented, so a
#: deadline means the same thing on the calendar as it does on the record it came
#: from. ``None`` = this row is not a deadline, or has no clock yet.
URGENCIES = frozenset({"due_soon", "overdue"})

#: ui-standards §2's semantic status set — green done / amber due / red blocked /
#: grey waiting. **A source translates its OWN vocabulary into this one**, which
#: is the whole reason the field exists: the calendar page must stay generic over
#: sources, and a page that mapped ``handed_to_fms`` to a colour would be a core
#: surface hard-coding a module's status codes — exactly the coupling §9k removes
#: from the backend, smuggled back in through the browser.
TONES = frozenset({"done", "warn", "blocked", "waiting"})


@dataclass(frozen=True, slots=True)
class CalendarEvent:
    """One agenda row. A VALUE — no ORM object ever crosses this boundary.

    Two fields are deliberately absent.

    ``kind`` would duplicate ``source``: one source produces one shape, and a
    source that needs two shapes registers twice. That keeps the census
    one-row-per-shape *and* one-row-per-scope-rule, which is the property that
    makes the census worth having.

    ``all_day`` would be ``True`` on every row this platform can currently
    produce, and a field nobody renders today is a field somebody renders next
    quarter (api-standards §9h). It arrives with timed room bookings, or not at
    all.
    """

    #: The registry key of the source that produced this row.
    source: str
    #: Stable identity *within* a source, e.g. ``"claim:88"``. Used for the merge
    #: tie-break, so ordering never depends on row order coming back from PG.
    ref: str
    title: str
    #: A **Manila** calendar date. The agenda groups on it, so it must already be
    #: local: grouping a UTC timestamp puts a 7 a.m. Manila event on the previous
    #: day for everybody.
    date_start: date
    #: Inclusive. ``None`` = a single-day event.
    date_end: date | None = None
    #: One muted line — venue, destination. Never a second sentence.
    detail: str | None = None
    #: The source's own machine code (``planned``, ``handed_to_fms``, …).
    status: str | None = None
    #: The **server's** display label. A calendar that maps codes to words
    #: client-side is a second status vocabulary to keep in step.
    status_label: str | None = None
    #: One of ``TONES`` — the source's own status, translated into the shared
    #: semantic set so the page never needs to know this source's vocabulary.
    tone: str | None = None
    #: ``None`` | ``"due_soon"`` | ``"overdue"`` — server-computed, for the same
    #: reason ``CountdownRing`` refuses to derive anything: a browser with a wrong
    #: clock must not be able to tell someone they still have time.
    urgency: str | None = None
    #: The FE route this row opens, or ``None`` for an inert row.
    href: str | None = None
    #: The spine join key (``core_activities.id``), when the row has one.
    activity_id: int | None = None


@dataclass(frozen=True, slots=True)
class SourceResult:
    """What one source contributed, and what it withheld."""

    events: Sequence[CalendarEvent]
    #: This source's count in the window **before** its own cap (§9f).
    total: int
    #: The server's own sentence about what this source is bounded by, *for this
    #: actor* — or ``None`` when nothing is withheld from them.
    #:
    #: **A sentence, never a count of hidden rows.** "3 more you cannot see"
    #: tells a division chief how much travel a sibling division booked, which is
    #: a disclosure they could not have assembled by opening records by hand —
    #: exactly what api-standards §9h forbids an aggregate to add. State the rule;
    #: never the residue.
    bounded_note: str | None = None
    #: True when the cap actually bit. Logged, and it makes "did we truncate?" a
    #: fact the dispatcher can report rather than infer from ``len(events)``.
    capped: bool = False


#: ``fetch(session, *, actor_user_id, start, end, cap, now) -> SourceResult``.
#: Keyword-only after the session so a signature change is a loud error at every
#: call site rather than a silently reordered positional.
Fetch = Callable[..., Awaitable[SourceResult]]


@dataclass(frozen=True, slots=True)
class CalendarSource:
    """A contributor to the agenda.

    A frozen dataclass, **not** a ``Protocol``. A protocol needing both
    ``__call__`` and ``key``/``label``/``feature_flag`` forces every
    implementation to be a class, or a function with attributes bolted on
    afterwards. A dataclass is *introspectable*, and that is precisely what makes
    ``tests/test_calendar_sources.py``'s census possible.
    """

    #: Registry key AND the wire value of ``CalendarEvent.source``. Namespaced
    #: ``<owner>.<thing>`` so keys cannot collide across modules and a reader can
    #: tell which module owns a row without a lookup table.
    key: str
    #: Human label for the envelope's ``sources[]`` block.
    label: str
    fetch: Fetch
    #: Feature flag that must be ON, or ``None`` for an always-on core source.
    #:
    #: The flag rides the SOURCE because a core route cannot carry
    #: ``require_feature("module.reimbursement")`` — core may not know the module
    #: exists. A flag-OFF source is **absent** from the response, never
    #: present-and-empty: an empty ``reimb.travel`` block would announce a module
    #: the tenant has not bought (api-standards §9 / §9k).
    feature_flag: str | None = None
    #: The NAME of the exact scope rule this source applies.
    #:
    #: ``register_source`` **refuses an empty one**, and that refusal is
    #: load-bearing: it makes the omission impossible at import time, before any
    #: test runs. R-9's census lesson in a third substrate — a source with no
    #: declared rule is how a calendar leaks, and *absence never fails a test
    #: unless you make it*.
    scope_rule: str = field(default="")


_SOURCES: dict[str, CalendarSource] = {}


def register_source(source: CalendarSource) -> None:
    """Install a calendar source. Called from the composition root (``main.py``).

    **Idempotent by construction, not by discipline:** the registry is a dict
    keyed on ``key``, so re-registering replaces rather than appends. The test
    suite imports ``office_connect.main`` from many modules, and a list would
    double every event the second time it was imported.

    **Order-independent by construction:** nothing reads insertion order —
    ``registered_sources()`` sorts by key, and the merge sorts on
    ``(date_start, source, ref)``.
    """
    if not source.key:
        raise ValueError("a calendar source must declare a non-empty `key`")
    if not source.scope_rule.strip():
        raise ValueError(
            f"calendar source {source.key!r} must declare a non-empty "
            "`scope_rule` — the name of the exact rule it applies. A source "
            "with no declared rule is how a calendar leaks (api-standards §9k)."
        )
    _SOURCES[source.key] = source


def registered_sources() -> tuple[CalendarSource, ...]:
    """Every registered source, **key-sorted**.

    Sorted for the same reason D-1 sorted ``/auth/me``'s permission codes: an
    order that depends on import order is non-deterministic as a function of *how
    the application was loaded* — stable on a dev box, arbitrary elsewhere, and
    impossible to snapshot-test.
    """
    return tuple(_SOURCES[key] for key in sorted(_SOURCES))


def clear_sources() -> None:
    """Empty the registry. **Test seam only** — never called by application code."""
    _SOURCES.clear()


__all__ = [
    "TONES",
    "URGENCIES",
    "CalendarEvent",
    "CalendarSource",
    "SourceResult",
    "clear_sources",
    "register_source",
    "registered_sources",
]
