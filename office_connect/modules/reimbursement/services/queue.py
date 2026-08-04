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

from datetime import date, datetime

from sqlalchemy import Select, or_, select
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
) -> Select:
    """Submitted, live claims inside the actor's scope.

    Drafts are excluded by construction (``workflow_instance_id IS NOT NULL``):
    an unsubmitted claim is nobody's oversight, it is the traveller's own work
    and My Work already shows it. Terminal claims are excluded because this is a
    queue — R-7-board's columns are where "Done" gets counted.
    """
    stmt = (
        select(ReimbClaim)
        .join(
            WorkflowInstance,
            WorkflowInstance.id == ReimbClaim.workflow_instance_id,
        )
        .where(
            ReimbClaim.workflow_instance_id.is_not(None),
            or_(
                ReimbClaim.status.is_(None),
                ReimbClaim.status.not_in(st.ALL_TERMINAL_STATES),
            ),
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
