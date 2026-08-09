"""Increment 4 Group A — configurable activity taxonomies (GAD/CCET/DRR/UHC).

Tags are rows, never boolean columns; assignments give an activity multi-tag.

⚠ ``core_activity_tags`` is a SEEDED reference table, so every tag here goes in
through ``owned_row`` and comes back out (``seed_addition_guard``, conftest).
Assignments and activities are ordinary test data and stay as they are.
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

from tests.conftest import owned_row


def _tok() -> str:
    return uuid.uuid4().hex[:10]


def _tag(taxonomy="gad", code=None, label="tag") -> ActivityTag:
    """Build (never commit) a tag — persisting is ``owned_row``'s job, so no
    caller can acquire one without also acquiring its undo."""
    return ActivityTag(taxonomy=taxonomy, code=code or _tok(), label=label)


async def test_tag_assignment_round_trip(app_session):
    activity = Activity(title="Tagged activity", date_start=date(2026, 7, 23))
    app_session.add(activity)
    async with owned_row(app_session, _tag()) as tag:
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
    async with owned_row(
        app_session, _tag(taxonomy="ccet", code=code, label="CCET-A")
    ):
        dup = ActivityTag(taxonomy="ccet", code=code, label="dup")
        app_session.add(dup)
        with pytest.raises(IntegrityError):
            await app_session.commit()
        await app_session.rollback()


async def test_soft_deleted_tag_frees_the_code(app_session):
    code = _tok()
    # This one needs no `owned_row` — soft-deleting it IS the test.
    tag = _tag(taxonomy="drr", code=code, label="DRR-P")
    app_session.add(tag)
    await app_session.commit()
    soft_delete(tag)
    await app_session.commit()

    # The partial-unique index ignores the soft-deleted row → the code can return.
    async with owned_row(
        app_session, _tag(taxonomy="drr", code=code, label="DRR-P v2")
    ) as revived:
        assert revived.id != tag.id


async def test_assignment_soft_delete_is_audited(app_session, owner_session):
    activity = Activity(title="Re-tag me", date_start=date(2026, 7, 23))
    app_session.add(activity)
    async with owned_row(app_session, _tag(taxonomy="uhc", label="UHC-SD")) as tag:
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
