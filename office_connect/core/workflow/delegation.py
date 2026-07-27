"""Authority resolution — direct grant OR an active OIC delegation.

The engine authorizes on permission STRINGS via ``core/org_units.py::authorize_scoped``
(never role names). Delegation adds the first-class OIC path: an actor may act if they
hold the permission themselves, OR they hold an in-window delegation from someone who
does. The caller records BOTH the actor and the ``on_behalf_of`` delegator on the
event, so the audit trail stays truthful ("Approved by Cruz (OIC for Reyes)").

This refines the Stage-B B3 "no RBAC delegation table" decision: a role-window grants a
ROLE; ``core_workflow_delegations`` records that one PERSON exercised another's
authority for a workflow action (master-plan §1.1 #1).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import false, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.models import WorkflowDelegation
from office_connect.core.org_units import ancestors_or_self, authorize_scoped
from office_connect.core.time import utc_now


@dataclass(frozen=True)
class Authority:
    """Resolved authorization outcome. ``on_behalf_of`` is the delegator when the
    actor acted under a delegation, else ``None`` (a direct grant)."""

    authorized: bool
    on_behalf_of: int | None = None


async def resolve_authority(
    session: AsyncSession,
    *,
    actor_user_id: int,
    required_permission: str | None,
    org_unit_id: int | None,
    definition_id: int | None = None,
    now: datetime | None = None,
) -> Authority:
    """Decide whether ``actor_user_id`` may exercise ``required_permission`` against
    ``org_unit_id`` — directly, or via an active delegation from a grant-holder.

    A ``None`` permission is an open gate (authorized, no delegation). A direct grant
    wins (``on_behalf_of=None``); otherwise each active delegation whose scope covers
    the target is tried, and passes iff the *delegator* holds the permission there."""
    if required_permission is None:
        return Authority(True, None)

    if await authorize_scoped(session, actor_user_id, required_permission, org_unit_id):
        return Authority(True, None)

    now = now or utc_now()
    # Candidate delegations TO this actor, active now, scoped to this definition (or
    # any), and to this org subtree (or any).
    covering = await ancestors_or_self(session, org_unit_id) if org_unit_id else []
    stmt = select(WorkflowDelegation).where(
        WorkflowDelegation.delegate_user_id == actor_user_id,
        WorkflowDelegation.starts_at <= now,
        WorkflowDelegation.ends_at > now,
        or_(
            WorkflowDelegation.definition_id.is_(None),
            WorkflowDelegation.definition_id == definition_id,
        ),
        or_(
            WorkflowDelegation.org_unit_id.is_(None),
            WorkflowDelegation.org_unit_id.in_(covering) if covering else false(),
        ),
    )
    for deleg in (await session.execute(stmt)).scalars().all():
        if await authorize_scoped(
            session, deleg.delegator_user_id, required_permission, org_unit_id
        ):
            return Authority(True, deleg.delegator_user_id)

    return Authority(False, None)
