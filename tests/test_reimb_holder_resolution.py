"""R-4-app QA gate: deterministic holder resolution (the work-management pointer).

The holder is never an authorization decision — it is whose inbox/ladder the
item lands in. Rules pinned here: scoped grants only (a global grant — e.g.
system_admin's — never makes someone "the" holder), nearest org unit wins,
lowest user id tie-break, originator excluded under segregation, zero-match
fails CLOSED (the transition refuses; no null holder can ever be written).
"""

import pytest

from office_connect.core.api.errors import APIError
from office_connect.core.models import WorkflowState
from office_connect.modules.reimbursement.services import status as st
from office_connect.modules.reimbursement.services.lifecycle import (
    resolve_holder,
    submit_claim,
)
from tests.reimb_lifecycle_helpers import ensure_reimb_workflow, trip_claim
from tests.reimbursement_helpers import make_staff
from tests.workflow_helpers import grant_scoped_role, make_org_unit


async def _setup(app_session, make_user, *, division_approvers=(), office_approvers=()):
    """Office → division tree + a submittable claim; approvers granted per the
    caller's scoping spec. Returns (office, division, owner, claim)."""
    office = await make_org_unit(app_session, kind="office")
    division = await make_org_unit(app_session, kind="division", parent=office)
    staff = await make_staff(app_session, division_id=division.id)
    owner, _ = await make_user(roles=("staff",), staff_id=staff.id)
    for user in division_approvers:
        await grant_scoped_role(
            app_session, user=user, role_code="approver", org_unit_id=division.id
        )
    for user in office_approvers:
        await grant_scoped_role(
            app_session, user=user, role_code="approver", org_unit_id=office.id
        )
    await ensure_reimb_workflow(app_session)
    claim = await trip_claim(app_session, staff=staff)
    return office, division, owner, claim


async def test_deepest_scope_wins(app_session, seed_rbac, make_user, reimb_flag_on):
    near, _ = await make_user()
    far, _ = await make_user()
    _, _, owner, claim = await _setup(
        app_session, make_user,
        division_approvers=(near,), office_approvers=(far,),
    )
    submitted = await submit_claim(
        app_session, claim_id=claim.id, actor_user_id=owner.id
    )
    assert submitted.holder_id == near.id  # division beats office


async def test_lowest_user_id_breaks_ties(app_session, seed_rbac, make_user, reimb_flag_on):
    first, _ = await make_user()
    second, _ = await make_user()
    _, _, owner, claim = await _setup(
        app_session, make_user, division_approvers=(first, second),
    )
    submitted = await submit_claim(
        app_session, claim_id=claim.id, actor_user_id=owner.id
    )
    assert submitted.holder_id == min(first.id, second.id)


async def test_zero_match_fails_closed(app_session, seed_rbac, make_user, reimb_flag_on):
    """No scoped approver anywhere on the path → the SUBMIT refuses. The
    invariant holds by refusing the move, never by writing a null holder."""
    _, _, owner, claim = await _setup(app_session, make_user)
    with pytest.raises(APIError) as ei:
        await submit_claim(app_session, claim_id=claim.id, actor_user_id=owner.id)
    assert ei.value.code == "reimb_no_eligible_holder"
    await app_session.rollback()


async def test_global_grants_never_hold(app_session, seed_rbac, make_user, reimb_flag_on):
    """A GLOBAL approver grant (system_admin's shape) can still ACT — but is
    never resolved as the holder; with only global holders, submit refuses."""
    global_approver, _ = await make_user(roles=("approver",))  # unscoped grant
    _, _, owner, claim = await _setup(app_session, make_user)
    with pytest.raises(APIError) as ei:
        await submit_claim(app_session, claim_id=claim.id, actor_user_id=owner.id)
    assert ei.value.code == "reimb_no_eligible_holder"
    await app_session.rollback()


async def test_claimant_without_login_falls_back_to_originator(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """A claimant with no ``core_users`` row (most plantilla staff never log
    in): claimant-held states fall back to the instance originator so the
    holder is still a person. Unit-level — transient objects, no engine."""
    from types import SimpleNamespace

    staff = await make_staff(app_session)  # no linked user
    claim = await trip_claim(app_session, staff=staff)
    state = WorkflowState(code=st.RETURNED, kind="normal")
    instance = SimpleNamespace(originator_user_id=4242, org_unit_id=None)

    kind, holder_id = await resolve_holder(
        app_session, state=state, claim=claim, instance=instance
    )
    assert (kind, holder_id) == ("user", 4242)


async def test_external_and_terminal_holders(app_session, seed_rbac, make_user, reimb_flag_on):
    from types import SimpleNamespace

    staff = await make_staff(app_session)
    claim = await trip_claim(app_session, staff=staff)
    instance = SimpleNamespace(originator_user_id=1, org_unit_id=None)

    kind, holder_id = await resolve_holder(
        app_session,
        state=WorkflowState(code=st.HANDED_TO_FMS, kind="normal"),
        claim=claim, instance=instance,
    )
    assert (kind, holder_id) == ("external_fms", None)

    kind, holder_id = await resolve_holder(
        app_session,
        state=WorkflowState(code=st.PAID_CLOSED, kind="terminal"),
        claim=claim, instance=instance,
    )
    assert (kind, holder_id) == (None, None)
