"""The transition executor — one atomic, idempotent, concurrency-safe action.

``execute_action`` is the single mutating entry point. In ONE transaction it:

1. ``SELECT ... FOR UPDATE`` the instance (serializes concurrent actors).
2. Idempotency replay: an existing event for ``(instance, idempotency_key)`` is
   returned verbatim — a retry/double-click never acts twice.
3. Compare-and-swap: an ``expected_version`` mismatch → 409; acting on a terminal
   state → 409 (someone finished it first).
4. Route: pick the first transition ``(from_state, action)`` whose typed amount guard
   passes; none → 422.
5. Authorize server-side (the SAME check ``available_actions`` uses): gate actions via
   the active step's permission + org scope + delegation; originator actions via
   ownership or the transition's permission. Segregation-of-duties on approval gates.
6. Advance: mark the step(s), fan-in per join type, move ``current_state`` + bump
   ``row_version``, activate the next gate's steps, and append the append-only event.

Because ``core/audit.py::_block_unaudited_bulk_dml`` forbids ORM bulk UPDATE and every
change must ride the hash chain, the CAS is a row lock + in-Python check + an audited
ORM mutate — not a raw conditional UPDATE. Correctness is identical; auditability is
preserved.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.maker_checker import assert_segregation
from office_connect.core.models import (
    WorkflowDefinitionVersion,
    WorkflowEvent,
    WorkflowInstance,
    WorkflowState,
    WorkflowStep,
    WorkflowTransition,
)
from office_connect.core.org_units import authorize_scoped
from office_connect.core.session import set_audit_context
from office_connect.core.time import utc_now
from office_connect.core.workflow import errors, steps as steps_mod
from office_connect.core.workflow.delegation import Authority, resolve_authority
from office_connect.core.workflow.guards import amount_guard_passes

GATE_ACTIONS = frozenset({"approve", "return", "reject"})
ORIGINATOR_ACTIONS = frozenset({"submit", "resubmit", "cancel"})


async def _select_transition(
    session: AsyncSession,
    instance: WorkflowInstance,
    current: WorkflowState,
    action: str,
) -> WorkflowTransition | None:
    stmt = (
        select(WorkflowTransition)
        .where(
            WorkflowTransition.from_state_id == current.id,
            WorkflowTransition.action == action,
        )
        .order_by(WorkflowTransition.sort_order, WorkflowTransition.id)
    )
    for transition in (await session.execute(stmt)).scalars():
        if amount_guard_passes(transition, instance):
            return transition
    return None


async def _definition_id(session: AsyncSession, instance: WorkflowInstance) -> int:
    version = await session.get(
        WorkflowDefinitionVersion, instance.definition_version_id
    )
    return version.definition_id if version else None


async def _authorize_originator(
    session: AsyncSession,
    *,
    instance: WorkflowInstance,
    transition: WorkflowTransition,
    actor_user_id: int,
    definition_id: int,
    now: datetime,
) -> Authority:
    if instance.originator_user_id is not None and actor_user_id == instance.originator_user_id:
        return Authority(True, None)
    # An admin/delegate may act if they hold the transition's permission at the unit.
    return await resolve_authority(
        session,
        actor_user_id=actor_user_id,
        required_permission=transition.required_permission,
        org_unit_id=instance.org_unit_id,
        definition_id=definition_id,
        now=now,
    )


def _emit(
    *,
    instance: WorkflowInstance,
    action: str,
    from_state_id: int,
    to_state_id: int,
    actor_user_id: int | None,
    on_behalf_of: int | None,
    comment: str | None,
    idempotency_key: str | None,
    step_id: int | None,
) -> WorkflowEvent:
    return WorkflowEvent(
        instance_id=instance.id,
        step_id=step_id,
        event_type="transition",
        action=action,
        from_state_id=from_state_id,
        to_state_id=to_state_id,
        actor_user_id=actor_user_id,
        on_behalf_of_user_id=on_behalf_of,
        comment=comment,
        idempotency_key=idempotency_key,
        revision_no=instance.revision_no,
    )


async def execute_action(
    session: AsyncSession,
    *,
    instance_id: int,
    action: str,
    actor_user_id: int,
    comment: str | None = None,
    idempotency_key: str | None = None,
    expected_version: int | None = None,
    now: datetime | None = None,
) -> WorkflowEvent:
    """Perform ``action`` on an instance, returning the recorded event. Raises a
    structured ``APIError`` (see ``errors``) on any guard/authz/concurrency failure."""
    now = now or utc_now()
    set_audit_context(session, actor_id=actor_user_id)

    # 1. Lock the instance for the duration of the transaction.
    instance = (
        await session.execute(
            select(WorkflowInstance)
            .where(WorkflowInstance.id == instance_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if instance is None:
        raise errors.instance_not_found()

    # 2. Idempotency replay.
    if idempotency_key:
        existing = (
            await session.execute(
                select(WorkflowEvent).where(
                    WorkflowEvent.instance_id == instance_id,
                    WorkflowEvent.idempotency_key == idempotency_key,
                )
            )
        ).scalars().first()
        if existing is not None:
            return existing

    # 3. Compare-and-swap preconditions.
    if expected_version is not None and instance.row_version != expected_version:
        raise errors.stale_version()

    current = await session.get(WorkflowState, instance.current_state_id)
    if current.kind == "terminal":
        raise errors.state_conflict()

    # 4. Route.
    transition = await _select_transition(session, instance, current, action)
    if transition is None:
        raise errors.transition_not_allowed(action)

    # Comment requirement (state- or transition-level).
    if (transition.requires_comment or current.requires_comment) and not comment:
        raise errors.comment_required()

    definition_id = await _definition_id(session, instance)
    on_behalf_of: int | None = None
    acted_step_id: int | None = None
    new_state_id = current.id  # default: no move (partial approval)

    if action in GATE_ACTIONS:
        gate = await steps_mod.gate_steps(
            session,
            instance_id=instance.id,
            state_id=current.id,
            revision_no=instance.revision_no,
            lock=True,
        )
        if action == "approve":
            # Distinct-approver: this actor may not fill two slots of one gate.
            if any(s.acted_by_user_id == actor_user_id and s.status == "done" for s in gate):
                raise errors.already_acted()
            step = next((s for s in gate if s.status == "active"), None)
            if step is None:
                raise errors.already_acted()
            auth = await resolve_authority(
                session,
                actor_user_id=actor_user_id,
                required_permission=step.required_permission,
                org_unit_id=step.org_unit_id,
                definition_id=definition_id,
                now=now,
            )
            if not auth.authorized:
                raise errors.not_authorized()
            if current.enforce_segregation and instance.originator_user_id is not None:
                prior = [
                    s.acted_by_user_id
                    for s in gate
                    if s.status == "done" and s.acted_by_user_id is not None
                ]
                assert_segregation(
                    maker_id=instance.originator_user_id,
                    checker_ids=[*prior, actor_user_id],
                )
            on_behalf_of = auth.on_behalf_of
            step.status = "done"
            step.acted_by_user_id = actor_user_id
            step.on_behalf_of_user_id = on_behalf_of
            step.acted_at = now
            step.comment = comment
            acted_step_id = step.id
            await session.flush()
            if steps_mod.join_satisfied(gate):
                new_state_id = transition.to_state_id
                for other in gate:
                    if other.status == "active":
                        other.status = "skipped"
        else:  # return / reject
            auth = await resolve_authority(
                session,
                actor_user_id=actor_user_id,
                required_permission=current.required_permission
                or transition.required_permission,
                org_unit_id=instance.org_unit_id,
                definition_id=definition_id,
                now=now,
            )
            if not auth.authorized:
                raise errors.not_authorized()
            on_behalf_of = auth.on_behalf_of
            resolved = "returned" if action == "return" else "skipped"
            for s in gate:
                if s.status in ("active", "pending"):
                    s.status = resolved
                    s.acted_by_user_id = actor_user_id
                    s.on_behalf_of_user_id = on_behalf_of
                    s.acted_at = now
            new_state_id = transition.to_state_id
    else:  # originator actions: submit / resubmit / cancel
        auth = await _authorize_originator(
            session,
            instance=instance,
            transition=transition,
            actor_user_id=actor_user_id,
            definition_id=definition_id,
            now=now,
        )
        if not auth.authorized:
            raise errors.not_authorized()
        on_behalf_of = auth.on_behalf_of
        if action == "resubmit":
            instance.revision_no += 1
        new_state_id = transition.to_state_id

    # Advance state + bump the CAS version (every successful action bumps it).
    moved = new_state_id != current.id
    instance.current_state_id = new_state_id
    instance.row_version += 1
    await session.flush()

    if moved:
        new_state = await session.get(WorkflowState, new_state_id)
        if new_state.is_approval_gate:
            await steps_mod.activate_state_steps(
                session, instance=instance, state=new_state, now=now
            )

    event = _emit(
        instance=instance,
        action=action,
        from_state_id=current.id,
        to_state_id=new_state_id,
        actor_user_id=actor_user_id,
        on_behalf_of=on_behalf_of,
        comment=comment,
        idempotency_key=idempotency_key,
        step_id=acted_step_id,
    )
    session.add(event)
    await session.flush()
    return event


async def available_actions(
    session: AsyncSession,
    *,
    instance_id: int,
    actor_user_id: int,
    now: datetime | None = None,
) -> list[str]:
    """The actions ``actor_user_id`` may take on the instance right now — the single
    (state × actor × guards × delegation) computation a GET renders and a POST
    re-validates through ``execute_action`` (the UI never computes permissions).

    Contract: an action listed here is one ``execute_action`` would accept for
    this actor *now* — including the actor-dependent gate guards
    (distinct-approver, segregation). Offering an action that is certain to 409
    is a bug, not a race (workflow-standards §3)."""
    now = now or utc_now()
    instance = await session.get(WorkflowInstance, instance_id)
    if instance is None:
        raise errors.instance_not_found()
    current = await session.get(WorkflowState, instance.current_state_id)
    if current is None or current.kind == "terminal":
        return []
    definition_id = await _definition_id(session, instance)

    stmt = (
        select(WorkflowTransition)
        .where(WorkflowTransition.from_state_id == current.id)
        .order_by(WorkflowTransition.sort_order, WorkflowTransition.id)
    )
    allowed: list[str] = []
    for transition in (await session.execute(stmt)).scalars():
        if transition.action in allowed:
            continue
        if not amount_guard_passes(transition, instance):
            continue
        if transition.action in GATE_ACTIONS:
            if transition.action == "approve":
                gate = await steps_mod.gate_steps(
                    session,
                    instance_id=instance.id,
                    state_id=current.id,
                    revision_no=instance.revision_no,
                )
                if not any(s.status == "active" for s in gate):
                    continue
                # Mirror execute_action's two ACTOR-dependent guards, or the UI
                # would render a button that always 409s. Distinct-approver:
                # this actor already filled a slot of this gate.
                if any(
                    s.acted_by_user_id == actor_user_id and s.status == "done"
                    for s in gate
                ):
                    continue
                # Segregation: the maker can never be a checker (COA 92-389).
                # Prior checkers can't be the maker (they'd have been blocked),
                # so the actor-as-originator case is the only one to filter.
                if (
                    current.enforce_segregation
                    and instance.originator_user_id is not None
                    and instance.originator_user_id == actor_user_id
                ):
                    continue
            auth = await resolve_authority(
                session,
                actor_user_id=actor_user_id,
                required_permission=current.required_permission
                or transition.required_permission,
                org_unit_id=instance.org_unit_id,
                definition_id=definition_id,
                now=now,
            )
            if auth.authorized:
                allowed.append(transition.action)
        else:
            auth = await _authorize_originator(
                session,
                instance=instance,
                transition=transition,
                actor_user_id=actor_user_id,
                definition_id=definition_id,
                now=now,
            )
            if auth.authorized:
                allowed.append(transition.action)
    return allowed
