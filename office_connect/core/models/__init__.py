"""Core spine models — importing this package completes ``Base.metadata``.

Alembic's ``env.py`` imports this module so autogenerate sees every table.
"""

from office_connect.core.models.activity import Activity
from office_connect.core.models.activity_tag import ActivityTag, ActivityTagAssignment
from office_connect.core.models.attachment import Attachment
from office_connect.core.models.audit_log import AuditLog
from office_connect.core.models.compliance_deadline import ComplianceDeadline
from office_connect.core.models.feature_flag import FeatureFlag
from office_connect.core.models.holiday import Holiday
from office_connect.core.models.notification import (
    NotificationDelivery,
    NotificationOutbox,
)
from office_connect.core.models.pap_code import ObjectCode, PapCode
from office_connect.core.models.query_log import QueryLog
from office_connect.core.models.report_lineage import ReportLineage
from office_connect.core.models.tenant_config import TenantConfig

__all__ = [
    "Activity",
    "ActivityTag",
    "ActivityTagAssignment",
    "Attachment",
    "AuditLog",
    "ComplianceDeadline",
    "FeatureFlag",
    "Holiday",
    "NotificationDelivery",
    "NotificationOutbox",
    "ObjectCode",
    "PapCode",
    "QueryLog",
    "ReportLineage",
    "TenantConfig",
]
