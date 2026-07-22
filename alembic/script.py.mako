"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

Conventions (docs/standards/database-standards.md):
- Table names: <module_prefix>_<plural> — prefixes core_/reimb_/css_/dmwis_/admin_.
- Every table carries its full mandatory column set (§6) in the revision that
  creates it.
- NEW APPEND-ONLY TABLES must explicitly `REVOKE UPDATE ... FROM oc_app` —
  the schema's default privileges grant UPDATE to future tables.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
