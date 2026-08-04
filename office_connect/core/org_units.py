"""Org-unit ancestry + org-scoped authorization (Stage B / Increment 3, RBAC).

A ``core_user_roles`` grant with ``org_unit_id`` NULL is *global*; set, it is
*scoped* — "Approver OF the BLHSD Finance Section". A scoped grant authorizes the
permission for the grantee's unit **and everything below it**. So to decide
whether an actor may act on a request that belongs to some org unit, we walk UP
from the *request's* unit to the root and ask whether any of the actor's scoped
grants sits on that path (or is global). This is the reusable approver-resolution
primitive the Stage-C reimbursement flow calls.

``core_org_units`` is a plain self-referential adjacency list
(``parent_org_unit_id``); ``ancestors_or_self`` is the recursive-CTE walker (there
was no ancestry helper before B3). It is soft-delete-filtered and depth-guarded so
a mis-set parent pointer can never spin an unbounded query.

``descendants_or_self`` (Stage C R-7-queue) is its inverse, and exists because a
LIST endpoint asks the scope question backwards: not "may this actor act on this
one request" but "which requests may this actor see", which is the subtree
closure of their grants and must be one query, not one per row.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.models import (
    OrgUnit,
    Permission,
    RolePermission,
    User,
    UserRole,
)
from office_connect.core.time import utc_now

_MAX_ANCESTRY_DEPTH = 64


class OrgUnitScope(enum.Enum):
    """How ``require_permission`` interprets a grant's org scope.

    - ``GLOBAL`` — the permission is checked without org bounds (the default;
      identical to B2 behavior). A grant of the permission — global or scoped —
      satisfies it.
    - ``REQUESTER`` — the permission is checked against the *request's* org unit:
      the actor must hold it globally, or via a scoped grant whose unit is an
      ancestor-or-self of the request's unit.
    """

    GLOBAL = "global"
    REQUESTER = "requester"


async def ancestors_or_self(
    session: AsyncSession, org_unit_id: int | None
) -> list[int]:
    """Return ``org_unit_id`` and every ancestor id, walking ``parent_org_unit_id``
    to the root, ordered nearest-first (self, parent, …, root). Empty for
    ``None``. Soft-deleted nodes stop the walk."""
    if org_unit_id is None:
        return []
    ou = OrgUnit.__table__
    base = (
        select(ou.c.id, ou.c.parent_org_unit_id, literal(0).label("depth"))
        .where(ou.c.id == org_unit_id, ou.c.deleted_at.is_(None))
        .cte(name="org_ancestry", recursive=True)
    )
    parent = ou.alias()
    step = select(
        parent.c.id, parent.c.parent_org_unit_id, (base.c.depth + 1).label("depth")
    ).where(
        parent.c.id == base.c.parent_org_unit_id,
        parent.c.deleted_at.is_(None),
        base.c.depth < _MAX_ANCESTRY_DEPTH,
    )
    cte = base.union_all(step)
    # Core-table select: the ORM soft-delete listener does not apply here, so the
    # deleted_at filter is stated explicitly in the CTE above; skip the listener.
    stmt = select(cte.c.id).order_by(cte.c.depth).execution_options(include_deleted=True)
    return list((await session.execute(stmt)).scalars().all())


async def descendants_or_self(
    session: AsyncSession, org_unit_ids: Iterable[int]
) -> set[int]:
    """Return every id in ``org_unit_ids`` plus everything BELOW them.

    The inverse walk of :func:`ancestors_or_self`, and the same authorization
    rule read from the other end: a scoped grant at unit U authorizes U and its
    whole subtree, so "may this actor act on THIS request" walks up from the
    request, while "which requests may this actor see" needs the subtree closure
    of the grants. A LIST endpoint can only ask the second question — filtering
    rows one at a time with ``ancestors_or_self`` is a query per row, unbounded
    by the page size.

    Unordered (a set — callers filter with ``IN``, they do not render a tree).
    Soft-deleted nodes stop the walk, so a disbanded section does not drag its
    children back into scope. Depth-guarded like its sibling.
    """
    roots = {int(i) for i in org_unit_ids}
    if not roots:
        return set()
    ou = OrgUnit.__table__
    base = (
        select(ou.c.id, literal(0).label("depth"))
        .where(ou.c.id.in_(roots), ou.c.deleted_at.is_(None))
        .cte(name="org_subtree", recursive=True)
    )
    child = ou.alias()
    step = select(child.c.id, (base.c.depth + 1).label("depth")).where(
        child.c.parent_org_unit_id == base.c.id,
        child.c.deleted_at.is_(None),
        base.c.depth < _MAX_ANCESTRY_DEPTH,
    )
    cte = base.union_all(step)
    # Core-table select: the ORM soft-delete listener does not apply here, so the
    # deleted_at filter is stated explicitly in the CTE above; skip the listener.
    stmt = select(cte.c.id).execution_options(include_deleted=True)
    return set((await session.execute(stmt)).scalars().all())


async def scoped_org_units(
    session: AsyncSession,
    user_id: int,
    perm: str,
    *,
    now: datetime | None = None,
) -> set[int | None]:
    """The org scopes at which the user currently holds ``perm``: ``None`` for a
    global grant, or the ``org_unit_id`` of each scoped grant. Empty = does not
    hold the permission at all. Honors the delegation/OIC valid window."""
    now = now or utc_now()
    stmt = (
        select(UserRole.org_unit_id)
        .join(RolePermission, RolePermission.role_id == UserRole.role_id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(
            UserRole.user_id == user_id,
            Permission.code == perm,
            or_(UserRole.valid_from.is_(None), UserRole.valid_from <= now),
            or_(UserRole.valid_to.is_(None), UserRole.valid_to > now),
        )
    )
    return set((await session.execute(stmt)).scalars().all())


async def permission_holders(
    session: AsyncSession,
    perm: str,
    target_org_unit_id: int | None,
    *,
    now: datetime | None = None,
) -> list[tuple[int, int | None]]:
    """The inverse of :func:`authorize_scoped`: ``(user_id, grant_org_unit_id)``
    pairs of live, active users who currently hold ``perm`` covering
    ``target_org_unit_id``. A scoped grant qualifies when its unit sits on the
    target's ancestry path; global grants are returned with ``None`` as the unit
    (callers decide whether global holders count — work-management holder
    resolution ignores them so ``system_admin`` never becomes "the" holder).
    Honors the grant validity window and ``core_users.is_active``. Ranking is
    caller policy; pairs come back deduplicated, ordered by ``user_id``."""
    now = now or utc_now()
    covered = (
        await ancestors_or_self(session, target_org_unit_id)
        if target_org_unit_id is not None
        else []
    )
    scope_clause = UserRole.org_unit_id.is_(None)
    if covered:
        scope_clause = or_(
            UserRole.org_unit_id.is_(None), UserRole.org_unit_id.in_(covered)
        )
    stmt = (
        select(UserRole.user_id, UserRole.org_unit_id)
        .join(RolePermission, RolePermission.role_id == UserRole.role_id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .join(User, User.id == UserRole.user_id)
        .where(
            Permission.code == perm,
            User.is_active.is_(True),
            or_(UserRole.valid_from.is_(None), UserRole.valid_from <= now),
            or_(UserRole.valid_to.is_(None), UserRole.valid_to > now),
            scope_clause,
        )
        .distinct()
        .order_by(UserRole.user_id, UserRole.org_unit_id)
    )
    return [(uid, unit) for uid, unit in (await session.execute(stmt)).all()]


async def authorize_scoped(
    session: AsyncSession,
    user_id: int,
    perm: str,
    target_org_unit_id: int | None,
) -> bool:
    """True if ``user_id`` may exercise ``perm`` against ``target_org_unit_id`` —
    holds it globally, or via a scoped grant whose unit covers (is an
    ancestor-or-self of) the target. A global grant authorizes anywhere; with no
    grant, or a scoped-only grant that does not cover the target, it is denied."""
    scopes = await scoped_org_units(session, user_id, perm)
    if not scopes:
        return False
    if None in scopes:  # a global grant of this permission
        return True
    if target_org_unit_id is None:
        return False  # scoped-only grant, but the request has no unit to cover
    covered = set(await ancestors_or_self(session, target_org_unit_id))
    return bool({s for s in scopes if s is not None} & covered)
