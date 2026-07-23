"""tenant settings bag — non-public JSONB on core_tenant_configs

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-23

Adds ``core_tenant_configs.settings`` — a general-purpose, **non-public** JSONB
bag for tenant configuration that must NOT be exposed by ``GET /api/v1/config``
(which serves only ``branding``). First consumer: the Increment-3 bootstrap CLI
records the designated System Admin under ``settings.bootstrap_admin`` for Stage
B to promote to a real user (no ``core_users`` table exists yet — that identity
decision is deferred to Stage B, foundation.md §5).

``oc_app`` already holds table-level UPDATE on ``core_tenant_configs`` (granted
in 0001), which covers columns added later — no grant change needed.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "core_tenant_configs",
        sa.Column(
            "settings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("core_tenant_configs", "settings")
