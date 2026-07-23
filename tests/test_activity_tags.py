"""Increment 4 Group A — configurable activity taxonomies (GAD/CCET/DRR/UHC).

Tags are rows, never boolean columns; assignments give an activity multi-tag.
Natural keys are tokenized per run — the dev DB keeps benign rows between runs.
"""

import uuid
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from office_connect.core.models import (
    Activity,
    ActivityTag,
    ActivityTagAssignment,
    AuditLog,
)
from office_connect.core.soft_delete import soft_delete


def _tok() -> str:
    return uuid.uuid4().hex[:10]


async def _make_tag(session, taxonomy="gad", code=None, label="tag"):
    tag = ActivityTag(taxonomy=taxonomy, code=code or _tok(), label=label)
    session.add(tag)
    await session.commit()
    return tag


async def test_tag_assignment_round_trip(app_session):
    activity = Activity(title="Tagged activity", date_start=date(2026, 7, 23))
    app_session.add(activity)
    tag = await _make_tag(app_session)
    app_session.add(
        ActivityTagAssignment(activity_id=activity.id, activity_tag_id=tag.id)
    )
    await app_session.commit()

    rows = list(
        (
            await app_session.execute(
                select(ActivityTagAssignment).where(
                    ActivityTagAssignment.activity_id == activity.id
                )
            )
        ).scalars()
    )
    assert len(rows) == 1
    assert rows[0].activity_tag_id == tag.id


async def test_taxonomy_code_unique_among_live(app_session):
    code = _tok()
    await _make_tag(app_session, taxonomy="ccet", code=code, label="CCET-A")
    dup = ActivityTag(taxonomy="ccet", code=code, label="dup")
    app_session.add(dup)
    with pytest.raises(IntegrityError):
        await app_session.commit()
    await app_session.rollback()


async def test_soft_deleted_tag_frees_the_code(app_session):
    code = _tok()
    tag = await _make_tag(app_session, taxonomy="drr", code=code, label="DRR-P")
    soft_delete(tag)
    await app_session.commit()

    # The partial-unique index ignores the soft-deleted row → the code can return.
    revived = ActivityTag(taxonomy="drr", code=code, label="DRR-P v2")
    app_session.add(revived)
    await app_session.commit()
    assert revived.id != tag.id


async def test_assignment_soft_delete_is_audited(app_session, owner_session):
    activity = Activity(title="Re-tag me", date_start=date(2026, 7, 23))
    app_session.add(activity)
    tag = await _make_tag(app_session, taxonomy="uhc", label="UHC-SD")
    assignment = ActivityTagAssignment(
        activity_id=activity.id, activity_tag_id=tag.id
    )
    app_session.add(assignment)
    await app_session.commit()

    soft_delete(assignment)
    await app_session.commit()

    actions = list(
        (
            await owner_session.execute(
                select(AuditLog.action)
                .where(
                    AuditLog.table_name == "core_activity_tag_assignments",
                    AuditLog.row_pk == assignment.id,
                )
                .order_by(AuditLog.id)
            )
        ).scalars()
    )
    assert actions == ["insert", "soft_delete"]
