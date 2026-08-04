"""Reimbursement models — importing this package registers every ``reimb_*`` table
on the shared ``Base.metadata`` (Alembic autogenerate + migrations see them).

All models subclass ``office_connect.core.base.Base`` and consume core via FK only
(module → core; never the reverse — lint-imports). Deferred vs the build spec §5:
``reimb_approval_steps`` is superseded by ``core_workflow_steps`` (dropped);
``reimb_signatory_configs`` is the workflow definition (authored at R-4-app).
``reimb_template_maps`` landed at R-5 as a *binding* table (catalog code →
registered document key), not the spec's placeholder-merge map — the Jinja
template is the field mapping now. Candidate for core-service #13 at Stage E.
"""

from office_connect.modules.reimbursement.models.cash_advance import ReimbCashAdvance
from office_connect.modules.reimbursement.models.checklist import (
    ReimbChecklistCatalog,
    ReimbChecklistItem,
)
from office_connect.modules.reimbursement.models.claim import (
    ReimbClaim,
    ReimbItineraryLeg,
)
from office_connect.modules.reimbursement.models.config import (
    ReimbConfig,
    ReimbDteCluster,
    ReimbRegionCluster,
)
from office_connect.modules.reimbursement.models.returns import (
    ReimbReturnEvent,
    ReimbReturnReasonCatalog,
)
from office_connect.modules.reimbursement.models.templates import ReimbTemplateMap
from office_connect.modules.reimbursement.models.tracking import (
    ReimbAttachment,
    ReimbExternalEvent,
    ReimbStatusHistory,
)

__all__ = [
    "ReimbCashAdvance",
    "ReimbChecklistCatalog",
    "ReimbChecklistItem",
    "ReimbClaim",
    "ReimbItineraryLeg",
    "ReimbConfig",
    "ReimbDteCluster",
    "ReimbRegionCluster",
    "ReimbReturnEvent",
    "ReimbReturnReasonCatalog",
    "ReimbAttachment",
    "ReimbExternalEvent",
    "ReimbStatusHistory",
    "ReimbTemplateMap",
]
