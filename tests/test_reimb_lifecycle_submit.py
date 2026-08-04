"""R-4-app QA gate: ``submit_claim`` — the atomic first-submit transaction.

Totals + RB reference + workflow instance + status mirror commit (or roll
back) together; the claim-row lock serializes the double-submit race; the
feature flag blocks BEFORE a reference number is burned; owner-only submit
guards segregation's maker identity.
"""

import asyncio
import re
from decimal import Decimal

import pytest
from sqlalchemy import select

from office_connect.core.api.errors import APIError
from office_connect.core.db import SessionLocal
from office_connect.core.models import (
    WorkflowDefinition,
    WorkflowDefinitionVersion,
    WorkflowInstance,
    WorkflowStep,
)
from office_connect.modules.reimbursement.models import ReimbClaim, ReimbStatusHistory
from office_connect.modules.reimbursement.services import status as st
from office_connect.modules.reimbursement.services.lifecycle import (
    claim_action,
    submit_claim,
)
from office_connect.modules.reimbursement.workflow import SUBJECT_KIND
from tests.reimb_lifecycle_helpers import (
    return_reason_ids,
    standard_cast,
    trip_claim,
)
from tests.reimbursement_helpers import make_staff


async def test_submit_happy_path(app_session, seed_rbac, make_user, reimb_flag_on):
    cast = await standard_cast(app_session, make_user)
    claim = await submit_claim(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id
    )
    await app_session.commit()

    assert re.fullmatch(r"RB-\d{4}-\d{4}", claim.ref_no)
    assert claim.totals["grand"] == "6500.00"
    assert claim.status == st.DIVISION_APPROVAL
    assert claim.next_action == "Approve or return"
    assert (claim.holder_kind, claim.holder_id) == ("user", cast.approver.id)
    assert claim.holder_since is not None

    instance = await app_session.get(WorkflowInstance, claim.workflow_instance_id)
    assert (instance.subject_kind, instance.subject_id) == (SUBJECT_KIND, claim.id)
    assert instance.org_unit_id == cast.division.id
    assert instance.originator_user_id == cast.owner.id
    assert instance.amount == Decimal("6500.00")

    history = (
        await app_session.execute(
            select(ReimbStatusHistory).where(
                ReimbStatusHistory.claim_id == claim.id
            )
        )
    ).scalars().all()
    assert [(h.from_status, h.to_status) for h in history] == [
        (st.DRAFT, st.DIVISION_APPROVAL)
    ]


