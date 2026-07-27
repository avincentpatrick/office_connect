"""Stage B (Phase 2) Increment 4 — full person-field SPI redaction.

Extends the B1 credential-redaction policy to the broader person-field set:
``core_staff`` direct identifiers and the notification recipient/body/payload
VALUES never enter the immutable hash chain (the field NAME is kept, so "the
field changed" stays auditable; the live row is the source of truth for the
current value). Structural / non-identifying fields stay recorded, and
``verify_chain`` still holds (redaction is deterministic at write time, so the
stored payload is exactly what the verifier rehashes). Policy: master-plan §4 #4,
database-standards §7.
"""

import secrets

from sqlalchemy import select

from office_connect.core.audit import verify_chain
from office_connect.core.models import AuditLog, NotificationOutbox, Staff


async def test_staff_person_fields_redacted_on_insert(app_session, owner_session):
    emp = f"E-{secrets.token_hex(4)}"
    staff = Staff(
        employee_no=emp,
        given_name="Juan",
        middle_name="Santos",
        surname="Dela Cruz",
        full_name="Juan Santos Dela Cruz",
        email=f"{emp}@doh.gov",
        position_title="Administrative Officer III",
        plantilla_item_no="OSEC-ADOF3-2020-1",
    )
    app_session.add(staff)
    await app_session.commit()

    row = (
        await owner_session.execute(
            select(AuditLog).where(
                AuditLog.table_name == "core_staff",
                AuditLog.row_pk == staff.id,
                AuditLog.action == "insert",
            )
        )
    ).scalar_one()
    # Direct identifiers: field name kept, value withheld.
    for field in ("given_name", "middle_name", "surname", "full_name", "email"):
        assert row.new_data[field] == "[redacted]", field
    # Structural / non-identifying fields recorded normally (not RA-10173 SPI).
    assert row.new_data["employee_no"] == emp
    assert row.new_data["position_title"] == "Administrative Officer III"
    assert row.new_data["plantilla_item_no"] == "OSEC-ADOF3-2020-1"


async def test_staff_surname_redacted_on_update(app_session, owner_session):
    emp = f"E-{secrets.token_hex(4)}"
    staff = Staff(
        employee_no=emp, given_name="Ana", surname="Before", full_name="Ana Before"
    )
    app_session.add(staff)
    await app_session.commit()

    staff.surname = "After"
    staff.full_name = "Ana After"
    await app_session.commit()

    row = (
        await owner_session.execute(
            select(AuditLog)
            .where(
                AuditLog.table_name == "core_staff",
                AuditLog.row_pk == staff.id,
                AuditLog.action == "update",
            )
            .order_by(AuditLog.id.desc())
            .limit(1)
        )
    ).scalar_one()
    # Neither the old nor the new value is sealed into the chain.
    assert row.new_data["surname"] == "[redacted]"
    assert row.old_data["surname"] == "[redacted]"


async def test_notification_recipient_and_body_redacted(app_session, owner_session):
    to = f"n-{secrets.token_hex(4)}@doh.gov"
    row = NotificationOutbox(
        channel="email",
        status="queued",
        recipient_email=to,
        subject="Your claim was approved",
        body_text="Dear Juan Dela Cruz, claim RB-2026-0001 is approved.",
        payload={"to": [to], "cc": []},
    )
    app_session.add(row)
    await app_session.commit()

    audit = (
        await owner_session.execute(
            select(AuditLog).where(
                AuditLog.table_name == "core_notifications",
                AuditLog.row_pk == row.id,
                AuditLog.action == "insert",
            )
        )
    ).scalar_one()
    assert audit.new_data["recipient_email"] == "[redacted]"
    assert audit.new_data["body_text"] == "[redacted]"
    assert audit.new_data["payload"] == "[redacted]"
    # Non-identifying fields recorded normally.
    assert audit.new_data["subject"] == "Your claim was approved"
    assert audit.new_data["channel"] == "email"


async def test_chain_still_verifies_after_person_field_writes(
    app_session, owner_session
):
    staff = Staff(
        employee_no=f"E-{secrets.token_hex(4)}",
        given_name="X",
        surname="Y",
        full_name="X Y",
    )
    app_session.add(staff)
    await app_session.commit()

    rows = (
        (await owner_session.execute(select(AuditLog).order_by(AuditLog.id)))
        .scalars()
        .all()
    )
    assert verify_chain(rows) is None
