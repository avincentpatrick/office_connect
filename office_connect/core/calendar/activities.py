"""The ``core.activity`` calendar source — the spine itself.

`core_activities` is master-plan §1.2's connection spine: *"the answer to 'what
work was this for?'"*. This is the first surface that reads it.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.calendar.sources import (
    CalendarEvent,
    CalendarSource,
    SourceResult,
)
from office_connect.core.models import Activity

SOURCE_KEY = "core.activity"

#: ``core_activity_status`` -> ui-standards §2's semantic set. Owned here, beside
#: the vocabulary it translates, so the calendar page stays generic over sources.
_TONES: dict[str, str] = {
    "planned": "waiting",
    "ongoing": "warn",
    "done": "done",
    "cancelled": "blocked",
}
_LABELS: dict[str, str] = {
    "planned": "Planned",
    "ongoing": "Ongoing",
    "done": "Done",
    "cancelled": "Cancelled",
}


def _overlaps(start: date, end: date):
    """Rows whose span intersects ``[start, end]``.

    ``date_end`` is nullable and means "single day", so it is coalesced to
    ``date_start`` rather than treated as an open interval — an activity with no
    end date is one day long, not forever.
    """
    return (
        Activity.date_start <= end,
        func.coalesce(Activity.date_end, Activity.date_start) >= start,
    )


async def fetch_activities(
    session: AsyncSession,
    *,
    actor_user_id: int,
    start: date,
    end: date,
    cap: int,
    now: datetime,
) -> SourceResult:
    """Every live activity overlapping the window. **Tenant-wide, deliberately.**

    ``actor_user_id`` is accepted and unused: the signature is the registry's,
    and a source that ignores the actor should be visibly doing so rather than
    quietly having a different shape from its siblings.

    Soft-deleted rows are excluded automatically by the ``OCSession`` listener.
    """
    conditions = _overlaps(start, end)

    total = (
        await session.execute(
            select(func.count()).select_from(
                select(Activity.id).where(*conditions).subquery()
            )
        )
    ).scalar_one()

    rows = list(
        (
            await session.execute(
                select(Activity)
                .where(*conditions)
                # Ordered so truncation can only ever drop the LATEST rows in the
                # window, never rows from the middle (api-standards §9k).
                .order_by(Activity.date_start.asc(), Activity.id.asc())
                .limit(cap)
            )
        )
        .scalars()
        .all()
    )

    events = [
        CalendarEvent(
            source=SOURCE_KEY,
            ref=f"activity:{row.id}",
            title=row.title,
            date_start=row.date_start,
            date_end=row.date_end,
            detail=row.venue,
            status=row.status,
            status_label=_LABELS.get(row.status, row.status),
            tone=_TONES.get(row.status, "waiting"),
            # No detail screen exists for an activity, so the row is inert. A
            # link to nowhere is worse than no link.
            href=None,
            activity_id=row.id,
        )
        for row in rows
    ]
    # NOTE deliberately absent: `Activity.custom` (free JSONB) and `ppa_code`.
    # This surface is tenant-wide and `custom` is a field a tenant can put
    # anything into — including the thing decision 12 is about (calendar.md §6c).
    return SourceResult(
        events=events,
        total=total,
        bounded_note=None,  # nothing is withheld from anyone
        # Truncated iff the pre-cap count exceeds what we are returning. Stated
        # the same way in every source so the dispatcher's warning means one thing.
        capped=total > len(rows),
    )


ACTIVITY_SOURCE = CalendarSource(
    key=SOURCE_KEY,
    label="Activities",
    fetch=fetch_activities,
    feature_flag=None,  # a core surface, like /directory and /audit
    scope_rule=(
        "none — TENANT-WIDE by owner decision (calendar.md decision 12, "
        "2026-08-09). core_activities is the connection spine and carries no "
        "person data. division_id/section_id exist on the row and are "
        "deliberately NOT filtered on; `custom` never crosses the wire."
    ),
)

__all__ = ["ACTIVITY_SOURCE", "SOURCE_KEY", "fetch_activities"]