async def test_submit_flag_off_blocks_before_burning_a_ref(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    cast = await standard_cast(app_session, make_user)
    claim_id, owner_id = cast.claim.id, cast.owner.id  # pre-rollback (expiry)
    await app_session.commit()  # the claim must survive the failed-submit rollback
    reimb_flag_on.enabled = False
    await app_session.flush()

    with pytest.raises(APIError) as ei:
        await submit_claim(app_session, claim_id=claim_id, actor_user_id=owner_id)
    assert ei.value.code == "workflow_module_disabled"
    await app_session.rollback()

    fresh = await app_session.get(ReimbClaim, claim_id)
    assert fresh.ref_no is None  # the flag fires before allocation — no burn
    assert fresh.workflow_instance_id is None
    assert fresh.status is None


async def test_flag_off_lets_in_flight_finish(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    cast = await standard_cast(app_session, make_user)
    await submit_claim(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id
    )
    reimb_flag_on.enabled = False
    await app_session.flush()

    # New submissions are blocked, but execute_action never reads the flag.
    claim = await claim_action(
        app_session, claim_id=cast.claim.id, action="approve",
        actor_user_id=cast.approver.id,
    )
    assert claim.status == st.ADMIN_REVIEW


async def test_double_submit_race_burns_one_ref(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    cast = await standard_cast(app_session, make_user)
    claim_id, owner_id = cast.claim.id, cast.owner.id
    await app_session.commit()  # both racers need committed rows

    async def _try(session_label: str) -> str:
        async with SessionLocal() as session:
            try:
                await submit_claim(
                    session, claim_id=claim_id, actor_user_id=owner_id
                )
                await session.commit()
                return "ok"
            except APIError as exc:
                await session.rollback()
                return exc.code

    results = await asyncio.gather(_try("a"), _try("b"))
    assert sorted(results) == ["ok", "reimb_claim_already_submitted"], results

    async with SessionLocal() as check:
        fresh = await check.get(ReimbClaim, claim_id)
        instances = (
            await check.execute(
                select(WorkflowInstance).where(
                    WorkflowInstance.subject_kind == SUBJECT_KIND,
                    WorkflowInstance.subject_id == claim_id,
                )
            )
        ).scalars().all()
        assert len(instances) == 1  # no orphaned ghost instance
        assert fresh.workflow_instance_id == instances[0].id


async def test_submit_is_owner_only(app_session, seed_rbac, make_user, reimb_flag_on):
    cast = await standard_cast(app_session, make_user)
    outsider, _ = await make_user(roles=("staff",))
    with pytest.raises(APIError) as ei:
        await submit_claim(
            app_session, claim_id=cast.claim.id, actor_user_id=outsider.id
        )
    assert ei.value.code == "reimb_not_claim_owner"
    await app_session.rollback()


async def test_submit_fails_closed_without_org_unit(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    cast = await standard_cast(app_session, make_user)
    unplaced = await make_staff(app_session)  # no division/section
    owner, _ = await make_user(roles=("staff",), staff_id=unplaced.id)
    claim = await trip_claim(app_session, staff=unplaced)
    with pytest.raises(APIError) as ei:
        await submit_claim(app_session, claim_id=claim.id, actor_user_id=owner.id)
    assert ei.value.code == "reimb_claimant_no_org_unit"
    await app_session.rollback()


async def test_submit_routes_a_liquidation_onto_its_own_chain(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """R-6-liq-chain reverses R-4-app's refusal: a liquidation is no longer an
    unsupported kind, it is a kind with its own definition and its own number
    series. Submitting one must land on ``certify_b`` with an ``LQ-`` ref, never
    on the claim chain's ``division_approval`` with an ``RB-``."""
    cast = await standard_cast(app_session, make_user)
    # trip_claim(packet=True) satisfies whatever THIS kind's catalog blocks on,
    # which is the liquidation set — the checklist engine was already kind-aware.
    liq = await trip_claim(app_session, staff=cast.staff, kind="liquidation")

    claim = await submit_claim(
        app_session, claim_id=liq.id, actor_user_id=cast.owner.id
    )
    assert claim.status == "certify_b"
    assert claim.ref_no.startswith("LQ-")

    instance = await app_session.get(WorkflowInstance, claim.workflow_instance_id)
    version = await app_session.get(
        WorkflowDefinitionVersion, instance.definition_version_id
    )
    definition = await app_session.get(WorkflowDefinition, version.definition_id)
    assert definition.code == "reimbursement.liquidation"
    await app_session.rollback()


async def test_resubmit_keeps_ref_bumps_revision(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    cast = await standard_cast(app_session, make_user)
    claim = await submit_claim(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id
    )
    ref = claim.ref_no
    await claim_action(
        app_session, claim_id=claim.id, action="return",
        actor_user_id=cast.approver.id, comment="Missing boarding pass.",
        reason_ids=await return_reason_ids(app_session),
    )
    assert claim.status == st.RETURNED
    assert (claim.holder_kind, claim.holder_id) == ("user", cast.owner.id)

    await claim_action(
        app_session, claim_id=claim.id, action="resubmit",
        actor_user_id=cast.owner.id,
    )
    instance = await app_session.get(WorkflowInstance, claim.workflow_instance_id)
    assert claim.status == st.DIVISION_APPROVAL
    assert claim.ref_no == ref  # a reference number is allocated ONCE, ever
    assert instance.revision_no == 2  # resubmit restarts the chain (spec §7.6)
    assert instance.amount == Decimal("6500.00")  # recomputed pre-route

    fresh_steps = (
        await app_session.execute(
            select(WorkflowStep).where(
                WorkflowStep.instance_id == instance.id,
                WorkflowStep.revision_no == 2,
                WorkflowStep.status == "active",
            )
        )
    ).scalars().all()
    assert len(fresh_steps) == 1  # fresh fan-in — approvals never carry over
