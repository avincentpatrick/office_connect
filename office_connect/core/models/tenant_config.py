"""Tenant identity + branding — one row per tenant (business table)."""

from typing import Any

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from office_connect.core.base import AuditColsMixin, Base, PKMixin, SoftDeleteMixin


class TenantConfig(PKMixin, AuditColsMixin, SoftDeleteMixin, Base):
    __tablename__ = "core_tenant_configs"

    name: Mapped[str]
    short_name: Mapped[str]
    # Display timezone only — storage is always UTC (database-standards.md §9).
    timezone: Mapped[str] = mapped_column(server_default="Asia/Manila")
    # Branding values feed the UI design-token contract (ui-standards.md §2)
    # via GET /api/v1/config.
    branding: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
