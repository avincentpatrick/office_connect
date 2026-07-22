"""QA gate (rule 5): the hash chain records every change and detects tampering.

The tamper test mutates a row INSIDE an uncommitted transaction and rolls it
back — the dev database's chain is never left corrupted.
"""

import json
from datetime import date

from sqlalchemy import select, text

from office_connect.core.audit import verify_chain
from office_connect.core.models import Activity, AuditLog
from office_connect.core.soft_delete import soft_delete


async def _all_audit_rows(session) -> list[AuditLog]:
    result = await session.execute(select(AuditLog).order_by(AuditLog.id))
    return list(result.scalars())


async def test_lifecycle_produces_chained_rows(app_session, owner_session):
    activity = Activity(title="Chain test", date_start=date(2026, 7, 22))
    app_session.add(activity)
    await app_session.commit()

    activity.venue = "Training Hall"
    await app_session.commit()

    soft_delete(activity)
    await app_session.commit()

    rows = list(
        (
            await owner_session.execute(
                select(AuditLog)
                .where(
                    AuditLog.table_name == "core_activities",
                    AuditLog.row_pk == activity.id,
                )
                .order_by(AuditLog.id)
            )
        ).scalars()
    )
    assert [r.action for r in rows] == ["insert", "update", "soft_delete"]
    assert rows[0].new_data["title"] == "Chain test"
    assert rows[1].old_data == {"venue": None}
    assert rows[1].new_data == {"venue": "Training Hall"}
    assert rows[2].new_data["deleted_at"] is not None
    # Chain continuity across the three rows (may interleave with other tests'
    # rows — prev_hash linkage is asserted by the full verify below).
    whole_chain = await _all_audit_rows(owner_session)
    assert verify_chain(whole_chain) is None


async def test_tamper_is_detected_then_rolled_back(app_session, owner_session):
    activity = Activity(title="Tamper target", date_start=date(2026, 7, 22))
    app_session.add(activity)
    await app_session.commit()

    target_id = (
        await owner_session.execute(
            select(AuditLog.id)
            .where(
                AuditLog.table_name == "core_activities",
                AuditLog.row_pk == activity.id,
            )
            .order_by(AuditLog.id)
        )
    ).scalars().first()
    assert target_id is not None

    # Forge inside an uncommitted transaction (owner role bypasses grants —
    # exactly the threat the chain exists to expose).
    await owner_session.execute(
        text(
            "UPDATE core_audit_logs "
            "SET new_data = jsonb_set(coalesce(new_data, '{}'::jsonb), "
            "'{title}', CAST(:forged AS jsonb)) WHERE id = :id"
        ),
        {"forged": json.dumps("FORGED"), "id": target_id},
    )
    tampered = await _all_audit_rows(owner_session)  # same tx sees the forgery
    assert verify_chain(tampered) == target_id  # QA gate: tamper detected

    await owner_session.rollback()  # never persist the forgery
    clean = await _all_audit_rows(owner_session)
    assert verify_chain(clean) is None
