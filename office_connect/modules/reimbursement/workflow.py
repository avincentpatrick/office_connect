"""The module's workflow definitions — authored on the shared engine.

Rule 10 in action: the signatory chain IS the workflow definition (the R-1
decision that dropped ``reimb_approval_steps``/``reimb_signatory_configs``).
**Two definitions, one subject kind** (R-6-liq-chain): a reimbursement claim and
a liquidation are both ``reimb_claims`` rows, so ``SUBJECT_KIND`` is
``reimb.claim`` for both and the polymorphic back-ref resolves identically —
what differs is which chain the row runs, which is DATA, not a second table.

``reimbursement.claim`` v1 authors the spec §5.5 role chain — Division Chief
approve → Admin Officer review → hand to FMS — on the spec §6.1 status machine:

    draft ─submit→ division_approval ─approve→ admin_review ─approve→
    handed_to_fms ─approve→ paid_closed
    (every gate ─return→ … loops toward the claimant; returned ─resubmit→
    re-enters at division_approval with a fresh revision)

``reimbursement.liquidation`` v1 authors spec §6.2's certification chain:

    draft ─submit→ certify_b ─approve→ certify_c ─approve→
    handed_to_fms ─approve→ settled

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
LIQUIDATION_DEFINITION_CODE = "reimbursement.liquidation"
#: ONE subject kind for both definitions — the subject is a ``reimb_claims`` row
#: either way, so the sanctioned polymorphic ``(subject_kind, subject_id)`` pair
#: (workflow-standards §10) resolves without knowing which chain it runs.
SUBJECT_KIND = "reimb.claim"
FEATURE_FLAG_KEY = "module.reimbursement"

#: claim kind → the definition its instances run on. Looked up rather than
#: branched, so adding a kind is a row here plus an authoring function, and
#: ``lifecycle`` never grows a chain of ``if claim.kind ==``.
#:
#: Kind strings are literal here rather than ``st.*_KIND`` for the import-order
#: reason below — the keys are cross-checked against the status vocabularies
#: immediately after that import, so the duplication cannot silently drift.
DEFINITION_CODES: dict[str, str] = {
    "reimbursement": DEFINITION_CODE,
    "liquidation": LIQUIDATION_DEFINITION_CODE,
}


def definition_code(kind: str | None) -> str:
    """The definition code a claim of this kind runs on.

    Raises like ``_assert_graph_invariants`` on an unknown kind: starting an
    instance on a guessed chain would route real approvals to the wrong people.
    """
    try:
        return DEFINITION_CODES[kind or "reimbursement"]
    except KeyError:
        raise RuntimeError(
            f"no workflow definition for claim kind '{kind}' — "
            f"known kinds are {sorted(DEFINITION_CODES)}."
        ) from None


# Must come AFTER the identity constants AND ``definition_code``: importing
# ``services`` pulls in lifecycle/notify, which import those names back from
# this (then still partially initialized) module — e.g. when ops.bootstrap
# imports us first.
from office_connect.modules.reimbursement.services import status as st

# Every kind with a vocabulary must have a chain and vice versa — a kind with
# labels but no definition would create claims nobody can submit, and one with a
# definition but no vocabulary would render raw state codes.
if set(DEFINITION_CODES) != set(st.VOCABULARIES):
    raise RuntimeError(
        f"claim-kind drift: definitions {sorted(DEFINITION_CODES)} != "
        f"status vocabularies {sorted(st.VOCABULARIES)}."
    )

# Gate permissions — pinned on the STATE (execute-time authz), never only on a
# transition. division_approval + admin_review enforce segregation (COA 92-389:
# the claimant can never clear their own gate; distinct person per gate).
APPROVE_PERM = "reimb.claim.approve"
REVIEW_PERM = "reimb.claim.review"
FMS_PERM = "reimb.claim.fms_update"
#: Certification B — spec §5.5's "Director IV". A PERMISSION, not a role: which
#: person holds it at which org unit is grant data, and ``resolve_holder``'s
#: nearest-first ranking then picks the right one. Inventing a ``director`` role
#: would encode a chain DOH DO 2019-0225 has not confirmed (R-0 item still open).
CERTIFY_PERM = "reimb.liquidation.certify"

# The closed set of actions a definition may author — ``reject`` is absent by
# spec §6.1 decision, ``escalate`` because the engine routes it as an originator
# action (unhandled by either branch); authoring it would be a latent trap.
#
# The liquidation chain adds NO verb: its certifications are ``approve`` at gate
# states, exactly like the claim chain's approvals. That is what lets the
# un-gated ``api/actions.py`` drive both chains with no new route.
_AUTHORED_ACTIONS = frozenset({"submit", "approve", "return", "cancel", "resubmit"})


def _assert_graph_invariants(
    states: list[WorkflowState],
    transitions: list[WorkflowTransition],
    *,
    vocab: st.Vocabulary,
) -> None:
    """Seed-time self-checks beyond ``validate_graph`` (developer errors, so
    ``RuntimeError`` like ``apply_rbac_grants``): no open gates, no stray verbs,
    and THAT KIND's status vocabulary covers every authored state.

    The vocabulary is a parameter rather than a module global (R-6-liq-chain):
    with two chains, checking both against one merged set would accept a
    liquidation state authored into the claim graph — the exact drift this
    check exists to catch.
    """
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
    if authored_codes != set(vocab.all_states):
        raise RuntimeError(
            f"status vocabulary drift for kind '{vocab.kind}': authored states "
            f"{sorted(authored_codes)} != vocabulary.all_states "
            f"{sorted(vocab.all_states)}."
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

    labels = st.REIMBURSEMENT.labels
    s: dict[str, WorkflowState] = {}
    s[st.DRAFT] = await wf.add_state(
        session, version=version, code=st.DRAFT,
        name=labels[st.DRAFT], kind="initial", sort_order=0,
    )
    s[st.DIVISION_APPROVAL] = await wf.add_state(
        session, version=version, code=st.DIVISION_APPROVAL,
        name=labels[st.DIVISION_APPROVAL], kind="normal", sort_order=1,
        is_approval_gate=True, required_permission=APPROVE_PERM,
        enforce_segregation=True,
    )
    s[st.ADMIN_REVIEW] = await wf.add_state(
        session, version=version, code=st.ADMIN_REVIEW,
        name=labels[st.ADMIN_REVIEW], kind="normal", sort_order=2,
        is_approval_gate=True, required_permission=REVIEW_PERM,
        enforce_segregation=True,
    )
    s[st.HANDED_TO_FMS] = await wf.add_state(
        session, version=version, code=st.HANDED_TO_FMS,
        name=labels[st.HANDED_TO_FMS], kind="normal", sort_order=3,
        is_approval_gate=True, required_permission=FMS_PERM,
    )
    s[st.FMS_RETURNED] = await wf.add_state(
        session, version=version, code=st.FMS_RETURNED,
        name=labels[st.FMS_RETURNED], kind="normal", sort_order=4,
        is_approval_gate=True, required_permission=REVIEW_PERM,
    )
    s[st.RETURNED] = await wf.add_state(
        session, version=version, code=st.RETURNED,
        name=labels[st.RETURNED], kind="normal", sort_order=5,
    )
    s[st.PAID_CLOSED] = await wf.add_state(
        session, version=version, code=st.PAID_CLOSED,
        name=labels[st.PAID_CLOSED], kind="terminal", sort_order=6,
    )
    s[st.CANCELLED] = await wf.add_state(
        session, version=version, code=st.CANCELLED,
        name=labels[st.CANCELLED], kind="terminal", sort_order=7,
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

    _assert_graph_invariants(
        list(s.values()), transitions, vocab=st.REIMBURSEMENT
    )
    await wf.publish_version(session, version=version)
    await session.flush()
    return version


async def ensure_liquidation_definition(
    session: AsyncSession,
) -> WorkflowDefinitionVersion:
    """Idempotently author + publish v1 of ``reimbursement.liquidation``.

    Spec §6.2 reads ``CA Open → Liquidation Draft → Submitted → Certifications
    (A→B→C in order) → Handed to FMS → … → Settled``. Three authoring decisions
    turn that sentence into a graph:

    **Certification A is folded into submit** (user-confirmed at the R-6-liq
    kickoff; the R-4-app maker/checker decision applied verbatim). A certifies
    that the claimant incurred the expenses — the claimant IS the maker, and the
    engine's ``enforce_segregation`` guards ``instance.originator_user_id``, so
    authoring A as a gate would ask the maker to check themselves. Submitting a
    liquidation IS certification A; the event log records who and when.

    **No ``fms_returned``.** The claim chain has one so the Admin Officer can
    relay FMS's comments (spec §6.1 row 7); §6.2 names no such state, R-7 owns
    external tracking, and authoring it now would author a state with no screen.
    If FMS turns out to bounce liquidations with comments, that is definition
    **v2** — the same versioned-definition answer that defers the DO 2019-0225
    amount tiers. A liquidation FMS returns goes straight to ``returned``.

    **No new verb.** Certifications B and C are ``approve`` transitions at gate
    states, exactly like the claim chain's approvals, so the un-gated
    ``api/actions.py`` drives this chain with no new route and no new schema.
    """
    existing = await wf.get_published_version(session, LIQUIDATION_DEFINITION_CODE)
    if existing is not None:
        return existing

    definition = (
        (
            await session.execute(
                select(WorkflowDefinition).where(
                    WorkflowDefinition.code == LIQUIDATION_DEFINITION_CODE
                )
            )
        )
        .scalars()
        .first()
    )
    if definition is None:
        definition = await wf.create_definition(
            session,
            code=LIQUIDATION_DEFINITION_CODE,
            name="Local Travel Reimbursement — liquidation",
            module=FEATURE_FLAG_KEY,
            description=(
                "Spec §6.2 certification chain: submit (certification A, the "
                "claimant as maker) → certification B (Director IV) → "
                "certification C (Head, Accounting Unit — external wet sign "
                "recorded by the Admin Officer) → FMS → settled."
            ),
        )
    version = await wf.create_version(
        session, definition=definition, resubmit_policy="restart"
    )

    labels = st.LIQUIDATION.labels
    s: dict[str, WorkflowState] = {}
    s[st.DRAFT] = await wf.add_state(
        session, version=version, code=st.DRAFT,
        name=labels[st.DRAFT], kind="initial", sort_order=0,
    )
    s[st.CERTIFY_B] = await wf.add_state(
        session, version=version, code=st.CERTIFY_B,
        name=labels[st.CERTIFY_B], kind="normal", sort_order=1,
        is_approval_gate=True, required_permission=CERTIFY_PERM,
        enforce_segregation=True,
    )
    # Certification C is cleared by the Admin Officer RECORDING the Accounting
    # head's wet signature — they are FMS, outside the platform, so the act
    # inside Office-Connect is an administrative one under the existing review
    # permission. Segregation still holds: the claimant can never clear it.
    s[st.CERTIFY_C] = await wf.add_state(
        session, version=version, code=st.CERTIFY_C,
        name=labels[st.CERTIFY_C], kind="normal", sort_order=2,
        is_approval_gate=True, required_permission=REVIEW_PERM,
        enforce_segregation=True,
    )
    s[st.HANDED_TO_FMS] = await wf.add_state(
        session, version=version, code=st.HANDED_TO_FMS,
        name=labels[st.HANDED_TO_FMS], kind="normal", sort_order=3,
        is_approval_gate=True, required_permission=FMS_PERM,
    )
    s[st.RETURNED] = await wf.add_state(
        session, version=version, code=st.RETURNED,
        name=labels[st.RETURNED], kind="normal", sort_order=4,
    )
    s[st.SETTLED] = await wf.add_state(
        session, version=version, code=st.SETTLED,
        name=labels[st.SETTLED], kind="terminal", sort_order=5,
    )
    s[st.CANCELLED] = await wf.add_state(
        session, version=version, code=st.CANCELLED,
        name=labels[st.CANCELLED], kind="terminal", sort_order=6,
    )

    transitions = [
        # Submitting IS certification A — see the docstring.
        await wf.add_transition(
            session, version=version, from_state=s[st.DRAFT],
            to_state=s[st.CERTIFY_B], action="submit",
            required_permission=REVIEW_PERM,
        ),
        # Unreachable at runtime (instances are created AT submit); kept for
        # graph fidelity with the claim chain.
        await wf.add_transition(
            session, version=version, from_state=s[st.DRAFT],
            to_state=s[st.CANCELLED], action="cancel",
            requires_comment=True, required_permission=REVIEW_PERM,
        ),
        await wf.add_transition(
            session, version=version, from_state=s[st.CERTIFY_B],
            to_state=s[st.CERTIFY_C], action="approve",
        ),
        await wf.add_transition(
            session, version=version, from_state=s[st.CERTIFY_B],
            to_state=s[st.RETURNED], action="return", requires_comment=True,
        ),
        # A comment is MANDATORY on this approve, unlike every other rung: the
        # Admin Officer is attesting to a signature made on paper by someone
        # outside the platform, so the note naming whose signature and when is
        # the only record of certification C that Office-Connect will ever hold.
        # Binding a frozen snapshot to the step is core-service #3's signature
        # half — still unbuilt, deferred with a written reason.
        await wf.add_transition(
            session, version=version, from_state=s[st.CERTIFY_C],
            to_state=s[st.HANDED_TO_FMS], action="approve", requires_comment=True,
        ),
        await wf.add_transition(
            session, version=version, from_state=s[st.CERTIFY_C],
            to_state=s[st.RETURNED], action="return", requires_comment=True,
        ),
        await wf.add_transition(
            session, version=version, from_state=s[st.HANDED_TO_FMS],
            to_state=s[st.SETTLED], action="approve",
        ),
        await wf.add_transition(
            session, version=version, from_state=s[st.HANDED_TO_FMS],
            to_state=s[st.RETURNED], action="return", requires_comment=True,
        ),
        await wf.add_transition(
            session, version=version, from_state=s[st.RETURNED],
            to_state=s[st.CERTIFY_B], action="resubmit",
            required_permission=REVIEW_PERM,
        ),
        await wf.add_transition(
            session, version=version, from_state=s[st.RETURNED],
            to_state=s[st.CANCELLED], action="cancel",
            requires_comment=True, required_permission=REVIEW_PERM,
        ),
    ]

    _assert_graph_invariants(list(s.values()), transitions, vocab=st.LIQUIDATION)
    await wf.publish_version(session, version=version)
    await session.flush()
    return version


async def ensure_definitions(session: AsyncSession) -> dict[str, int]:
    """Author + publish every module definition. ``{code: version_id}``.

    One entry point so a new kind cannot ship with a vocabulary, a catalog and a
    lifecycle path but no chain — ``ops.bootstrap seed-workflows`` calls this,
    not the individual authors.
    """
    claim = await ensure_claim_definition(session)
    liquidation = await ensure_liquidation_definition(session)
    return {
        DEFINITION_CODE: claim.id,
        LIQUIDATION_DEFINITION_CODE: liquidation.id,
    }
