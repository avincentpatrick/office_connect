"""Shared builders for the workflow-engine tests.

Keeps each test focused on one behavior: a standard reimbursement-shaped chain
(draft → for_approval → approved, plus return/reject/cancel/resubmit) authored +
published through the real ``core.workflow`` authoring API, and small helpers for org
units + scoped role grants. Nothing here is production code — it exercises the engine
exactly as R-4-app will drive it.
"""

from __future__ import annotations

import secrets
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import select

from office_connect.core.models import OrgUnit, Role, UserRole
from office_connect.core import workflow as wf

APPROVE_PERM = "reimb.claim.approve"


async def build_chain(
    session,
    *,
    code: str | None = None,
    module: str | None = None,
    approve_permission: str | None = APPROVE_PERM,
    enforce_segregation: bool = False,
    sla_hours: int | None = None,
    step_count: int = 1,
    join_type: str = "all",
    quorum_count: int | None = None,
    amount_split: bool = False,
    publish: bool = True,
):
    """Author (and by default publish) a standard chain; return a namespace with the
    definition, version, and a ``states`` dict keyed by state code."""
    code = code or f"wf.test.{secrets.token_hex(4)}"
    definition = await wf.create_definition(
        session, code=code, name=code, module=module
    )
    version = await wf.create_version(session, definition=definition)

    s = {}
    s["draft"] = await wf.add_state(
        session, version=version, code="draft", name="Draft", kind="initial",
        sort_order=0,
    )
    s["for_approval"] = await wf.add_state(
        session, version=version, code="for_approval", name="For Approval",
        kind="normal", sort_order=1, is_approval_gate=True,
        required_permission=approve_permission, join_type=join_type,
        step_count=step_count, quorum_count=quorum_count, sla_hours=sla_hours,
        enforce_segregation=enforce_segregation,
    )
    s["approved"] = await wf.add_state(
        session, version=version, code="approved", name="Approved", kind="terminal",
        sort_order=2,
    )
    s["returned"] = await wf.add_state(
        session, version=version, code="returned", name="Returned", kind="normal",
        sort_order=3,
    )
    s["rejected"] = await wf.add_state(
        session, version=version, code="rejected", name="Rejected", kind="terminal",
        sort_order=4,
    )
    s["cancelled"] = await wf.add_state(
        session, version=version, code="cancelled", name="Cancelled",
        kind="terminal", sort_order=5,
    )

    await wf.add_transition(
        session, version=version, from_state=s["draft"], to_state=s["for_approval"],
        action="submit",
    )
    await wf.add_transition(
        session, version=version, from_state=s["draft"], to_state=s["cancelled"],
        action="cancel",
    )
    if amount_split:
        s["for_director"] = await wf.add_state(
            session, version=version, code="for_director", name="For Director",
            kind="normal", sort_order=6, is_approval_gate=True,
            required_permission=approve_permission,
        )
        await wf.add_transition(
            session, version=version, from_state=s["for_approval"],
            to_state=s["approved"], action="approve", sort_order=0,
            max_amount=Decimal("1000.00"),
        )
        await wf.add_transition(
            session, version=version, from_state=s["for_approval"],
            to_state=s["for_director"], action="approve", sort_order=1,
            min_amount=Decimal("1000.01"),
        )
        await wf.add_transition(
            session, version=version, from_state=s["for_director"],
            to_state=s["approved"], action="approve",
        )
    else:
        await wf.add_transition(
            session, version=version, from_state=s["for_approval"],
            to_state=s["approved"], action="approve",
        )
    await wf.add_transition(
        session, version=version, from_state=s["for_approval"],
        to_state=s["returned"], action="return", requires_comment=True,
    )
    await wf.add_transition(
        session, version=version, from_state=s["for_approval"],
        to_state=s["rejected"], action="reject", requires_comment=True,
    )
    await wf.add_transition(
        session, version=version, from_state=s["returned"],
        to_state=s["for_approval"], action="resubmit",
    )
    await wf.add_transition(
        session, version=version, from_state=s["returned"],
        to_state=s["cancelled"], action="cancel",
    )

    if publish:
        await wf.publish_version(session, version=version)
    await session.flush()
    return SimpleNamespace(definition=definition, version=version, states=s)


async def make_org_unit(session, *, code=None, kind="division", parent=None) -> OrgUnit:
    code = code or f"ou-{secrets.token_hex(4)}"
    ou = OrgUnit(
        code=code,
        name=code,
        kind=kind,
        parent_org_unit_id=parent.id if parent else None,
    )
    session.add(ou)
    await session.flush()
    return ou


async def grant_scoped_role(
    session, *, user, role_code: str, org_unit_id: int | None = None
) -> UserRole:
    """Link ``user`` to an existing role (created by seed_rbac) with an org scope."""
    role = (
        await session.execute(select(Role).where(Role.code == role_code))
    ).scalar_one()
    ur = UserRole(user_id=user.id, role_id=role.id, org_unit_id=org_unit_id)
    session.add(ur)
    await session.flush()
    return ur
