"""The oversight queue — who may see a LIST of claims, and which ones are stalled.

Two things live here, and they exist together because the second is worthless
without the first.

**Scope.** Every read path before this one answered "may this actor read THIS
claim" (``deps.can_read_claim``, one row, one ``authorize_scoped``). A list asks
the question backwards, and the naive translation is a security hole: the
``staff`` role's ``reimb.claim.read`` grant is GLOBAL (spec §3.2), because a
traveller must be able to read their own claim from anywhere in the org tree.
Key a list on that permission and every employee gets every colleague's
destinations, purposes and peso totals in one request. So the queue is scoped on
the OVERSIGHT permissions — the ones only an approver, a reviewer or the Admin
Officer holds — and on the subtree those grants actually cover
(``core.org_units.descendants_or_self``). Holding none of them is not an empty
list, it is a 403: this surface is not for you.

**The FMS follow-up clock (spec §7 rule 5).** ``handed_to_fms`` is deliberately
never SLA-stamped — the holder is ``external_fms``, the reminder ladder is
holder-only, and nobody nudges FMS. R-4-app recorded that the ">10 working days"
case is an *Admin dashboard filter* instead, and this is that filter. It counts
Manila working days since ``holder_since``, which for a claim sitting at
``handed_to_fms`` IS the hand-off instant: nothing overwrites it while the state
does not change, and a bounced-then-re-handed claim correctly starts a new
count. That is also why no column was added — the substrate was already right.

The threshold is config (``sla.external_followup_working_days``, default 10),
read fail-soft like every other cadence value: a missing row must not blank the
queue.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import Numeric, Select, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.models import WorkflowInstance
from office_connect.core.org_units import descendants_or_self, scoped_org_units
from office_connect.core.time import to_manila, utc_now
from office_connect.core.workdays import (
    load_nonworking_dates,
    working_days_between,
)
from office_connect.modules.reimbursement.models import ReimbClaim
from office_connect.modules.reimbursement.services import status as st
from office_connect.modules.reimbursement.services.lifecycle import (
    config_int,
    config_working_days,
)

#: The permissions that make someone an OVERSEER of other people's claims.
#: Deliberately excludes ``reimb.claim.read`` (global for ``staff``) and
#: ``reimb.claim.create``/``.submit`` (a traveller's own verbs).
OVERSIGHT_PERMS: tuple[str, ...] = (
    "reimb.claim.review",
    "reimb.claim.fms_update",
    "reimb.claim.approve",
)

_FOLLOWUP_KEY = "sla.external_followup_working_days"
_FOLLOWUP_DEFAULT = 10

#: Page bounds, following the one precedent in the codebase (``core/api/
#: directory.py``). The pagination *envelope* is a Stage-D deferral; until then
#: a list is ``?limit=&offset=`` with a server-side ceiling.
MAX_LIMIT = 200
DEFAULT_LIMIT = 50

#: How many externally-held claims the follow-up filter will scan. Generous by
#: design: this is the one filter whose failure mode is a stalled claim nobody
#: chases. Safe under truncation because the scan is ordered longest-waiting
#: first — everything over the threshold sorts ahead of everything under it —
#: and the router logs a warning if the cap is ever actually reached.
EXTERNAL_SCAN_CAP = 1000

# --- R-7-board (spec §9.6) --------------------------------------------------

#: Cards per board column. NOT a client-tunable ``?limit=``: a board that pages
#: is a queue, and the queue is one click away. The header count is the whole
#: column regardless, and ``card_limit`` rides the response so the "showing N of
#: M" line quotes the server's number rather than a literal the browser would
#: have to keep in step.
BOARD_CARD_LIMIT = 20

#: How far back the Done column looks. `paid_closed` and `settled` accumulate
#: forever, and an all-time peso figure is a number nobody reads — by year two
#: it says nothing about how the bureau is doing this quarter. In Bureau and
#: With FMS stay unbounded because they are live work: a claim stuck since March
#: is exactly what the board exists to show.
DONE_WINDOW_KEY = "board.done_window_days"
DONE_WINDOW_DEFAULT = 90


async def oversight_scope(
    session: AsyncSession, actor_user_id: int, *, now: datetime | None = None
) -> tuple[bool, set[int]]:
    """``(is_global, org_unit_ids)`` — the subtree this actor oversees.

    ``(True, set())`` means a global grant: no org filter at all. ``(False,
    set())`` means they hold no oversight permission anywhere, and the caller
    must refuse rather than return an empty list — an empty list reads as "there
    is no work", which is a different and misleading statement.
    """
    granted: set[int | None] = set()
    for perm in OVERSIGHT_PERMS:
        granted |= await scoped_org_units(session, actor_user_id, perm, now=now)
    if not granted:
        return (False, set())
    if None in granted:
        return (True, set())
    units = {int(u) for u in granted if u is not None}
    return (False, await descendants_or_self(session, units))


def scope_clause(is_global: bool, unit_ids: set[int]):
    """The WHERE fragment for a resolved scope, or ``None`` when unbounded.

    Claims whose instance carries no org unit are included for a global holder
    only. A scoped overseer must not see an unplaceable claim: "I could not
    determine whose it is" is not a reason to show it to someone.
    """
    if is_global:
        return None
    return WorkflowInstance.org_unit_id.in_(unit_ids)


def base_query(
    *,
    is_global: bool,
    unit_ids: set[int],
    kind: str | None = None,
    statuses: tuple[str, ...] | None = None,
    claimant_id: int | None = None,
    include_terminal: bool = False,
) -> Select:
    """Submitted claims inside the actor's scope — the one definition of
    "which claims may this actor see".

    Drafts are excluded by construction (``workflow_instance_id IS NOT NULL``):
    an unsubmitted claim is nobody's oversight, it is the traveller's own work
    and My Work already shows it.

    Terminal claims are excluded BY DEFAULT because the original caller is a
    queue. R-7-board's Done column is entirely terminal, so it opts out by
    typing ``include_terminal=True`` — a keyword with a safe default rather
    than a second query builder, because a second builder is a second copy of a
    *security predicate* (the join, ``scope_clause``, the draft rule), and a
    drifted scope clause leaks where a drifted display mapper merely renders
    wrong.

    Deliberately NOT "drop the terminal rule whenever ``statuses`` is given":
    that would quietly turn ``GET /claims?status=paid_closed`` on the queue from
    an empty list into a list of paid claims, which is the exact silent widening
    the flag exists to prevent.
    """
    stmt = (
        select(ReimbClaim)
        .join(
            WorkflowInstance,
            WorkflowInstance.id == ReimbClaim.workflow_instance_id,
        )
        .where(ReimbClaim.workflow_instance_id.is_not(None))
    )
    if not include_terminal:
        stmt = stmt.where(
            or_(
                ReimbClaim.status.is_(None),
                ReimbClaim.status.not_in(st.ALL_TERMINAL_STATES),
            )
        )
    clause = scope_clause(is_global, unit_ids)
    if clause is not None:
        stmt = stmt.where(clause)
    if kind is not None:
        stmt = stmt.where(ReimbClaim.kind == kind)
    if statuses:
        stmt = stmt.where(ReimbClaim.status.in_(statuses))
    if claimant_id is not None:
        stmt = stmt.where(ReimbClaim.claimant_id == claimant_id)
    return stmt


async def followup_threshold(
    session: AsyncSession, *, today: date | None = None
) -> int:
    """Working days with FMS after which a claim wants chasing (spec §7 rule 5)."""
    return await config_working_days(
        session,
        key=_FOLLOWUP_KEY,
        default=_FOLLOWUP_DEFAULT,
        today=today or to_manila(utc_now()).date(),
    )


async def days_with_fms(
    session: AsyncSession,
    claims: list[ReimbClaim],
    *,
    now: datetime | None = None,
) -> dict[int, int]:
    """``{claim_id: working days since hand-off}`` for the externally-held rows.

    One holiday window for the whole page, never a load per row — the same
    batching rule ``lifecycle._stamp_sla`` follows. Rows not held by FMS, and
    rows with no ``holder_since``, are simply absent from the mapping: the
    question does not apply to them, and 0 would be a false answer.
    """
    now = now or utc_now()
    external = [
        c
        for c in claims
        if c.holder_kind == "external_fms" and c.holder_since is not None
    ]
    if not external:
        return {}
    today = to_manila(now).date()
    # `holder_since` is UTC; the count is in Manila days, so convert first —
    # a hand-off at 08:00 UTC is already that afternoon in Manila.
    since = {c.id: to_manila(c.holder_since).date() for c in external}
    earliest = min(since.values())
    nonworking = await load_nonworking_dates(
        session, min(earliest, today), max(earliest, today)
    )
    return {
        cid: max(working_days_between(day, today, nonworking), 0)
        for cid, day in since.items()
    }


# --- R-7-board: the pipeline board (spec §9.6) ------------------------------


async def done_window_days(
    session: AsyncSession, *, today: date | None = None
) -> int:
    """How many days back the Done column reaches. Fail-soft like every other
    cadence value — a missing config row must not blank a column."""
    return await config_int(
        session,
        key=DONE_WINDOW_KEY,
        field="days",
        default=DONE_WINDOW_DEFAULT,
        today=today or to_manila(utc_now()).date(),
    )


def done_cutoff(now: datetime, days: int) -> datetime:
    """The instant the Done window opens."""
    return now - timedelta(days=days)


def _done_window_clause(cutoff: datetime):
    """Terminal rows must be recent; live rows are never age-filtered.

    One predicate rather than two queries, so the counts and the cards come off
    a set defined in exactly one place. ``cancelled`` is caught by this too and
    then dropped by the column mapping, which is belt and braces: a voided claim
    is off the board at both ends.
    """
    return or_(
        ReimbClaim.status.is_(None),
        ReimbClaim.status.not_in(st.ALL_TERMINAL_STATES),
        ReimbClaim.updated_at >= cutoff,
    )


#: ``totals->>'grand'`` as a number the database can add up.
#:
#: ``numeric(14,2)`` rather than the per-claim column's ``numeric(12,2)``: this
#: is a bureau-wide sum and the cast target is ours to choose, because the
#: source is JSONB text.
#:
#: **A load-bearing invariant of another module.** ``::numeric`` on text raises
#: ``invalid input syntax`` on anything that is not a number. The only writer of
#: ``totals["grand"]`` is ``services/compute.py``, through ``core.money_str``,
#: so every stored value is a valid 2-dp string. Anything that starts writing
#: ``totals`` must keep that true or this query starts failing.
_GRAND = cast(ReimbClaim.totals["grand"].astext, Numeric(14, 2))


async def column_totals(
    session: AsyncSession,
    *,
    is_global: bool,
    unit_ids: set[int],
    cutoff: datetime,
) -> tuple[dict[str, tuple[int, Decimal]], dict[str, int]]:
    """``({column: (count, pesos)}, {unmapped_status: count})`` for the board.

    ONE statement, grouped by status, bucketed in Python through
    ``st.BOARD_COLUMN_STATES``. Not a SQL ``CASE`` built from the same mapping:
    the mapping then lives in one place instead of two, at most a dozen rows
    come back, and — the real reason — **an unmapped status is observable**. A
    code left over from a retired definition version comes back in the grouped
    rows, lands in no column, and is returned for the caller to log. A ``CASE``
    would silently ``ELSE NULL`` it, and spec §14 grades this surface on "board
    totals match DB".

    That is also why the query does NOT pre-filter on ``ALL_BOARD_STATES``:
    filtering in SQL would hide the very rows the warning exists to catch.
    ``cancelled`` comes back and is dropped by the mapping's explicit ``None``,
    which is the mapping visibly doing its job.

    The count is deliberately unbounded — a header count that pages is not a
    count. Both predicates are indexed (``ix_reimb_claims_status``,
    ``ix_core_workflow_instances_org_unit_id``).
    """
    stmt = (
        base_query(is_global=is_global, unit_ids=unit_ids, include_terminal=True)
        .where(_done_window_clause(cutoff))
        .with_only_columns(
            ReimbClaim.status,
            func.count(ReimbClaim.id).label("claims"),
            func.coalesce(func.sum(_GRAND), 0).label("pesos"),
        )
        .group_by(ReimbClaim.status)
    )
    buckets: dict[str, tuple[int, Decimal]] = {
        column: (0, Decimal("0")) for column, _label in st.BOARD_COLUMNS
    }
    unmapped: dict[str, int] = {}
    for status, claims, pesos in (await session.execute(stmt)).all():
        column = next(
            (
                key
                for key, states in st.BOARD_COLUMN_STATES.items()
                if status in states
            ),
            None,
        )
        if column is None:
            # `draft` cannot appear (the instance join excludes it) and
            # `cancelled` is off the board on purpose — neither is a surprise,
            # so neither is reported. Anything else is.
            if status not in (st.DRAFT, st.CANCELLED):
                unmapped[str(status)] = int(claims)
            continue
        count, total = buckets[column]
        buckets[column] = (count + int(claims), total + Decimal(pesos))
    return buckets, unmapped


def board_card_query(
    *,
    is_global: bool,
    unit_ids: set[int],
    column: str,
    cutoff: datetime,
) -> Select:
    """The cards for one column — at most ``BOARD_CARD_LIMIT``, best first.

    The ordering diverges for Done, and it has to. A terminal state clears the
    holder (``lifecycle`` nulls ``holder_since`` with it), so "longest waiting"
    is not merely wrong there, it is undefined: every row would tie on NULL and
    fall through to ``id``. The question a Done column answers is "what just
    finished", so it sorts by the same field the window filters on.
    """
    stmt = base_query(
        is_global=is_global,
        unit_ids=unit_ids,
        statuses=tuple(sorted(st.BOARD_COLUMN_STATES[column])),
        include_terminal=True,
    ).where(_done_window_clause(cutoff))
    if column == st.BOARD_DONE:
        stmt = stmt.order_by(ReimbClaim.updated_at.desc(), ReimbClaim.id.desc())
    else:
        stmt = stmt.order_by(
            ReimbClaim.holder_since.asc().nulls_last(), ReimbClaim.id.asc()
        )
    return stmt.limit(BOARD_CARD_LIMIT)
