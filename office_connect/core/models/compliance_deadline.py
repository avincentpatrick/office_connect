"""Statutory compliance deadlines — the government calendar as effective-dated data.

Master-plan §1.1 #11 + §3.4. Every statutory deadline (CSMR, FOI registry, BAR/FAR
suite, BED, APP, PMR, RPCI/RPCPPE, PIF, SPMS ladder, GAD-AR, NPC renewal, ISO
surveillance, liquidation clocks, PAR/ICS, Transparency Seal, …) lives here as a
row, not code — effective-dated and **tenant-overridable** (``tenant_id`` NULL =
platform default; set = a tenant's override). Feeds the Government Outputs
countdown cards; working-day math via ``core/workdays.py`` when
``use_working_day_math``. Seeded by Group G.
"""

from datetime import date
from typing import Any

from sqlalchemy import BigInteger, Date, Enum, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from office_connect.core.base import (
    AuditColsMixin,
    Base,
    LookupMixin,
    PKMixin,
    SoftDeleteMixin,
)

DeadlineCadence = Enum(
    "annual",
    "semiannual",
    "quarterly",
    "monthly",
    "per_event",
    "custom",
    name="core_deadline_cadence",
)


class ComplianceDeadline(PKMixin, AuditColsMixin, SoftDeleteMixin, LookupMixin, Base):
    __tablename__ = "core_compliance_deadlines"
    __table_args__ = (
        # One platform default per (code, effective_from)…
        Index(
            "uq_core_compliance_deadlines_default",
            "code",
            "effective_from",
            unique=True,
            postgresql_where=text("tenant_id IS NULL AND deleted_at IS NULL"),
        ),
        # …and one override per (code, tenant, effective_from).
        Index(
            "uq_core_compliance_deadlines_tenant",
            "code",
            "tenant_id",
            "effective_from",
            unique=True,
            postgresql_where=text("tenant_id IS NOT NULL AND deleted_at IS NULL"),
        ),
        Index("ix_core_compliance_deadlines_code", "code"),
        Index("ix_core_compliance_deadlines_tenant_id", "tenant_id"),
        Index("ix_core_compliance_deadlines_cadence", "cadence"),
    )

    code: Mapped[str]
    name: Mapped[str]
    authority: Mapped[str]
    cadence: Mapped[str] = mapped_column(DeadlineCadence)
    due_rule: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    use_working_day_math: Mapped[bool] = mapped_column(server_default=text("true"))
    tenant_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_tenant_configs.id")
    )  # NULL = platform default
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
