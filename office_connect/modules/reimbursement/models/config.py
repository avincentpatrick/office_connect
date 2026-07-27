"""Regulatory config pack + the EO 77 3-cluster DTE rate tables (effective-dated).

``reimb_configs`` holds the §4 non-rate config (deadlines, thresholds, apportionment,
SLA, JO/COS rule) as effective-dated key rows with a legal ``source`` for display. The
per-diem DAILY RATES live in ``reimb_dte_clusters`` (EO 77 Annex A: cluster I/II/III),
routed by ``reimb_region_clusters`` (PSGC region → cluster) — this replaces the spec's
superseded 2-tier ``metro_manila_huc/other`` scheme. All three are effective-dated so a
rate change is a new row, never an in-place edit.
"""

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Date, Index, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from office_connect.core.base import (
    AuditColsMixin,
    Base,
    LookupMixin,
    PKMixin,
    SoftDeleteMixin,
)


class ReimbConfig(PKMixin, AuditColsMixin, SoftDeleteMixin, LookupMixin, Base):
    __tablename__ = "reimb_configs"
    __table_args__ = (
        Index(
            "uq_reimb_configs_key_scope",
            "key",
            "effective_from",
            "tenant_id",
            unique=True,
            postgresql_nulls_not_distinct=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_reimb_configs_key", "key"),
    )

    key: Mapped[str]  # e.g. "liquidation.deadline_calendar_days"
    value: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    value_display: Mapped[str | None]  # human render, e.g. "30 days from return"
    source: Mapped[str | None]  # legal citation, e.g. "COA Circular 97-002"
    effective_from: Mapped[date] = mapped_column(Date)
    tenant_id: Mapped[int | None] = mapped_column(BigInteger)  # NULL = platform default
    notes: Mapped[str | None] = mapped_column(Text)


class ReimbDteCluster(PKMixin, AuditColsMixin, SoftDeleteMixin, LookupMixin, Base):
    """EO 77 Annex A daily DTE rate per destination cluster, effective-dated."""

    __tablename__ = "reimb_dte_clusters"
    __table_args__ = (
        Index(
            "uq_reimb_dte_clusters_cluster_eff",
            "cluster",
            "effective_from",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    cluster: Mapped[str]  # "I" | "II" | "III"
    daily_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    label: Mapped[str | None]
    source: Mapped[str | None]
    effective_from: Mapped[date] = mapped_column(Date)


class ReimbRegionCluster(PKMixin, AuditColsMixin, SoftDeleteMixin, LookupMixin, Base):
    """PSGC region code → EO 77 cluster, effective-dated."""

    __tablename__ = "reimb_region_clusters"
    __table_args__ = (
        Index(
            "uq_reimb_region_clusters_region_eff",
            "region_code",
            "effective_from",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_reimb_region_clusters_cluster", "cluster"),
    )

    region_code: Mapped[str]  # PSGC region code, e.g. "13" (NCR)
    region_name: Mapped[str | None]
    cluster: Mapped[str]  # "I" | "II" | "III"
    effective_from: Mapped[date] = mapped_column(Date)
