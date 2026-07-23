"""User → role grants, org-unit-scoped (Stage B / Phase 2, RBAC).

A soft-deletable, optionally org-scoped grant. ``org_unit_id`` NULL = a global
grant (e.g. system admin); set = scoped ("Division Chief OF org-unit X") — the
approval flow resolves an approver by walking the requester's org-unit ancestry
(auth-rbac-onprem.md). ``valid_from`` / ``valid_to`` carry the time window a B3
delegation/OIC grant is active (built now so B3 needs no schema migration).

**Grant uniqueness uses ``NULLS NOT DISTINCT``** (Postgres 16): a plain partial
unique would let two ``(user, role, NULL)`` global grants both insert because
``NULL != NULL``. With ``NULLS NOT DISTINCT`` the two NULLs collide and the
duplicate is rejected.
"""

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from office_connect.core.base import (
    AuditColsMixin,
    Base,
    PKMixin,
    SoftDeleteMixin,
)


class UserRole(PKMixin, AuditColsMixin, SoftDeleteMixin, Base):
    __tablename__ = "core_user_roles"
    __table_args__ = (
        Index(
            "uq_core_user_roles_grant",
            "user_id",
            "role_id",
            "org_unit_id",
            unique=True,
            postgresql_nulls_not_distinct=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_core_user_roles_user_id", "user_id"),
        Index("ix_core_user_roles_role_id", "role_id"),
        Index("ix_core_user_roles_org_unit_id", "org_unit_id"),
    )

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("core_users.id"))
    role_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("core_roles.id"))
    org_unit_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_org_units.id")
    )
    valid_from: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
