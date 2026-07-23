"""Activity tags — GAD / CCET / DRR / UHC attribution as configurable ROWS.

Master-plan §1.1 #15 (connectedness contract): the cross-cutting government
attributions — Gender & Development, Climate Change Expenditure Tagging, Disaster
Risk Reduction, Universal Health Care — are **configurable taxonomy vocabulary +
assignments**, *never boolean columns*. A tenant adds or retires a tag without a
schema change, and reports roll up by ``taxonomy``.

Two tables:
- ``core_activity_tags`` (lookup) — the vocabulary (taxonomy + code + label).
- ``core_activity_tag_assignments`` (business link) — an activity ↔ tag edge,
  giving multi-tag (an activity can be GAD-attributed *and* CCET-adaptation).

``activity_id`` on an assignment is a real FK to ``core_activities`` (that table
exists); the "pick or create / nullable everywhere" rule governs how *modules*
reference activities, not this internal link table.
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

ActivityTaxonomy = Enum(
    "gad", "ccet", "drr", "uhc", name="core_activity_taxonomy"
)


class ActivityTag(PKMixin, AuditColsMixin, SoftDeleteMixin, LookupMixin, Base):
    """One configurable tag within a taxonomy (e.g. taxonomy=``gad``, code=
    ``attributed``). Retire with ``is_active=false``; never delete."""

    __tablename__ = "core_activity_tags"
    __table_args__ = (
        # A live (taxonomy, code) is unique; a soft-deleted one never blocks re-creation.
        Index(
            "uq_core_activity_tags_taxonomy_code",
            "taxonomy",
            "code",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_core_activity_tags_taxonomy", "taxonomy"),
    )

    taxonomy: Mapped[str] = mapped_column(ActivityTaxonomy)
    code: Mapped[str]
    label: Mapped[str]
    description: Mapped[str | None]
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))


class ActivityTagAssignment(PKMixin, AuditColsMixin, SoftDeleteMixin, Base):
    """An activity ↔ tag edge. Re-tagging soft-deletes the old edge (audited)."""

    __tablename__ = "core_activity_tag_assignments"
    __table_args__ = (
        Index(
            "uq_core_activity_tag_assignments_activity_tag",
            "activity_id",
            "activity_tag_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_core_activity_tag_assignments_activity_id", "activity_id"
        ),
        Index(
            "ix_core_activity_tag_assignments_activity_tag_id", "activity_tag_id"
        ),
    )

    activity_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("core_activities.id")
    )
    activity_tag_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("core_activity_tags.id")
    )
