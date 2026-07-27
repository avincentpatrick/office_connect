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
from office_connect.core.models.login_attempt import LoginAttempt
from office_connect.core.models.notification import (
    NotificationDelivery,
    NotificationOutbox,
)
from office_connect.core.models.notification_preference import NotificationPreference
from office_connect.core.models.org_unit import OrgUnit
from office_connect.core.models.pap_code import ObjectCode, PapCode
from office_connect.core.models.permission import Permission
from office_connect.core.models.query_log import QueryLog
from office_connect.core.models.report_lineage import ReportLineage
from office_connect.core.models.role import Role
from office_connect.core.models.role_permission import RolePermission
from office_connect.core.models.staff import Staff
from office_connect.core.models.tenant_config import TenantConfig
from office_connect.core.models.user import User
from office_connect.core.models.user_role import UserRole
from office_connect.core.models.workflow import (
    WorkflowDefinition,
    WorkflowDefinitionVersion,
    WorkflowDelegation,
    WorkflowEvent,
    WorkflowInstance,
    WorkflowState,
    WorkflowStep,
    WorkflowTransition,
)

__all__ = [
    "Activity",
    "ActivityTag",
    "ActivityTagAssignment",
    "Attachment",
    "AuditLog",
    "ComplianceDeadline",
    "FeatureFlag",
    "Holiday",
    "LoginAttempt",
    "NotificationDelivery",
    "NotificationOutbox",
    "NotificationPreference",
    "ObjectCode",
    "OrgUnit",
    "PapCode",
    "Permission",
    "QueryLog",
    "ReportLineage",
    "Role",
    "RolePermission",
    "Staff",
    "TenantConfig",
    "User",
    "UserRole",
    "WorkflowDefinition",
    "WorkflowDefinitionVersion",
    "WorkflowDelegation",
    "WorkflowEvent",
    "WorkflowInstance",
    "WorkflowState",
    "WorkflowStep",
    "WorkflowTransition",
]
