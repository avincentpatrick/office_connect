"""Role → permission grants (Stage B / Phase 2, RBAC).

A soft-deletable mapping, NOT a bare join table: a revoked grant survives as a
tombstoned (soft-deleted) row so "which permissions did role X carry in March"
stays answerable (auth-rbac-onprem.md — revoked grants are soft-deleted rows).
The partial-unique on ``(role_id, permission_id)`` lets a revoked-then-regranted
pair be re-inserted.
"""

from sqlalchemy import BigInteger, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from office_connect.core.base import (
    AuditColsMixin,
    Base,
    PKMixin,
    SoftDeleteMixin,
)


class RolePermission(PKMixin, AuditColsMixin, SoftDeleteMixin, Base):
    __tablename__ = "core_role_permissions"
    __table_args__ = (
        Index(
            "uq_core_role_permissions_role_id",
            "role_id",
            "permission_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_core_role_permissions_role_id", "role_id"),
        Index("ix_core_role_permissions_permission_id", "permission_id"),
    )

    role_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("core_roles.id"))
    permission_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("core_permissions.id")
    )
