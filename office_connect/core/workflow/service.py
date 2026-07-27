"""Consumer-facing facade: start an instance; act on it; read allowed actions.

A module (reimbursement first) consumes the engine through this surface plus the
authoring helpers in ``definitions``. ``start_instance`` is the ONLY place the feature
flag is checked — a flag OFF blocks NEW instances but ``execute_action`` never reads it,
so in-flight items always finish (design doc + master-plan §1.1 flag semantics).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.models import FeatureFlag, WorkflowEvent, WorkflowInstance
from office_connect.core.session import set_audit_context
from office_connect.core.time import utc_now
from office_connect.core.workflow import errors
from office_connect.core.workflow.definitions import (
    get_published_version,
    initial_state,
)
from office_connect.core.workflow.steps import activate_state_steps
from office_connect.core.workflow.transitions import available_actions, execute_action

__all__ = ["start_instance", "execute_action", "available_actions"]


async def _flag_enabled(session: AsyncSession, key: str) -> bool:
    row = (
        await session.execute(select(FeatureFlag).where(FeatureFlag.key == key))
    ).scalar_one_or_none()
    return bool(row and row.enabled and row.is_active)


async def start_instance(
    session: AsyncSession,
    *,
    definition_code: str,
    actor_user_id: int | None = None,
    org_unit_id: int | None = None,
    subject_kind: str | None = None,
    subject_id: int | None = None,
    amount: Decimal | None = None,
    context: dict[str, Any] | None = None,
    feature_flag_key: str | None = None,
    now: datetime | None = None,
) -> WorkflowInstance:
    """Create a new instance on the latest published version of ``definition_code``.

    If ``feature_flag_key`` is given, creation is blocked unless the flag is ON
    (``enabled AND is_active``); pass ``None`` to skip the gate (engine-internal /
    always-on definitions)."""
    now = now or utc_now()
    set_audit_context(session, actor_id=actor_user_id)

    if feature_flag_key is not None and not await _flag_enabled(session, feature_flag_key):
        raise errors.module_disabled(feature_flag_key)

    version = await get_published_version(session, definition_code)
    if version is None:
        raise errors.definition_not_published(definition_code)
    initial = await initial_state(session, version.id)

    instance = WorkflowInstance(
        definition_version_id=version.id,
        current_state_id=initial.id,
        originator_user_id=actor_user_id,
        org_unit_id=org_unit_id,
        subject_kind=subject_kind,
        subject_id=subject_id,
        amount=amount,
        context=context or {},
    )
    session.add(instance)
    await session.flush()

    if initial.is_approval_gate:
        await activate_state_steps(session, instance=instance, state=initial, now=now)

    event = WorkflowEvent(
        instance_id=instance.id,
        event_type="started",
        to_state_id=initial.id,
        actor_user_id=actor_user_id,
        revision_no=instance.revision_no,
    )
    session.add(event)
    await session.flush()
    return instance
