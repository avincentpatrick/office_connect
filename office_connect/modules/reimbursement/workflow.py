"""The ``reimbursement.claim`` workflow definition — authored on the shared engine.

Rule 10 in action: the signatory chain IS the workflow definition (the R-1
decision that dropped ``reimb_approval_steps``/``reimb_signatory_configs``).
v1 authors the spec §5.5 role chain — Division Chief approve → Admin Officer
review → hand to FMS — mapped onto the spec §6.1 status machine:

    draft ─submit→ division_approval ─approve→ admin_review ─approve→
    handed_to_fms ─approve→ paid_closed
    (every gate ─return→ … loops toward the claimant; returned ─resubmit→
    re-enters at division_approval with a fresh revision)

Deliberate deltas (module doc §2): NO ``reject`` (spec §6.1 has only
Return/Cancel); NO amount-tier guards yet (DOH DO 2019-0225 unobtained — the
tiered chain lands as an authored v2; versioned definitions make that clean);
FMS sub-statuses ride ``reimb_external_events`` at R-7, not extra states;
``sla_hours`` stays None — the lifecycle service stamps working-day due dates
(spec §7.4 counts WORKING days; the engine column is calendar hours).

Two engine facts shape the authoring (verified R-4-app kickoff):
- A permission-less originator transition is an OPEN GATE to any user
  (``_authorize_originator`` falls through to ``resolve_authority``, which
  authorizes ``None``). Every submit/resubmit/cancel transition therefore
  carries ``reimb.claim.review`` — the owner still passes first via the
  originator check, and Admin Officers gain the spec §3.2 assist lane.
- Approve authorizes on the STEP's pinned permission (from the STATE); a gate
  state without ``required_permission`` would be an open gate at execute time.
  ``_assert_graph_invariants`` refuses to publish such a graph.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core import workflow as wf
from office_connect.core.models import (
    WorkflowDefinition,
    WorkflowDefinitionVersion,
    WorkflowState,
    WorkflowTransition,
)
DEFINITION_CODE = "reimbursement.claim"
SUBJECT_KIND = "reimb.claim"
FEATURE_FLAG_KEY = "module.reimbursement"

# Must come AFTER the identity constants: importing ``services`` pulls in
# lifecycle/notify, which import those constants back from this (then still
# partially initialized) module — e.g. when ops.bootstrap imports us first.
from office_connect.modules.reimbursement.services import status as st

# Gate permissions — pinned on the STATE (execute-time authz), never only on a
# transition. division_approval + admin_review enforce segregation (COA 92-389:
# the claimant can never clear their own gate; distinct person per gate).
APPROVE_PERM = "reimb.claim.approve"
REVIEW_PERM = "reimb.claim.review"
FMS_PERM = "reimb.claim.fms_update"

# The closed set of actions this definition may author — ``reject`` is absent by
# spec §6.1 decision, ``escalate`` because the engine routes it as an originator
# action (unhandled by either branch); authoring it would be a latent trap.
_AUTHORED_ACTIONS = frozenset({"submit", "approve", "return", "cancel", "resubmit"})


def _assert_graph_invariants(
    states: list[WorkflowState], transitions: list[WorkflowTransition]
) -> None:
    """Seed-time self-checks beyond ``validate_graph`` (developer errors, so
    ``RuntimeError`` like ``apply_rbac_grants``): no open gates, no stray verbs,
    and the status vocabulary covers every authored state."""
    for s in states:
        if s.is_approval_gate and not s.required_permission:
            raise RuntimeError(
                f"gate state '{s.code}' has no required_permission — an open "
                "gate at execute time (authz bypass)."
            )
    for t in transitions:
        if t.action not in _AUTHORED_ACTIONS:
            raise RuntimeError(
                f"transition action '{t.action}' is outside the authored set "
                f"{sorted(_AUTHORED_ACTIONS)}."
            )
    authored_codes = {s.code for s in states}
    if authored_codes != set(st.ALL_STATES):
        raise RuntimeError(
            "status vocabulary drift: authored states "
            f"{sorted(authored_codes)} != services.status.ALL_STATES "
            f"{sorted(st.ALL_STATES)}."
        )


async def ensure_claim_definition(
    session: AsyncSession,
) -> WorkflowDefinitionVersion:
    """Idempotently author + publish v1 of ``reimbursement.claim``.

    Keyed on ``get_published_version`` — a re-run NEVER mints a new version
    (a chain change is an explicit, authored v2, e.g. the DO 2019-0225 tiered
    chain). Flushes; the caller owns the commit."""
    existing = await wf.get_published_version(session, DEFINITION_CODE)
    if existing is not None:
        return existing

    definition = (
        (
            await session.execute(
                select(WorkflowDefinition).where(
                    WorkflowDefinition.code == DEFINITION_CODE
                )
            )
        )
        .scalars()
        .first()
    )
    if definition is None:
        definition = await wf.create_definition(
            session,
            code=DEFINITION_CODE,
            name="Local Travel Reimbursement — claim",
            module=FEATURE_FLAG_KEY,
            description=(
                "Spec §6.1 status machine on the §5.5 role chain: Division "
                "Chief approve → Admin Officer review → FMS. Amount tiers "
                "deferred (DOH DO 2019-0225) — v2 when obtained."
            ),
        )
    version = await wf.create_version(
        session, definition=definition, resubmit_policy="restart"
    )

    s: dict[str, WorkflowState] = {}
    s[st.DRAFT] = await wf.add_state(
        session, version=version, code=st.DRAFT,
        name=st.STATUS_LABELS[st.DRAFT], kind="initial", sort_order=0,
    )
    s[st.DIVISION_APPROVAL] = await wf.add_state(
        session, version=version, code=st.DIVISION_APPROVAL,
        name=st.STATUS_LABELS[st.DIVISION_APPROVAL], kind="normal", sort_order=1,
        is_approval_gate=True, required_permission=APPROVE_PERM,
        enforce_segregation=True,
    )
    s[st.ADMIN_REVIEW] = await wf.add_state(
        session, version=version, code=st.ADMIN_REVIEW,
        name=st.STATUS_LABELS[st.ADMIN_REVIEW], kind="normal", sort_order=2,
        is_approval_gate=True, required_permission=REVIEW_PERM,
        enforce_segregation=True,
    )
    s[st.HANDED_TO_FMS] = await wf.add_state(
        session, version=version, code=st.HANDED_TO_FMS,
        name=st.STATUS_LABELS[st.HANDED_TO_FMS], kind="normal", sort_order=3,
        is_approval_gate=True, required_permission=FMS_PERM,
    )
    s[st.FMS_RETURNED] = await wf.add_state(
        session, version=version, code=st.FMS_RETURNED,
        name=st.STATUS_LABELS[st.FMS_RETURNED], kind="normal", sort_order=4,
        is_approval_gate=True, required_permission=REVIEW_PERM,
    )
    s[st.RETURNED] = await wf.add_state(
        session, version=version, code=st.RETURNED,
        name=st.STATUS_LABELS[st.RETURNED], kind="normal", sort_order=5,
    )
    s[st.PAID_CLOSED] = await wf.add_state(
        session, version=version, code=st.PAID_CLOSED,
        name=st.STATUS_LABELS[st.PAID_CLOSED], kind="terminal", sort_order=6,
    )
    s[st.CANCELLED] = await wf.add_state(
        session, version=version, code=st.CANCELLED,
        name=st.STATUS_LABELS[st.CANCELLED], kind="terminal", sort_order=7,
    )

    transitions = [
        await wf.add_transition(
            session, version=version, from_state=s[st.DRAFT],
            to_state=s[st.DIVISION_APPROVAL], action="submit",
            required_permission=REVIEW_PERM,
        ),
        # Unreachable at runtime (instances are created AT submit); kept for
        # spec §6.1 fidelity and for a future create-time-instance world.
        await wf.add_transition(
            session, version=version, from_state=s[st.DRAFT],
            to_state=s[st.CANCELLED], action="cancel",
            requires_comment=True, required_permission=REVIEW_PERM,
        ),
        await wf.add_transition(
            session, version=version, from_state=s[st.DIVISION_APPROVAL],
            to_state=s[st.ADMIN_REVIEW], action="approve",
        ),
        await wf.add_transition(
            session, version=version, from_state=s[st.DIVISION_APPROVAL],
            to_state=s[st.RETURNED], action="return", requires_comment=True,
        ),
        await wf.add_transition(
            session, version=version, from_state=s[st.ADMIN_REVIEW],
            to_state=s[st.HANDED_TO_FMS], action="approve",
        ),
        await wf.add_transition(
            session, version=version, from_state=s[st.ADMIN_REVIEW],
            to_state=s[st.RETURNED], action="return", requires_comment=True,
        ),
        await wf.add_transition(
            session, version=version, from_state=s[st.HANDED_TO_FMS],
            to_state=s[st.PAID_CLOSED], action="approve",
        ),
        await wf.add_transition(
            session, version=version, from_state=s[st.HANDED_TO_FMS],
            to_state=s[st.FMS_RETURNED], action="return", requires_comment=True,
        ),
        await wf.add_transition(
            session, version=version, from_state=s[st.FMS_RETURNED],
            to_state=s[st.RETURNED], action="return", requires_comment=True,
        ),
        await wf.add_transition(
            session, version=version, from_state=s[st.RETURNED],
            to_state=s[st.DIVISION_APPROVAL], action="resubmit",
            required_permission=REVIEW_PERM,
        ),
        await wf.add_transition(
            session, version=version, from_state=s[st.RETURNED],
            to_state=s[st.CANCELLED], action="cancel",
            requires_comment=True, required_permission=REVIEW_PERM,
        ),
    ]

    _assert_graph_invariants(list(s.values()), transitions)
    await wf.publish_version(session, version=version)
    await session.flush()
    return version
