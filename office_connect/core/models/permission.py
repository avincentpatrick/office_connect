"""Permissions — the dotted authorization strings (Stage B / Phase 2, RBAC).

Lookup table, seeded from a code catalog (``core/seeds/rbac.py``). Code checks a
permission string (e.g. ``reimb.claim.approve``); the DB decides which roles carry
it. A startup/test gate asserts every permission a role references exists here
(the classic RBAC role→permission indirection, NIST RBAC).
"""

from sqlalchemy import Index, text
from sqlalchemy.orm import Mapped, mapped_column

from office_connect.core.base import (
    AuditColsMixin,
    Base,
    LookupMixin,
    PKMixin,
    SoftDeleteMixin,
)


class Permission(PKMixin, AuditColsMixin, SoftDeleteMixin, LookupMixin, Base):
    __tablename__ = "core_permissions"
    __table_args__ = (
        Index(
            "uq_core_permissions_code",
            "code",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_core_permissions_category", "category"),
    )

    code: Mapped[str]
    name: Mapped[str]
    description: Mapped[str | None]
    category: Mapped[str | None]
