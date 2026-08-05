"""The comment-learning loop — spec §11, Objective 3.

Every return since R-4-screens has stored ≥1 taxonomy reason in the append-only
``reimb_return_events``. Nothing has ever read them back. This module is the
read, and the one act that closes the loop.

**Two halves.**

``ranked_reasons`` ranks the reasons packets come back for, over a 90-day window
with the immediately-preceding window as its trend. ``set_promoted`` flips one
reason to *promoted*, which makes it an advisory at wizard step 5 — spec §14's
graded sentence for this increment is *"Promotion creates a working warning with
no deploy"*, and the only thing standing between those two clauses is that a
promotion is a **data** change (rule 10).

**Privacy is the design constraint, not a footnote.** Spec §11: *"aggregates
only, mirroring the §14.7 pattern; per-person return counts are visible only to
the person themselves."* §14.7 is the privacy-preserving query log — ids and
parameter names, never values. Three things follow and all three are enforced
here rather than in the router:

- The aggregate has **no person dimension at all.** It groups by reason id and
  by nothing else, so there is no claimant column to leak, no drill-down to
  offer, and no "who" to reconstruct by subtracting two filtered calls.
- **The scope IS the privacy boundary.** The count spans exactly the claims the
  actor could already open one at a time (``queue.oversight_scope`` →
  ``queue.base_query``), so the aggregate reveals nothing they could not have
  assembled by hand. That is why no minimum-cell suppression is applied: the
  question "is this count about one person?" is already answered by "yes, and
  you oversee them".
- The claimant-facing advisory carries the **reason, never the number** — see
  ``api/tracking.py::list_return_reasons``, which is where the wizard reads it.

**Deliberately NOT here:** spec §13's KPI surface (cycle time, return *rate*,
per-division volume, configurable time filters + deltas) stays in Stage H where
master-plan §119 puts it, exactly as R-7-board deferred it. ``total_returns``
rides the envelope as context, never as a denominator — a rate needs a
submission count this surface does not compute.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import Select, and_, func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.org_units import scoped_org_units
from office_connect.core.session import set_audit_context
from office_connect.core.time import to_manila, utc_now
from office_connect.modules.reimbursement.models import (
    ReimbClaim,
    ReimbReturnEvent,
    ReimbReturnReasonCatalog,
)
from office_connect.modules.reimbursement.services import errors, queue
from office_connect.modules.reimbursement.services.lifecycle import config_int

logger = logging.getLogger(__name__)

#: How far back the ranking looks, and therefore how long the trend's comparison
#: window is. CALENDAR days like ``board.done_window_days`` and for the same
#: reason: this bounds a display window, not a deadline — nobody is late because
#: of it, and "the last 90 days" is what a bureau chief means.
WINDOW_KEY = "insights.window_days"
WINDOW_DEFAULT = 90

#: Trend verdicts. ``new`` is distinct from ``up`` on purpose: "3 returns, up
#: from 0" reads as a trend line when it is actually a first appearance, and the
#: two want different copy.
UP = "up"
DOWN = "down"
FLAT = "flat"
NEW = "new"


@dataclass(frozen=True)
class ReasonRank:
    """One row of the ranked list. No person dimension, by construction."""

    reason_id: int
    code: str
    label: str
    category: str
    count: int
    prior_count: int
    trend: str
    promoted: bool
    is_active: bool


@dataclass(frozen=True)
class Insights:
    """The whole surface: the ranking plus the window it describes."""

    window_days: int
    period_start: date
    total_returns: int
    items: tuple[ReasonRank, ...]


def _trend(count: int, prior: int) -> str:
    if prior == 0:
        return NEW if count else FLAT
    if count > prior:
        return UP
    if count < prior:
        return DOWN
    return FLAT


def window_cutoffs(now: datetime, days: int) -> tuple[datetime, datetime]:
    """``(cutoff, prior_cutoff)`` — the window, and the window before it."""
    cutoff = now - timedelta(days=days)
    return cutoff, cutoff - timedelta(days=days)


async def window_days(session: AsyncSession, *, today: date | None = None) -> int:
    """The ranking window. Fail-soft like every other cadence/display value —
    a missing config row must not blank the surface."""
    return await config_int(
        session,
        key=WINDOW_KEY,
        field="days",
        default=WINDOW_DEFAULT,
        today=today or to_manila(utc_now()).date(),
    )


def _events_query(
    *, is_global: bool, unit_ids: set[int], prior_cutoff: datetime
) -> Select:
    """Return events on claims inside the actor's scope, both windows.

    Built on ``queue.base_query`` so the SECURITY predicate — the instance join,
    the draft exclusion and ``scope_clause`` — has exactly one definition in the
    module. A second hand-rolled copy of a scope clause is how a surface starts
    counting a division it may not see, and here that drift would be invisible:
    the number would merely be bigger.

    ``include_terminal=True`` because a return that happened, happened. The claim
    it happened to may since have been paid, settled or **cancelled**, and none
    of those change why the packet came back. (Spec §6.1 row 9 excludes cancelled
    claims from KPIs; this is not a KPI — the fact being counted is the return
    event, not the claim's outcome. One predicate to flip if the resident auditor
    disagrees; pinned by test.)
    """
    return (
        queue.base_query(
            is_global=is_global, unit_ids=unit_ids, include_terminal=True
        )
        .join(ReimbReturnEvent, ReimbReturnEvent.claim_id == ReimbClaim.id)
        .where(ReimbReturnEvent.created_at >= prior_cutoff)
    )


async def ranked_reasons(
    session: AsyncSession,
    *,
    is_global: bool,
    unit_ids: set[int],
    now: datetime | None = None,
    days: int | None = None,
) -> Insights:
    """Spec §11: reasons ranked by window count, with trend.

    **ONE grouped statement over both windows**, via conditional aggregates —
    two round-trips would let a return landing between them be counted in
    neither, which on a surface whose whole job is counting is not a rounding
    error but a wrong answer.

    ``reason_ids`` is a JSONB array, so the rows are unnested with
    ``jsonb_array_elements_text`` and grouped **on the text element**. The
    element is deliberately NOT cast to an integer in SQL: ``queue._GRAND``'s
    ``::numeric`` is safe only because ``compute.py`` is the sole writer of what
    it casts, whereas ``reason_ids`` is FK-less JSONB with no database-level
    guarantee at all — one junk element would raise ``invalid input syntax`` and
    500 the entire surface instead of surfacing one bad row. Resolution happens
    in Python, and an id that resolves to nothing is **logged** rather than
    silently dropped: the same rule, and the same reason, as
    ``queue.column_totals``'s unmapped statuses.
    """
    now = now or utc_now()
    days = days if days is not None else await window_days(session)
    cutoff, prior_cutoff = window_cutoffs(now, days)

    element = func.jsonb_array_elements_text(ReimbReturnEvent.reason_ids).table_valued(
        "value"
    )
    in_window = ReimbReturnEvent.created_at >= cutoff
    in_prior = and_(
        ReimbReturnEvent.created_at >= prior_cutoff,
        ReimbReturnEvent.created_at < cutoff,
    )

    stmt = (
        _events_query(
            is_global=is_global, unit_ids=unit_ids, prior_cutoff=prior_cutoff
        )
        .join(element, true())
        .with_only_columns(
            element.c.value.label("reason"),
            func.count().filter(in_window).label("current"),
            func.count().filter(in_prior).label("prior"),
        )
        .group_by(element.c.value)
    )
    tallies: dict[int, tuple[int, int]] = {}
    unmapped: dict[str, int] = {}
    for raw, current, prior in (await session.execute(stmt)).all():
        try:
            reason_id = int(raw)
        except (TypeError, ValueError):
            unmapped[str(raw)] = int(current) + int(prior)
            continue
        tallies[reason_id] = (int(current), int(prior))

    # The count of RETURNS in the window — not the sum of the ranked counts,
    # which double-counts a return citing three reasons. Both numbers are true
    # and they answer different questions; the header asks this one.
    total_returns = (
        await session.execute(
            _events_query(
                is_global=is_global, unit_ids=unit_ids, prior_cutoff=prior_cutoff
            )
            .where(in_window)
            .with_only_columns(func.count(ReimbReturnEvent.id))
        )
    ).scalar_one()

    catalog = {}
    if tallies:
        rows = (
            (
                await session.execute(
                    # `include_deleted` for the same reason the timeline uses it:
                    # a reason retired last year still explains the returns it
                    # caused, and a ranked list that silently omits them would
                    # under-report the history it exists to show.
                    select(ReimbReturnReasonCatalog)
                    .where(ReimbReturnReasonCatalog.id.in_(tallies))
                    .execution_options(include_deleted=True)
                )
            )
            .scalars()
            .all()
        )
        catalog = {row.id: row for row in rows}

    for reason_id, (current, prior) in tallies.items():
        if reason_id not in catalog:
            unmapped[str(reason_id)] = current + prior
    if unmapped:
        # Cannot happen while `_assert_return_reasons` is the only writer's gate
        # — but a reason hard-deleted outside the app, or a junk element written
        # by a future caller that skips the service, lands here. The failure mode
        # is returns missing from a ranking with nothing on screen to say so.
        logger.warning(
            "reimb.insights.unmapped_reason reasons=%s — these return reasons "
            "resolve to no catalog row and are missing from the ranking.",
            sorted(unmapped),
        )

    items = [
        ReasonRank(
            reason_id=reason_id,
            code=row.code,
            label=row.label,
            category=row.category,
            count=current,
            prior_count=prior,
            trend=_trend(current, prior),
            promoted=bool(row.promoted_check),
            is_active=bool(row.is_active) and row.deleted_at is None,
        )
        for reason_id, (current, prior) in tallies.items()
        if (row := catalog.get(reason_id)) is not None
    ]
    # A reason that fell to ZERO this window but had returns in the one before
    # is KEPT, and sorts last with `trend: "down"`. That row is the learning loop
    # visibly working — dropping it would delete the only evidence a promotion
    # helped, on the one surface built to show it.
    items.sort(key=lambda item: (-item.count, -item.prior_count, item.label))

    return Insights(
        window_days=days,
        period_start=to_manila(cutoff).date(),
        total_returns=int(total_returns),
        items=tuple(items),
    )


# --------------------------------------------------------------------------
# Promotion (spec §11 — "one click … no code change")
# --------------------------------------------------------------------------


#: Promoting is the Admin Officer's act — ``seeds.py`` names them the taxonomy's
#: owner — so it rides ``reimb.claim.review`` rather than a new permission.
PROMOTE_PERM = "reimb.claim.review"


async def may_promote(
    session: AsyncSession, actor_user_id: int, *, now: datetime | None = None
) -> bool:
    """Does this actor hold ``reimb.claim.review`` AGENCY-WIDE?

    Deliberately narrower than ``queue.oversight_scope``, in two ways, and both
    matter.

    **Global, not scoped.** A promotion shows a warning to every claimant in the
    tenant. A grant covering one division cannot produce a tenant-wide effect —
    that is a scope escalation dressed as a feature, and it would be invisible
    because the result looks like the button working.

    **This permission, not the oversight SET.** ``oversight_scope`` unions
    review/approve/fms_update because any of them makes you an overseer of
    somebody, which is the right question for a *read*. Authoring the taxonomy is
    a different job: an approver clears claims, the Admin Officer owns the
    catalog (``seeds.py``'s ``owner`` field says so out loud).
    """
    granted = await scoped_org_units(session, actor_user_id, PROMOTE_PERM, now=now)
    return None in granted


async def set_promoted(
    session: AsyncSession,
    *,
    reason_id: int,
    promoted: bool,
    actor_user_id: int,
) -> ReimbReturnReasonCatalog:
    """Promote (or demote) one reason. Flushes; the router owns the transaction.

    **Load-and-mutate, never a bulk UPDATE.** ``core/audit.py`` refused exactly
    that at R-7-events and was right to: this is an admin act on a tenant-wide
    catalog whose effect is a warning shown to every claimant in the agency, and
    it must hash-chain. ``updated_by``/``updated_at`` are what answer "who
    promoted this, and when" — which is also why no promotion table was added.

    A retired reason cannot be promoted: warning claimants about a rule nobody
    enforces any more is worse than not warning at all, and the fail-safe
    direction on an advisory runs the opposite way to the usual one — **when in
    doubt, do not warn.** Demotion is deliberately NOT gated the same way, so a
    reason retired while promoted can always be switched off.
    """
    set_audit_context(session, actor_id=actor_user_id)
    row = (
        await session.execute(
            select(ReimbReturnReasonCatalog).where(
                ReimbReturnReasonCatalog.id == reason_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise errors.unknown_return_reason([reason_id])
    if promoted and not row.is_active:
        raise errors.reason_not_promotable(row.code)

    if bool(row.promoted_check) != promoted:
        row.promoted_check = promoted
        await session.flush()
    return row
