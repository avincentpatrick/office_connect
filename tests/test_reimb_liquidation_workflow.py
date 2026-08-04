"""R-6-liq-chain QA gate: the ``reimbursement.liquidation`` definition seeder.

The twin of ``test_reimb_workflow_definition.py``, for the second chain. What is
worth pinning here is not that a graph exists but that the three authoring
DECISIONS survived: certification A is folded into submit, certification C
carries a mandatory comment, and no ``fms_returned`` relay state was invented.
"""

from sqlalchemy import select

from office_connect.core.models import (
    WorkflowDefinition,
    WorkflowDefinitionVersion,
    WorkflowState,
    WorkflowTransition,
)
from office_connect.modules.reimbursement.services import status as st
from office_connect.modules.reimbursement.workflow import (
    CERTIFY_PERM,
    DEFINITION_CODE,
    FMS_PERM,
    LIQUIDATION_DEFINITION_CODE,
    REVIEW_PERM,
    definition_code,
    ensure_liquidation_definition,
)
from tests.reimb_lifecycle_helpers import (
    ensure_reimb_liquidation_workflow,
    ensure_reimb_workflow,
)


async def _graph(session, version_id):
    states = {
        s.code: s
        for s in (
            await session.execute(
                select(WorkflowState).where(
                    WorkflowState.definition_version_id == version_id
                )
            )
        ).scalars()
    }
    transitions = list(
        (
            await session.execute(
                select(WorkflowTransition).where(
                    WorkflowTransition.definition_version_id == version_id
                )
            )
        ).scalars()
    )
    return states, transitions


def _by(transitions, action):
    return {(t.from_state_id, t.to_state_id): t for t in transitions if t.action == action}


async def test_seeder_publishes_once_and_is_idempotent(app_session):
    v1 = await ensure_reimb_liquidation_workflow(app_session)
    v2 = await ensure_liquidation_definition(app_session)
    await app_session.commit()
    assert v1.id == v2.id
    assert v1.is_published

    published = (
        await app_session.execute(
            select(WorkflowDefinitionVersion)
            .join(
                WorkflowDefinition,
                WorkflowDefinition.id == WorkflowDefinitionVersion.definition_id,
            )
            .where(
                WorkflowDefinition.code == LIQUIDATION_DEFINITION_CODE,
                WorkflowDefinitionVersion.is_published.is_(True),
            )
        )
    ).scalars().all()
    assert len(published) == 1  # a chain change is an explicit authored v2


async def test_the_two_chains_are_separate_definitions(app_session):
    """Two definitions, ONE subject kind — a liquidation is a ``reimb_claims``
    row like any other, so nothing about the polymorphic back-ref forks."""
    claim_version = await ensure_reimb_workflow(app_session)
    liq_version = await ensure_reimb_liquidation_workflow(app_session)
    assert claim_version.definition_id != liq_version.definition_id
    assert definition_code("reimbursement") == DEFINITION_CODE
    assert definition_code("liquidation") == LIQUIDATION_DEFINITION_CODE


async def test_states_shape(app_session):
    version = await ensure_reimb_liquidation_workflow(app_session)
    states, _ = await _graph(app_session, version.id)

    assert set(states) == set(st.LIQUIDATION.all_states)
    assert states[st.DRAFT].kind == "initial"
    assert {c for c, s in states.items() if s.kind == "terminal"} == {
        st.SETTLED,
        st.CANCELLED,
    }
    # Spec §6.2 names no FMS-returned relay: R-7 owns external tracking, and a
    # state with no screen is a state nobody can clear. If FMS turns out to
    # bounce liquidations with comments, that is definition v2.
    assert st.FMS_RETURNED not in states
    assert st.PAID_CLOSED not in states

    gates = {c: s for c, s in states.items() if s.is_approval_gate}
    assert {c: s.required_permission for c, s in gates.items()} == {
        st.CERTIFY_B: CERTIFY_PERM,
        st.CERTIFY_C: REVIEW_PERM,
        st.HANDED_TO_FMS: FMS_PERM,
    }
    # Both certifications enforce segregation (COA 92-389): the claimant made
    # the claim, so they can clear neither checker slot. The FMS gate routes
    # paperwork and is not a certification.
    assert states[st.CERTIFY_B].enforce_segregation
    assert states[st.CERTIFY_C].enforce_segregation
    assert not states[st.HANDED_TO_FMS].enforce_segregation


