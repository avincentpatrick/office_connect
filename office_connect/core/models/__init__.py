"""Core spine models — importing this package completes ``Base.metadata``.

Alembic's ``env.py`` imports this module so autogenerate sees every table.
"""

from office_connect.core.models.activity import Activity
from office_connect.core.models.audit_log import AuditLog
from office_connect.core.models.feature_flag import FeatureFlag
from office_connect.core.models.query_log import QueryLog
from office_connect.core.models.tenant_config import TenantConfig

__all__ = ["Activity", "AuditLog", "FeatureFlag", "QueryLog", "TenantConfig"]
