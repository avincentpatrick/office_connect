"""Stage B (Phase 2) QA gate: break-glass admin promotion + credential redaction.

Proves ``promote-admin`` mints exactly one break-glass login with a verifiable
temporary password and a global ``system_admin`` grant (idempotently), and that
the credential-secret columns (``password_hash``/``mfa_secret``) are redacted out
of the immutable audit chain on both INSERT and UPDATE (the Stage-B execution of
the audit-payload SPI policy for secrets).
"""

import secrets

from sqlalchemy import select

from office_connect.core.models import AuditLog, Role, User, UserRole
from office_connect.core.security import hash_password, verify_password
from office_connect.ops import bootstrap


async def test_promote_admin_creates_break_glass_login(app_session):
    await bootstrap._seed_rbac(app_session)
    email = f"bg-{secrets.token_hex(4)}@example.gov.ph"
    await bootstrap._record_admin(app_session, email, "Break-Glass Admin")

    result = await bootstrap._promote_admin(app_session)
    assert result["created"] is True

    user = (
        await app_session.execute(select(User).where(User.email == email))
    ).scalar_one()
    assert user.is_break_glass is True
    assert user.must_change_password is True
    assert user.is_active is True
    assert user.staff_id is None
    # The printed temp password verifies against the stored Argon2id hash.
    assert verify_password(result["temporary_password"], user.password_hash)

    role = (
        await app_session.execute(select(Role).where(Role.code == "system_admin"))
    ).scalar_one()
    grant = (
        await app_session.execute(
            select(UserRole).where(
                UserRole.user_id == user.id, UserRole.role_id == role.id
            )
        )
    ).scalar_one()
    assert grant.org_unit_id is None  # global grant

    # Idempotent: a second promotion finds the live account and no-ops.
    again = await bootstrap._promote_admin(app_session)
    assert again["created"] is False


async def test_user_secret_columns_redacted_on_insert(app_session, owner_session):
    email = f"redact-ins-{secrets.token_hex(4)}@example.gov.ph"
    user = User(
        email=email,
        password_hash=hash_password("super-secret-passphrase"),
        mfa_secret="JBSWY3DPEHPK3PXP",
    )
    app_session.add(user)
    await app_session.commit()

    row = (
        await owner_session.execute(
            select(AuditLog).where(
                AuditLog.table_name == "core_users",
                AuditLog.row_pk == user.id,
                AuditLog.action == "insert",
            )
        )
    ).scalar_one()
    assert row.new_data["password_hash"] == "[redacted]"
    assert row.new_data["mfa_secret"] == "[redacted]"
    # Non-SPI columns are recorded normally.
    assert row.new_data["email"] == email
    assert row.new_data["is_break_glass"] is False


async def test_user_password_hash_redacted_on_update(app_session, owner_session):
    email = f"redact-upd-{secrets.token_hex(4)}@example.gov.ph"
    user = User(email=email, password_hash=hash_password("first"))
    app_session.add(user)
    await app_session.commit()

    user.password_hash = hash_password("second")
    await app_session.commit()

    row = (
        await owner_session.execute(
            select(AuditLog)
            .where(
                AuditLog.table_name == "core_users",
                AuditLog.row_pk == user.id,
                AuditLog.action == "update",
            )
            .order_by(AuditLog.id.desc())
            .limit(1)
        )
    ).scalar_one()
    assert row.new_data["password_hash"] == "[redacted]"
    assert row.old_data["password_hash"] == "[redacted]"
