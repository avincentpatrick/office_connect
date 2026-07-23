"""Organizational units — the self-referencing office/division/section tree.

Stage B (Phase 2), core-service #14 (master-plan §1.1). The scoping spine: every
approval role is granted "OF org-unit X" (``core_user_roles.org_unit_id``), and
``core_activities.division_id`` / ``section_id`` resolve here. ``kind`` is an
explicit discriminator — not pure parent-chaining — because the spine models a
division and a section as *separate* columns, so the app must cheaply answer
"is this node a division or a section" (rule: a ``division_id`` references a
``kind='division'`` node, a ``section_id`` a ``kind='section'`` node).
"""

from sqlalchemy import BigInteger, Enum, ForeignKey, Index, Integer, text
from sqlalchemy.orm import Mapped, mapped_column

from office_connect.core.base import (
    AuditColsMixin,
    Base,
    LookupMixin,
    PKMixin,
    SoftDeleteMixin,
)

OrgUnitKind = Enum(
    "office", "division", "section", "unit", name="core_org_unit_kind"
)


class OrgUnit(PKMixin, AuditColsMixin, SoftDeleteMixin, LookupMixin, Base):
    """One node of the org hierarchy. Deactivate, never delete."""

    __tablename__ = "core_org_units"
    __table_args__ = (
        # A live code is unique; a soft-deleted one never blocks re-entry.
        Index(
            "uq_core_org_units_code",
            "code",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_core_org_units_parent_org_unit_id", "parent_org_unit_id"),
        Index("ix_core_org_units_kind", "kind"),
    )

    code: Mapped[str]
    name: Mapped[str]
    kind: Mapped[str] = mapped_column(OrgUnitKind)
    parent_org_unit_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_org_units.id")
    )
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
