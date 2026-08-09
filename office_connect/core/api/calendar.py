"""Calendar of Activities — the agenda endpoint (Stage D-2).

One surface, many contributors, none of which can import each other. The registry
that makes that possible is ``core/calendar/sources.py``; the binding contract is
`docs/standards/api-standards.md` **§9k**.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.api.errors import APIError
from office_connect.core.api.schemas.calendar import (
    CalendarDayOut,
    CalendarEventOut,
    CalendarOut,
    CalendarSourceOut,
)
from office_connect.core.auth.dependencies import require_permission
from office_connect.core.auth.principal import Principal
from office_connect.core.calendar import register_source
from office_connect.core.calendar.activities import ACTIVITY_SOURCE
from office_connect.core.calendar.service import (
    MAX_WINDOW_DAYS,
    SOURCE_CAP,
    Agenda,
    CalendarWindowError,
    collect,
    resolve_window,
)
from office_connect.core.db import get_session
from office_connect.core.time import utc_now

router = APIRouter()

# Core registers its OWN source here rather than in main.py: this is core
# registering into core's registry, which breaks no contract, and it keeps the
# composition root's job to the thing only it can do — wiring MODULES in.
register_source(ACTIVITY_SOURCE)

#: The permission. Three-part like ``rbac.role.read`` / ``workflow.instance.read``,
#: because the area will grow siblings: ``activity.read`` and ``activity.manage``
#: are RESERVED for a future registry-maintenance screen, so the calendar's grant
#: can never quietly become the registry's edit grant.
PERMISSION = "activity.calendar.read"


def _out(agenda: Agenda) -> CalendarOut:
    return CalendarOut(
        days=[
            CalendarDayOut(
                date=day.day,
                is_today=day.is_today,
                is_nonworking=day.is_nonworking,
                nonworking_label=day.nonworking_label,
                events=[
                    CalendarEventOut(
                        source=event.source,
                        ref=event.ref,
                        title=event.title,
                        date_start=event.date_start,
                        date_end=event.date_end,
                        detail=event.detail,
                        status=event.status,
                        status_label=event.status_label,
                        tone=event.tone,
                        urgency=event.urgency,
                        href=event.href,
                        activity_id=event.activity_id,
                    )
                    for event in day.events
                ],
            )
            for day in agenda.days
        ],
        total=agenda.total,
        start=agenda.window.start,
        end=agenda.window.end,
        window_max_days=MAX_WINDOW_DAYS,
        window_clamped=agenda.window.clamped,
        source_cap=SOURCE_CAP,
        sources=[
            CalendarSourceOut(
                key=report.key,
                label=report.label,
                count=report.count,
                total=report.total,
                bounded_note=report.bounded_note,
            )
            for report in agenda.sources
        ],
        today=agenda.today,
    )


@router.get("/calendar", response_model=CalendarOut)
async def calendar_agenda(
    start: date | None = Query(
        default=None, description="Manila date, inclusive. Defaults to today."
    ),
    end: date | None = Query(
        default=None,
        description=(
            "Manila date, inclusive. Defaults to 30 days out; clamped to 92, "
            "and `window_clamped` says when that happened."
        ),
    ),
    principal: Principal = Depends(require_permission(PERMISSION)),
    session: AsyncSession = Depends(get_session),
) -> CalendarOut:
    """The agenda for a date window.

    **No `limit`/`offset` — the window IS the paging control** (api-standards
    §9g's board precedent, and §9k for the correctness reason: past a per-source
    cap, an offset drops rows from the *middle* of the merged chronology while
    ``total`` still looks right).

    Each registered source applies its own scope rule, so the rows a caller sees
    here are exactly the rows their own modules already let them read one at a
    time. A source that narrows to nothing is a fact about this caller, not a
    refusal — the surface itself is theirs, and ``sources[].bounded_note`` says
    in the server's own words what bounded it.
    """
    now = utc_now()
    try:
        window = resolve_window(start=start, end=end, now=now)
    except CalendarWindowError as exc:
        raise APIError(422, "validation_error", str(exc)) from exc

    agenda = await collect(
        session, actor_user_id=principal.user_id, window=window, now=now
    )
    return _out(agenda)