async def test_certification_a_is_the_submit(app_session):
    """The chain enters at ``certify_b``, not at a ``certify_a`` gate — the
    claimant is the maker and certifies BY submitting."""
    version = await ensure_reimb_liquidation_workflow(app_session)
    states, transitions = await _graph(app_session, version.id)
    submits = [t for t in transitions if t.action == "submit"]
    assert len(submits) == 1
    assert submits[0].from_state_id == states[st.DRAFT].id
    assert submits[0].to_state_id == states[st.CERTIFY_B].id


async def test_the_certification_walk_is_b_then_c_then_fms(app_session):
    version = await ensure_reimb_liquidation_workflow(app_session)
    states, transitions = await _graph(app_session, version.id)
    approves = _by(transitions, "approve")
    assert (states[st.CERTIFY_B].id, states[st.CERTIFY_C].id) in approves
    assert (states[st.CERTIFY_C].id, states[st.HANDED_TO_FMS].id) in approves
    assert (states[st.HANDED_TO_FMS].id, states[st.SETTLED].id) in approves
    # No shortcut past a certification — "A→B→C in order" is the graph's job.
    assert (states[st.CERTIFY_B].id, states[st.HANDED_TO_FMS].id) not in approves


async def test_certification_c_demands_a_comment(app_session):
    """The only approve in either chain that requires one. The Admin Officer is
    attesting to a signature made on paper by someone outside the platform, so
    the note is the ONLY record of certification C that Office-Connect holds —
    binding a frozen snapshot to the step is core-service #3's unbuilt half."""
    version = await ensure_reimb_liquidation_workflow(app_session)
    states, transitions = await _graph(app_session, version.id)
    approves = _by(transitions, "approve")
    assert approves[
        (states[st.CERTIFY_C].id, states[st.HANDED_TO_FMS].id)
    ].requires_comment
    assert not approves[
        (states[st.CERTIFY_B].id, states[st.CERTIFY_C].id)
    ].requires_comment


async def test_every_return_and_cancel_requires_a_comment(app_session):
    version = await ensure_reimb_liquidation_workflow(app_session)
    _, transitions = await _graph(app_session, version.id)
    for t in transitions:
        if t.action in ("return", "cancel"):
            assert t.requires_comment, t.action


async def test_originator_transitions_carry_a_permission(app_session):
    """A permission-less originator transition is an OPEN GATE to any user
    (the engine authorizes ``None``) — the R-4-app finding, applied here too."""
    version = await ensure_reimb_liquidation_workflow(app_session)
    _, transitions = await _graph(app_session, version.id)
    for t in transitions:
        if t.action in ("submit", "resubmit", "cancel"):
            assert t.required_permission == REVIEW_PERM
        else:
            assert t.required_permission is None  # gate authz = the state's pin


async def test_resubmit_reenters_at_the_first_certification(app_session):
    version = await ensure_reimb_liquidation_workflow(app_session)
    states, transitions = await _graph(app_session, version.id)
    resubmits = [t for t in transitions if t.action == "resubmit"]
    assert len(resubmits) == 1
    assert resubmits[0].from_state_id == states[st.RETURNED].id
    # A fixed liquidation is re-certified from the top: B never inherits a
    # decision made about the version C bounced.
    assert resubmits[0].to_state_id == states[st.CERTIFY_B].id


async def test_no_reject_and_no_stray_verbs(app_session):
    version = await ensure_reimb_liquidation_workflow(app_session)
    _, transitions = await _graph(app_session, version.id)
    actions = {t.action for t in transitions}
    assert "reject" not in actions  # spec §6.1/§6.2 have only Return/Cancel
    assert actions <= {"submit", "approve", "return", "cancel", "resubmit"}
