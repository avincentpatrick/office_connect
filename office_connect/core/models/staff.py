"""Staff directory — the plantilla-authoritative person registry (core-service #14).

Stage B (Phase 2). Identity is **split** (foundation.md §5 decision, 2026-07-23):
``core_staff`` is the person directory (a superset — most plantilla persons never
log in); ``core_users`` is the auth-account table that references a staff row.
CSS-IS is a separate system that *feeds* person data into this table for display
— there is no code dependency on it; the inbound ingestion lands late in Stage B.
Dev/UAT run on synthetic fixtures (``bootstrap load-fixtures``).

Module person-references (e.g. a future reimbursement claimant) resolve a
person's plantilla/org data through ``core_users.staff_id → core_staff``; the
acting-login columns (``*_by`` / ``actor_id``) point at ``core_users`` instead.
"""

from sqlalchemy import BigInteger, Enum, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from office_connect.core.base import (
    AuditColsMixin,
    Base,
    PKMixin,
    SoftDeleteMixin,
)

EmploymentStatus = Enum(
    "permanent",
    "temporary",
    "casual",
    "coterminous",
    "contractual",
    "contract_of_service",
    "job_order",
    name="core_employment_status",
)


class Staff(PKMixin, AuditColsMixin, SoftDeleteMixin, Base):
    """A person on the plantilla. Deactivate/soft-delete on offboarding — the
    row is never hard-deleted, so historical references stay resolvable."""

    __tablename__ = "core_staff"
    __table_args__ = (
        Index(
            "uq_core_staff_employee_no",
            "employee_no",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # Work email is optional but unique among live rows when present.
        Index(
            "uq_core_staff_email",
            "email",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND email IS NOT NULL"),
        ),
        Index("ix_core_staff_division_id", "division_id"),
        Index("ix_core_staff_section_id", "section_id"),
        Index("ix_core_staff_surname", "surname"),
    )

    employee_no: Mapped[str]
    given_name: Mapped[str]
    middle_name: Mapped[str | None]
    surname: Mapped[str]
    full_name: Mapped[str]
    email: Mapped[str | None]
    position_title: Mapped[str | None]
    plantilla_item_no: Mapped[str | None]
    employment_status: Mapped[str | None] = mapped_column(EmploymentStatus)
    division_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_org_units.id")
    )
    section_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_org_units.id")
    )
