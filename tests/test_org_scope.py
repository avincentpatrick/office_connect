"""B3: org-unit ancestry walk + org-scoped authorization."""

import secrets

from sqlalchemy import select

from office_connect.core.models import OrgUnit, Role, UserRole
from office_connect.core.org_units import (
    ancestors_or_self,
    authorize_scoped,
    descendants_or_self,
)
from office_connect.core.time import utc_now

APPROVE = "reimb.claim.approve"


async def _mk_org(session, kind, parent_id=None):
    ou = OrgUnit(
        code=f"ou-{secrets.token_hex(4)}",
        name=kind.title(),
        kind=kind,
        parent_org_unit_id=parent_id,
    )
    session.add(ou)
    await session.flush()
    return ou


async def _approver_role_id(session):
    return (
        await session.execute(select(Role).where(Role.code == "approver"))
    ).scalar_one().id


async def test_ancestors_or_self_walks_to_root(app_session):
    office = await _mk_org(app_session, "office")
    div = await _mk_org(app_session, "division", office.id)
    sec = await _mk_org(app_session, "section", div.id)
    await app_session.commit()
    assert set(await ancestors_or_self(app_session, sec.id)) == {
        sec.id,
        div.id,
        office.id,
    }
    assert await ancestors_or_self(app_session, None) == []


async def test_scoped_grant_covers_subtree_denies_siblings(
    app_session, seed_rbac, make_user
):
    office = await _mk_org(app_session, "office")
    div1 = await _mk_org(app_session, "division", office.id)
    sec1 = await _mk_org(app_session, "section", div1.id)
    div2 = await _mk_org(app_session, "division", office.id)
    sec2 = await _mk_org(app_session, "section", div2.id)
    user, _ = await make_user()
    # "Approver OF div1".
    app_session.add(
        UserRole(
            user_id=user.id,
            role_id=await _approver_role_id(app_session),
            org_unit_id=div1.id,
        )
    )
    await app_session.commit()

    assert await authorize_scoped(app_session, user.id, APPROVE, sec1.id) is True
    assert await authorize_scoped(app_session, user.id, APPROVE, div1.id) is True
    # A sibling subtree is NOT covered by a div1-scoped grant.
    assert await authorize_scoped(app_session, user.id, APPROVE, sec2.id) is False


async def test_global_grant_authorizes_anywhere(app_session, seed_rbac, make_user):
    office = await _mk_org(app_session, "office")
    div = await _mk_org(app_session, "division", office.id)
    user, _ = await make_user()
    app_session.add(
        UserRole(
            user_id=user.id,
            role_id=await _approver_role_id(app_session),
            org_unit_id=None,  # global
        )
    )
    await app_session.commit()
    assert await authorize_scoped(app_session, user.id, APPROVE, div.id) is True
    assert await authorize_scoped(app_session, user.id, APPROVE, None) is True


async def test_no_grant_is_denied(app_session, seed_rbac, make_user):
    user, _ = await make_user()
    assert await authorize_scoped(app_session, user.id, APPROVE, None) is False


# --- R-7-queue: the inverse walk ------------------------------------------
# `ancestors_or_self` answers "may this actor act on THIS request". A LIST
# endpoint asks it backwards — "which requests may this actor see" — and that
# is the subtree closure of their grants, in one query rather than one per row.


async def test_descendants_or_self_walks_the_whole_subtree(app_session):
    office = await _mk_org(app_session, "office")
    div1 = await _mk_org(app_session, "division", office.id)
    sec1 = await _mk_org(app_session, "section", div1.id)
    div2 = await _mk_org(app_session, "division", office.id)
    await app_session.commit()

    assert await descendants_or_self(app_session, [div1.id]) == {div1.id, sec1.id}
    # From the root, everything.
    assert await descendants_or_self(app_session, [office.id]) == {
        office.id,
        div1.id,
        sec1.id,
        div2.id,
    }
    # A leaf is its own closure.
    assert await descendants_or_self(app_session, [sec1.id]) == {sec1.id}


async def test_descendants_or_self_unions_multiple_roots(app_session):
    """Two scoped grants are one scope, not two queries — and an overlapping
    pair must not double-count or drop anything."""
    office = await _mk_org(app_session, "office")
    div1 = await _mk_org(app_session, "division", office.id)
    sec1 = await _mk_org(app_session, "section", div1.id)
    div2 = await _mk_org(app_session, "division", office.id)
    await app_session.commit()

    assert await descendants_or_self(app_session, [div1.id, div2.id]) == {
        div1.id,
        sec1.id,
        div2.id,
    }
    # Overlapping roots (parent + its own child) collapse cleanly.
    assert await descendants_or_self(app_session, [div1.id, sec1.id]) == {
        div1.id,
        sec1.id,
    }
    assert await descendants_or_self(app_session, []) == set()


async def test_a_soft_deleted_unit_stops_the_walk(app_session):
    """A disbanded division must not drag its children back into someone's
    scope — the same rule ``ancestors_or_self`` applies walking up."""
    office = await _mk_org(app_session, "office")
    div = await _mk_org(app_session, "division", office.id)
    sec = await _mk_org(app_session, "section", div.id)
    div.deleted_at = utc_now()
    await app_session.commit()

    reachable = await descendants_or_self(app_session, [office.id])
    assert div.id not in reachable
    assert sec.id not in reachable
    assert reachable == {office.id}
