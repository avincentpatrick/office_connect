"""Roles — named permission bundles (Stage B / Phase 2, RBAC).

Lookup table: admin-editable, deactivate never delete. Code authorizes against
PERMISSION strings, never role names (auth-rbac-onprem.md) — a role is just a
grouping the admin console composes. ``is_system`` protects the built-in roles
(``system_admin``, ``auditor``) from being retired.
"""

from sqlalchemy import Index, false, text
from sqlalchemy.orm import Mapped, mapped_column

from office_connect.core.base import (
    AuditColsMixin,
    Base,
    LookupMixin,
    PKMixin,
    SoftDeleteMixin,
)


class Role(PKMixin, AuditColsMixin, SoftDeleteMixin, LookupMixin, Base):
    __tablename__ = "core_roles"
    __table_args__ = (
        Index(
            "uq_core_roles_code",
            "code",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    code: Mapped[str]
    name: Mapped[str]
    description: Mapped[str | None]
    is_system: Mapped[bool] = mapped_column(server_default=false())
