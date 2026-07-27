"""Design-time authoring: definitions, versions, states, transitions + publish.

A definition is authored as a DRAFT version (states + transitions added freely), then
``publish_version`` validates the graph and freezes it. Published versions are
immutable (editing raises); a new revision is a NEW version. New instances start on the
LATEST published version; in-flight instances stay pinned to theirs.

Reimbursement (R-4-app) will build its chain through exactly these helpers; the engine
ships them so the chain is data, not code.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.models import (
    WorkflowDefinition,
    WorkflowDefinitionVersion,
    WorkflowState,
    WorkflowTransition,
)
from office_connect.core.time import utc_now
from office_connect.core.workflow import errors


async def create_definition(
    session: AsyncSession,
    *,
    code: str,
    name: str,
    module: str | None = None,
    description: str | None = None,
) -> WorkflowDefinition:
    definition = WorkflowDefinition(
        code=code, name=name, module=module, description=description
    )
    session.add(definition)
    await session.flush()
    return definition


async def create_version(
    session: AsyncSession,
    *,
    definition: WorkflowDefinition,
    resubmit_policy: str = "restart",
) -> WorkflowDefinitionVersion:
    """Open a new DRAFT version (next ``version_no``) of ``definition``."""
    max_no = (
        await session.execute(
            select(func.max(WorkflowDefinitionVersion.version_no)).where(
                WorkflowDefinitionVersion.definition_id == definition.id
            )
        )
    ).scalar_one_or_none()
    version = WorkflowDefinitionVersion(
        definition_id=definition.id,
        version_no=(max_no or 0) + 1,
        resubmit_policy=resubmit_policy,
    )
    session.add(version)
    await session.flush()
    return version


async def add_state(
    session: AsyncSession,
    *,
    version: WorkflowDefinitionVersion,
    code: str,
    name: str,
    kind: str = "normal",
    sort_order: int = 0,
    is_approval_gate: bool = False,
    required_permission: str | None = None,
    join_type: str = "all",
    step_count: int = 1,
    quorum_count: int | None = None,
    sla_hours: int | None = None,
    enforce_segregation: bool = False,
    requires_comment: bool = False,
) -> WorkflowState:
    if version.is_published:
        raise errors.already_published()
    state = WorkflowState(
        definition_version_id=version.id,
        code=code,
        name=name,
        kind=kind,
        sort_order=sort_order,
        is_approval_gate=is_approval_gate,
        required_permission=required_permission,
        join_type=join_type,
        step_count=step_count,
        quorum_count=quorum_count,
        sla_hours=sla_hours,
        enforce_segregation=enforce_segregation,
        requires_comment=requires_comment,
    )
    session.add(state)
    await session.flush()
    return state


async def add_transition(
    session: AsyncSession,
    *,
    version: WorkflowDefinitionVersion,
    from_state: WorkflowState,
    to_state: WorkflowState,
    action: str,
    sort_order: int = 0,
    required_permission: str | None = None,
    min_amount: Decimal | None = None,
    max_amount: Decimal | None = None,
    requires_comment: bool = False,
) -> WorkflowTransition:
    if version.is_published:
        raise errors.already_published()
    transition = WorkflowTransition(
        definition_version_id=version.id,
        from_state_id=from_state.id,
        to_state_id=to_state.id,
        action=action,
        sort_order=sort_order,
        required_permission=required_permission,
        min_amount=min_amount,
        max_amount=max_amount,
        requires_comment=requires_comment,
    )
    session.add(transition)
    await session.flush()
    return transition


async def _states_and_transitions(
    session: AsyncSession, version_id: int
) -> tuple[list[WorkflowState], list[WorkflowTransition]]:
    states = list(
        (
            await session.execute(
                select(WorkflowState).where(
                    WorkflowState.definition_version_id == version_id
                )
            )
        ).scalars()
    )
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


def validate_graph(
    states: list[WorkflowState], transitions: list[WorkflowTransition]
) -> None:
    """Raise ``workflow_invalid_definition`` unless the graph is well-formed:
    exactly one initial state, ≥1 terminal, every non-terminal has an exit, every
    transition endpoint is a known state, and every state is reachable from initial."""
    if not states:
        raise errors.invalid_definition("A version needs at least one state.")
    ids = {s.id for s in states}
    initials = [s for s in states if s.kind == "initial"]
    if len(initials) != 1:
        raise errors.invalid_definition(
            f"Exactly one initial state required (found {len(initials)})."
        )
    if not any(s.kind == "terminal" for s in states):
        raise errors.invalid_definition("At least one terminal state required.")

    out: dict[int, list[int]] = {s.id: [] for s in states}
    for t in transitions:
        if t.from_state_id not in ids or t.to_state_id not in ids:
            raise errors.invalid_definition(
                "A transition references a state outside this version."
            )
        out[t.from_state_id].append(t.to_state_id)

    for s in states:
        if s.kind != "terminal" and not out[s.id]:
            raise errors.invalid_definition(
                f"Non-terminal state '{s.code}' has no outgoing transition."
            )

    # Reachability from the initial state.
    seen: set[int] = set()
    frontier = [initials[0].id]
    while frontier:
        node = frontier.pop()
        if node in seen:
            continue
        seen.add(node)
        frontier.extend(out[node])
    unreachable = ids - seen
    if unreachable:
        codes = sorted(s.code for s in states if s.id in unreachable)
        raise errors.invalid_definition(f"Unreachable states: {', '.join(codes)}.")


async def publish_version(
    session: AsyncSession, *, version: WorkflowDefinitionVersion
) -> WorkflowDefinitionVersion:
    """Validate + freeze a draft version. Idempotent for an already-published one."""
    if version.is_published:
        return version
    states, transitions = await _states_and_transitions(session, version.id)
    validate_graph(states, transitions)
    version.is_published = True
    version.published_at = utc_now()
    await session.flush()
    return version


async def get_published_version(
    session: AsyncSession, definition_code: str
) -> WorkflowDefinitionVersion | None:
    """The latest published version of a definition (current for new instances)."""
    stmt = (
        select(WorkflowDefinitionVersion)
        .join(
            WorkflowDefinition,
            WorkflowDefinition.id == WorkflowDefinitionVersion.definition_id,
        )
        .where(
            WorkflowDefinition.code == definition_code,
            WorkflowDefinitionVersion.is_published.is_(True),
        )
        .order_by(WorkflowDefinitionVersion.version_no.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalars().first()


async def initial_state(session: AsyncSession, version_id: int) -> WorkflowState:
    stmt = select(WorkflowState).where(
        WorkflowState.definition_version_id == version_id,
        WorkflowState.kind == "initial",
    )
    return (await session.execute(stmt)).scalars().one()
