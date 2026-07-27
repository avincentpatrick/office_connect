"""RBAC seed data — the permission catalog, baseline roles, and default grants.

Stage B (Phase 2), auth-rbac-onprem.md. Code authorizes against permission
STRINGS (never role names); this module is the single source of the baseline
catalog and the built-in role→permission mapping the admin console starts from.

- ``PERMISSIONS_DATASET`` / ``ROLES_DATASET`` are ordinary idempotent
  ``SeedDataset``s (upsert by ``code``), registered in ``datasets.REGISTRY`` so
  ``load-reference`` seeds the catalogs in every environment (they are public
  config, not synthetic data).
- ``apply_rbac_grants`` wires ``core_role_permissions`` from ``ROLE_GRANTS``. It
  is bespoke (the natural key is ``(role_id, permission_id)`` — surrogate ids
  unknown at authoring): it inserts missing grants, RESTORES soft-deleted ones,
  and **soft-deletes (tombstones) grants no longer in the map** so a revocation
  survives as an auditable row (auth-rbac-onprem.md).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.models import Permission, Role, RolePermission
from office_connect.core.seeds.base import SeedDataset
from office_connect.core.soft_delete import soft_delete

_ALL = ("all",)

# --- Permission catalog: (code, human label, category) -------------------
# Code is the stable authorization string checked in code; the DB decides which
# roles carry it. ``reimb.*`` is a placeholder proving the cross-module pattern —
# it is not wired to any endpoint until Stage C.
_PERMISSION_CATALOG: tuple[tuple[str, str, str], ...] = (
    # user lifecycle (admin-only provisioning; no self-registration)
    ("user.create", "Create user accounts", "auth"),
    ("user.read", "View user accounts", "auth"),
    ("user.update", "Edit user accounts", "auth"),
    ("user.deactivate", "Deactivate user accounts", "auth"),
    ("user.password.reset", "Reset a user's password", "auth"),
    ("session.read", "View active sessions", "auth"),
    ("session.revoke", "Revoke sessions", "auth"),
    # RBAC administration
    ("rbac.role.read", "View roles", "rbac"),
    ("rbac.role.create", "Create roles", "rbac"),
    ("rbac.role.update", "Edit roles", "rbac"),
    ("rbac.role.grant", "Grant a role to a user", "rbac"),
    ("rbac.role.revoke", "Revoke a role from a user", "rbac"),
    ("rbac.permission.read", "View permissions", "rbac"),
    # org units
    ("orgunit.read", "View org units", "orgunit"),
    ("orgunit.manage", "Manage the org-unit tree", "orgunit"),
    # audit (COA Res. 2020-034 read-only auditor)
    ("audit.read", "View the audit trail", "audit"),
    ("audit.verify", "Run/print chain verification", "audit"),
    # platform admin
    ("admin.config.read", "View tenant config", "admin"),
    ("admin.config.update", "Edit tenant config", "admin"),
    ("admin.featureflag.manage", "Manage feature flags", "admin"),
    # staff directory
    ("staff.read", "View the staff directory", "staff"),
    ("staff.import", "Import staff records", "staff"),
    ("staff.manage", "Edit staff records", "staff"),
    # attachments (Stage B / Increment 4 — coarse gate until Stage-C holder scoping)
    ("attachment.upload", "Upload attachments", "attachment"),
    ("attachment.read", "View attachment metadata", "attachment"),
    ("attachment.download", "Download attachment content", "attachment"),
    ("attachment.delete", "Soft-delete an attachment", "attachment"),
    ("attachment.dispose.read", "View the disposal-eligibility report", "attachment"),
    # reimbursement (placeholder — pattern only, wired at Stage C)
    ("reimb.claim.create", "Create a reimbursement claim", "reimb"),
    ("reimb.claim.read", "View reimbursement claims", "reimb"),
    ("reimb.claim.submit", "Submit a reimbursement claim", "reimb"),
    ("reimb.claim.approve", "Approve a reimbursement claim", "reimb"),
)

_ALL_PERMISSION_CODES: tuple[str, ...] = tuple(c for c, _, _ in _PERMISSION_CATALOG)

# --- Baseline roles: (code, name, is_system) -----------------------------
_ROLE_CATALOG: tuple[tuple[str, str, bool], ...] = (
    ("system_admin", "System Administrator", True),
    ("auditor", "Auditor (read-only)", True),
    ("approver", "Approver", False),
    ("staff", "Staff", False),
)

# --- Default role → permission grants ------------------------------------
# system_admin carries every permission. auditor is strictly read-only
# (COA Res. 2020-034). approver/staff are org-scoped at grant time.
ROLE_GRANTS: dict[str, tuple[str, ...]] = {
    "system_admin": _ALL_PERMISSION_CODES,
    "auditor": (
        "audit.read",
        "audit.verify",
        "session.read",
        "user.read",
        "rbac.role.read",
        "rbac.permission.read",
        "orgunit.read",
        "staff.read",
        "admin.config.read",
        # Read-only records posture: metadata + the retention report, NOT raw
        # content bytes (which may carry SPI; downloads are holder-scoped in Stage C).
        "attachment.read",
        "attachment.dispose.read",
    ),
    "approver": (
        "reimb.claim.read",
        "reimb.claim.approve",
        "attachment.read",
        "attachment.download",
    ),
    "staff": (
        "reimb.claim.create",
        "reimb.claim.read",
        "reimb.claim.submit",
        "attachment.upload",
        "attachment.read",
        "attachment.download",
    ),
}


PERMISSIONS_DATASET = SeedDataset(
    name="permissions",
    owner="Security / System Admin",
    cadence="on_revision",
    environments=_ALL,
    model=Permission,
    natural_key=("code",),
    rows=tuple(
        {"code": code, "name": name, "category": category}
        for code, name, category in _PERMISSION_CATALOG
    ),
)

ROLES_DATASET = SeedDataset(
    name="roles",
    owner="Security / System Admin",
    cadence="on_revision",
    environments=_ALL,
    model=Role,
    natural_key=("code",),
    rows=tuple(
        {"code": code, "name": name, "is_system": is_system}
        for code, name, is_system in _ROLE_CATALOG
    ),
)


async def apply_rbac_grants(session: AsyncSession) -> dict[str, Any]:
    """Idempotently reconcile ``core_role_permissions`` to ``ROLE_GRANTS``.

    Insert missing grants, restore tombstoned ones, and soft-delete grants no
    longer wanted. Raises if a role/permission code is not seeded (the "every
    code exists in the DB" gate). Requires the catalogs seeded first."""
    roles = {
        r.code: r for r in (await session.execute(select(Role))).scalars().all()
    }
    perms = {
        p.code: p
        for p in (await session.execute(select(Permission))).scalars().all()
    }

    inserted = restored = unchanged = revoked = 0
    for role_code, perm_codes in ROLE_GRANTS.items():
        role = roles.get(role_code)
        if role is None:
            raise RuntimeError(
                f"role '{role_code}' not seeded — seed the role catalog first"
            )
        want_ids: set[int] = set()
        for pc in perm_codes:
            perm = perms.get(pc)
            if perm is None:
                raise RuntimeError(
                    f"permission '{pc}' (referenced by role '{role_code}') "
                    "is not in the permission catalog"
                )
            want_ids.add(perm.id)

        existing = (
            (
                await session.execute(
                    select(RolePermission)
                    .where(RolePermission.role_id == role.id)
                    .execution_options(include_deleted=True)
                )
            )
            .scalars()
            .all()
        )
        live = {rp.permission_id: rp for rp in existing if rp.deleted_at is None}
        tombstoned: dict[int, RolePermission] = {}
        for rp in existing:
            if rp.deleted_at is not None:
                tombstoned.setdefault(rp.permission_id, rp)

        for pid in want_ids:
            if pid in live:
                unchanged += 1
            elif pid in tombstoned:
                rp = tombstoned[pid]
                rp.deleted_at = None
                rp.deleted_by = None
                restored += 1
            else:
                session.add(RolePermission(role_id=role.id, permission_id=pid))
                inserted += 1

        for pid, rp in live.items():
            if pid not in want_ids:
                soft_delete(rp)
                revoked += 1

    await session.flush()
    return {
        "grants_inserted": inserted,
        "grants_restored": restored,
        "grants_unchanged": unchanged,
        "grants_revoked": revoked,
    }
