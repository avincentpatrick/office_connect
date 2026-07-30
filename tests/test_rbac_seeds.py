"""Stage B (Phase 2) QA gate: RBAC seed catalogs + grant reconciliation.

Idempotent upsert of the permission/role catalogs and the bespoke role→permission
grant resolver (insert / restore-tombstoned / soft-delete-revoked), plus the
"every permission a role references exists in the DB" gate (auth-rbac-onprem.md).
"""

from sqlalchemy import select

from office_connect.core.models import Permission, Role, RolePermission
from office_connect.core.seeds import apply_dataset
from office_connect.core.seeds.rbac import (
    PERMISSIONS_DATASET,
    ROLES_DATASET,
    ROLE_GRANTS,
    apply_rbac_grants,
)
from office_connect.core.soft_delete import soft_delete


async def _seed(session):
    await apply_dataset(session, PERMISSIONS_DATASET)
    await apply_dataset(session, ROLES_DATASET)
    await apply_rbac_grants(session)
    await session.commit()


async def test_rbac_seed_idempotent(app_session):
    await _seed(app_session)
    # Second reconcile pass must change nothing.
    result = await apply_rbac_grants(app_session)
    await app_session.commit()
    assert result["grants_inserted"] == 0, result
    assert result["grants_restored"] == 0, result
    assert result["grants_revoked"] == 0, result


async def test_every_referenced_permission_is_seeded(app_session):
    await _seed(app_session)
    codes = set(
        (await app_session.execute(select(Permission.code))).scalars().all()
    )
    for role_code, perm_codes in ROLE_GRANTS.items():
        for pc in perm_codes:
            assert pc in codes, f"role '{role_code}' references unseeded permission '{pc}'"


async def test_system_admin_carries_every_permission(app_session):
    await _seed(app_session)
    role = (
        await app_session.execute(select(Role).where(Role.code == "system_admin"))
    ).scalar_one()
    granted = set(
        (
            await app_session.execute(
                select(Permission.code)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .where(RolePermission.role_id == role.id)
            )
        )
        .scalars()
        .all()
    )
    assert granted == set(ROLE_GRANTS["system_admin"])


async def test_r4app_reimb_catalog_and_admin_officer(app_session):
    """R-4-app additions: the two gate permissions + the Admin Officer role
    (spec §5.5 'Admin Officer review' + §6.1 FMS handoff)."""
    await _seed(app_session)
    codes = set(
        (await app_session.execute(select(Permission.code))).scalars().all()
    )
    assert {"reimb.claim.review", "reimb.claim.fms_update"} <= codes

    role = (
        await app_session.execute(select(Role).where(Role.code == "admin_officer"))
    ).scalar_one()
    granted = set(
        (
            await app_session.execute(
                select(Permission.code)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .where(
                    RolePermission.role_id == role.id,
                    RolePermission.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    assert granted == set(ROLE_GRANTS["admin_officer"])


async def test_reseed_restores_a_revoked_grant(app_session):
    await _seed(app_session)
    role = (
        await app_session.execute(select(Role).where(Role.code == "auditor"))
    ).scalar_one()
    grant = (
        await app_session.execute(
            select(RolePermission).where(RolePermission.role_id == role.id).limit(1)
        )
    ).scalars().first()
    assert grant is not None
    soft_delete(grant)
    await app_session.commit()

    result = await apply_rbac_grants(app_session)
    await app_session.commit()
    assert result["grants_restored"] >= 1, result
    # The auditor grant is live again.
    refreshed = (
        await app_session.execute(
            select(RolePermission).where(RolePermission.id == grant.id)
        )
    ).scalar_one_or_none()
    assert refreshed is not None and refreshed.deleted_at is None
