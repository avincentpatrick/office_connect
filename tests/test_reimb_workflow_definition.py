"""R-4-app QA gate: the ``reimbursement.claim`` definition seeder.

The authored graph IS the signatory chain (Rule 10) — these tests pin its exact
shape: spec §5.5 role chain on the §6.1 machine, NO reject, NO amount guards
(DO 2019-0225 deferral), comments on the return/cancel TRANSITIONS (the engine
never reads the destination state's flag), review permission on every
originator transition (a permission-less one is an open gate to any user), and
gate permissions on the STATES (execute-time authz pins the step from there).
"""

from sqlalchemy import select

from office_connect.core.models import WorkflowDefinitionVersion, WorkflowDefinition, WorkflowState, WorkflowTransition
from office_connect.modules.reimbursement.services import status as st
from office_connect.modules.reimbursement.workflow import (
    APPROVE_PERM,
    DEFINITION_CODE,
    FMS_PERM,
    REVIEW_PERM,
    ensure_claim_definition,
)
from tests.reimb_lifecycle_helpers import ensure_reimb_workflow


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


async def test_seeder_publishes_once_and_is_idempotent(app_session):
    v1 = await ensure_reimb_workflow(app_session)
    v2 = await ensure_claim_definition(app_session)
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
                WorkflowDefinition.code == DEFINITION_CODE,
                WorkflowDefinitionVersion.is_published.is_(True),
            )
        )
    ).scalars().all()
    assert len(published) == 1  # a re-run NEVER mints a new version


async def test_states_shape(app_session):
    version = await ensure_reimb_workflow(app_session)
    states, _ = await _graph(app_session, version.id)

    assert set(states) == set(st.REIMBURSEMENT.all_states)
    assert states[st.DRAFT].kind == "initial"
    assert {c for c, s in states.items() if s.kind == "terminal"} == {
        st.PAID_CLOSED,
        st.CANCELLED,
    }

    gates = {c: s for c, s in states.items() if s.is_approval_gate}
    assert {c: s.required_permission for c, s in gates.items()} == {
        st.DIVISION_APPROVAL: APPROVE_PERM,
        st.ADMIN_REVIEW: REVIEW_PERM,
        st.HANDED_TO_FMS: FMS_PERM,
        st.FMS_RETURNED: REVIEW_PERM,
    }
    # Segregation on the two human review gates only (COA 92-389); the FMS
    # gates route paperwork, they are not certifications.
    assert {c for c, s in gates.items() if s.enforce_segregation} == {
        st.DIVISION_APPROVAL,
        st.ADMIN_REVIEW,
    }
    # Working-day SLA is module-stamped — the calendar-hours column stays unset.
    assert all(s.sla_hours is None for s in states.values())
    assert all(s.step_count == 1 and s.join_type == "all" for s in gates.values())


async def test_transitions_shape(app_session):
    version = await ensure_reimb_workflow(app_session)
    states, transitions = await _graph(app_session, version.id)
    by_id = {s.id: code for code, s in states.items()}

    triples = {(by_id[t.from_state_id], t.action, by_id[t.to_state_id]) for t in transitions}
    assert triples == {
        (st.DRAFT, "submit", st.DIVISION_APPROVAL),
        (st.DRAFT, "cancel", st.CANCELLED),
        (st.DIVISION_APPROVAL, "approve", st.ADMIN_REVIEW),
        (st.DIVISION_APPROVAL, "return", st.RETURNED),
        (st.ADMIN_REVIEW, "approve", st.HANDED_TO_FMS),
        (st.ADMIN_REVIEW, "return", st.RETURNED),
        (st.HANDED_TO_FMS, "approve", st.PAID_CLOSED),
        (st.HANDED_TO_FMS, "return", st.FMS_RETURNED),
        (st.FMS_RETURNED, "return", st.RETURNED),
        (st.RETURNED, "resubmit", st.DIVISION_APPROVAL),
        (st.RETURNED, "cancel", st.CANCELLED),
    }
    # Spec §6.1 has no reject; escalate is a latent engine trap — never authored.
    assert all(t.action not in ("reject", "escalate") for t in transitions)
    # Amount tiers are the recorded DO 2019-0225 deferral — no guards in v1.
    assert all(t.min_amount is None and t.max_amount is None for t in transitions)


async def test_comment_and_permission_pins(app_session):
    version = await ensure_reimb_workflow(app_session)
    states, transitions = await _graph(app_session, version.id)
    by_id = {s.id: code for code, s in states.items()}

    for t in transitions:
        # Reason-mandatory rides the TRANSITION (the engine ORs the CURRENT
        # state's flag, never the destination's).
        assert t.requires_comment is (t.action in ("return", "cancel")), (
            by_id[t.from_state_id], t.action,
        )
        # FLAG 1: permission-less originator transitions are open gates.
        if t.action in ("submit", "resubmit", "cancel"):
            assert t.required_permission == REVIEW_PERM
        else:
            assert t.required_permission is None  # gate authz = the state's pin


async def test_vocabulary_covers_definition(app_session):
    version = await ensure_reimb_workflow(app_session)
    states, _ = await _graph(app_session, version.id)
    # The module twin of the engine's replay consistency: mapping drift between
    # the authored graph and the status vocabulary fails loudly here.
    vocab = st.REIMBURSEMENT
    assert set(vocab.next_action) == set(states)
    assert set(vocab.labels) == set(states)
    for code, state in states.items():
        if state.kind == "terminal":
            assert vocab.next_action[code] is None
        else:
            assert vocab.next_action[code]
