"""The reimbursement module's contributions to the Calendar of Activities.

Two sources, registered from the composition root (``main.py``) because
``core`` may not import ``modules`` — api-standards §9k. This file lives INSIDE
the module precisely so it can do the thing core cannot: import
``services.queue.oversight_scope``, the one definition of "which claims may this
actor see", and apply it unchanged.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.calendar.sources import (
    CalendarEvent,
    CalendarSource,
    SourceResult,
)
from office_connect.core.models import User
from office_connect.core.time import to_manila
from office_connect.modules.reimbursement.models import ReimbCashAdvance, ReimbClaim
from office_connect.modules.reimbursement.services import deadline as dl
from office_connect.modules.reimbursement.services import queue
from office_connect.modules.reimbursement.services import status as st
from office_connect.modules.reimbursement.services.cash_advance import (
    UNLIQUIDATED_STATUSES,
)
from office_connect.modules.reimbursement.workflow import FEATURE_FLAG_KEY

TRAVEL_KEY = "reimb.travel"
LIQUIDATION_KEY = "reimb.liquidation"

#: Claim status -> ui-standards §2's semantic set. Owned here, beside the
#: vocabulary it translates: the calendar page must stay generic over sources,
#: and a core page mapping `handed_to_fms` to a colour would be the coupling
#: §9k removes from the backend, smuggled back in through the browser.
_CLAIM_TONES: dict[str, str] = {
    st.DRAFT: "waiting",
    st.DIVISION_APPROVAL: "waiting",
    st.ADMIN_REVIEW: "waiting",
    st.HANDED_TO_FMS: "waiting",
    st.FMS_RETURNED: "warn",
    st.RETURNED: "warn",
    st.PAID_CLOSED: "done",
    st.CANCELLED: "blocked",
}

_CA_TONES: dict[str, str] = {
    "open": "waiting",
    "liquidation_started": "warn",
    "settled": "done",
    "overdue": "blocked",
}
_CA_LABELS: dict[str, str] = {
    "open": "To liquidate",
    "liquidation_started": "Liquidation started",
    "settled": "Settled",
    "overdue": "Overdue",
}


async def _actor_staff_id(session: AsyncSession, actor_user_id: int) -> int | None:
    """The caller's own staff id, resolved from their user row.

    Never from a client-supplied id — the same rule `my_work` follows. A user
    with no staff link (a break-glass or system account) has no own-claims.
    """
    actor = await session.get(User, actor_user_id)
    return actor.staff_id if actor is not None else None


def _trip_overlaps(start: date, end: date):
    """Claims whose trip intersects the window.

    ``date_return`` is coalesced to ``date_depart``: a same-day trip has no
    return date, and treating NULL as "open-ended" would put every dateless
    claim on every window. Claims with no ``date_depart`` at all are excluded
    by the comparison itself — a claim with no dates has no place on a calendar.
    """
    return (
        ReimbClaim.date_depart <= end,
        func.coalesce(ReimbClaim.date_return, ReimbClaim.date_depart) >= start,
    )


# ---------------------------------------------------------------- travel
async def fetch_travel(
    session: AsyncSession,
    *,
    actor_user_id: int,
    start: date,
    end: date,
    cap: int,
    now: datetime,
) -> SourceResult:
    """Trips the actor oversees, plus their own — api-standards §9f/§9h.

    **Two queries, unioned on id, rather than one widened ``base_query``.**
    ``base_query`` is a *security predicate* shared by the queue, the board and
    Insights, and its own docstring warns that a second or mutated copy is how a
    scope clause drifts. Two indexed reads over a <=92-day window is the cheap,
    honest answer.

    ``include_terminal=True``: a trip that already happened and was paid is
    still a calendar fact. The queue excludes terminals because it is a *work*
    queue — a different question with a different right answer.

    The own-claims branch has no ``WorkflowInstance`` join, so a **draft** trip
    appears on your own calendar. That is deliberate: an unsubmitted trip is
    still a trip you are taking.
    """
    is_global, unit_ids = await queue.oversight_scope(
        session, actor_user_id, now=now
    )
    staff_id = await _actor_staff_id(session, actor_user_id)

    id_selects = []
    if is_global or unit_ids:
        id_selects.append(
            queue.base_query(
                is_global=is_global, unit_ids=unit_ids, include_terminal=True
            )
            .with_only_columns(ReimbClaim.id)
            .where(*_trip_overlaps(start, end))
        )
    if staff_id is not None:
        id_selects.append(
            select(ReimbClaim.id).where(
                ReimbClaim.claimant_id == staff_id, *_trip_overlaps(start, end)
            )
        )

    if not id_selects:
        # Oversees nobody and has no staff link. NOT a refusal: the calendar is
        # legitimately theirs (activities are tenant-wide), so an empty travel
        # layer is a fact about them, stated in words (api-standards §9k).
        return SourceResult(events=[], total=0, bounded_note=_travel_note(False, set()))

    visible_ids: set[int] = set()
    for stmt in id_selects:
        visible_ids |= set((await session.execute(stmt)).scalars().all())

    total = len(visible_ids)
    if total == 0:
        return SourceResult(
            events=[], total=0, bounded_note=_travel_note(is_global, unit_ids)
        )

    rows = list(
        (
            await session.execute(
                select(ReimbClaim)
                .where(ReimbClaim.id.in_(visible_ids))
                # Truncation can only drop the LATEST rows in the window, never
                # rows from the middle (api-standards §9k).
                .order_by(ReimbClaim.date_depart.asc(), ReimbClaim.id.asc())
                .limit(cap)
            )
        )
        .scalars()
        .all()
    )

    events = []
    for row in rows:
        status = row.status or st.DRAFT
        vocab = st.vocabulary(row.kind)
        events.append(
            CalendarEvent(
                source=TRAVEL_KEY,
                ref=f"claim:{row.id}",
                title=row.purpose or (row.ref_no or "Travel"),
                date_start=row.date_depart,
                date_end=row.date_return,
                detail=row.destination,
                status=status,
                status_label=vocab.labels.get(status, status),
                tone=_CLAIM_TONES.get(status, "waiting"),
                # A trip is not a deadline; the SLA clock belongs to the queue,
                # which is the surface that exists to chase it.
                urgency=None,
                href=f"/reimbursement/claims/{row.id}",
                activity_id=row.activity_id,
            )
        )

    return SourceResult(
        events=events,
        total=total,
        bounded_note=_travel_note(is_global, unit_ids),
        capped=total > len(rows),
    )


def _travel_note(is_global: bool, unit_ids: set[int]) -> str | None:
    """What bounded this actor's travel layer, in the server's own words.

    A SENTENCE, never a count of hidden rows: "3 more you cannot see" tells a
    division chief how much travel a sibling division booked, which is a
    disclosure they could not have assembled by opening records one at a time
    (api-standards §9h).
    """
    if is_global:
        return None  # nothing is withheld
    if unit_ids:
        return "Travel is shown for the offices you oversee, plus your own."
    return "Travel shown here is your own. Colleagues' claims are not on this calendar."


# ----------------------------------------------------------- liquidation
async def fetch_liquidation(
    session: AsyncSession,
    *,
    actor_user_id: int,
    start: date,
    end: date,
    cap: int,
    now: datetime,
) -> SourceResult:
    """The caller's OWN unsettled liquidation deadlines (COA 97-002).

    **Own advances only, deliberately.** There is no set-form scope rule for
    cash advances anywhere in the codebase: ``GET /cash-advances`` is
    single-claimant and ``deps.can_read_cash_advance`` is a per-ROW rule that
    places a person by ``staff.section_id or staff.division_id`` — a *different*
    placement rule from the claim's ``WorkflowInstance.org_unit_id``. Inventing
    the set form here would mean a second org-placement predicate for the same
    module that must agree with the first one forever, and it would disclose
    "person X took a cash advance" in a list where that has never been visible.
    Own-only delivers the clock in full to the person the clock is about.
    (calendar.md §6b records the cost of widening it later.)

    **The clock is read from the ADVANCE, never from
    ``reimb_claims.liquidation_deadline``** — ``cash_advance.link_claim`` calls
    that column "a MIRROR, written here only". Feeding both would draw two
    countdown rows for one obligation on the same day, which is a defect that
    looks exactly like working software.
    """
    staff_id = await _actor_staff_id(session, actor_user_id)
    if staff_id is None:
        return SourceResult(events=[], total=0, bounded_note=_LIQUIDATION_NOTE)

    conditions = (
        ReimbCashAdvance.claimant_id == staff_id,
        ReimbCashAdvance.deadline_date.is_not(None),
        ReimbCashAdvance.deadline_date >= start,
        ReimbCashAdvance.deadline_date <= end,
        # A settled advance has no clock left to run. The module's own constant,
        # never a copied literal — a duplicated status set is how "settled" ends
        # up meaning two things.
        ReimbCashAdvance.status.in_(tuple(sorted(UNLIQUIDATED_STATUSES))),
    )

    total = (
        await session.execute(
            select(func.count()).select_from(
                select(ReimbCashAdvance.id).where(*conditions).subquery()
            )
        )
    ).scalar_one()

    rows = list(
        (
            await session.execute(
                select(ReimbCashAdvance)
                .where(*conditions)
                .order_by(
                    ReimbCashAdvance.deadline_date.asc(), ReimbCashAdvance.id.asc()
                )
                .limit(cap)
            )
        )
        .scalars()
        .all()
    )

    today = to_manila(now).date()
    events = [
        CalendarEvent(
            source=LIQUIDATION_KEY,
            ref=f"advance:{row.id}",
            title="Liquidation due",
            date_start=row.deadline_date,
            date_end=None,
            # No peso amount and no DV number: a calendar has no business
            # carrying financial identifiers.
            detail=None,
            status=row.status,
            status_label=_CA_LABELS.get(row.status, row.status),
            tone=_CA_TONES.get(row.status, "waiting"),
            # Rule 10: the engine that already owns the COA 97-002 clock.
            urgency=_urgency(dl.deadline_state(deadline=row.deadline_date, today=today)),
            href="/reimbursement/cash-advances",
            activity_id=None,
        )
        for row in rows
    ]

    return SourceResult(
        events=events,
        total=total,
        bounded_note=_LIQUIDATION_NOTE,
        capped=total > len(rows),
    )


_LIQUIDATION_NOTE = "Liquidation deadlines shown here are your own."


def _urgency(state: str | None) -> str | None:
    """``deadline.py``'s state, narrowed to the calendar's vocabulary.

    ``on_track`` becomes ``None``: the calendar's urgency field exists to raise
    a colour, and "this is fine" is the absence of one.
    """
    if state in (dl.DUE_SOON, dl.OVERDUE):
        return state
    return None


TRAVEL_SOURCE = CalendarSource(
    key=TRAVEL_KEY,
    label="Travel",
    fetch=fetch_travel,
    feature_flag=FEATURE_FLAG_KEY,
    scope_rule=(
        "services/queue.py::oversight_scope + base_query(include_terminal=True), "
        "UNIONed with the caller's own claims by claimant_id (resolved from "
        "core_users.staff_id, never a client id). api-standards §9f — never the "
        "route's globally-granted reimb.claim.read."
    ),
)

LIQUIDATION_SOURCE = CalendarSource(
    key=LIQUIDATION_KEY,
    label="Liquidation deadlines",
    fetch=fetch_liquidation,
    feature_flag=FEATURE_FLAG_KEY,
    scope_rule=(
        "OWN advances only — reimb_cash_advances.claimant_id == the caller's "
        "staff_id. Deliberately NOT deps.can_read_cash_advance: that is a "
        "per-ROW rule with no set form anywhere, and inventing one is a security "
        "increment (calendar.md §6b)."
    ),
)

__all__ = [
    "LIQUIDATION_KEY",
    "LIQUIDATION_SOURCE",
    "TRAVEL_KEY",
    "TRAVEL_SOURCE",
    "fetch_liquidation",
    "fetch_travel",
]
