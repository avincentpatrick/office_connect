"""Reimbursement document generation (R-5) — the module's consumer of
core-services #8 (template → PDF) and #3 (frozen snapshots).

Importing this package registers the module's three GAM forms with core, so a
consumer only needs ``from ...documents import service``.
"""

from office_connect.modules.reimbursement.documents.registry import (
    AR_01,
    DV_32,
    IOT_45,
    SPECS,
    register,
)
from office_connect.modules.reimbursement.documents.service import (
    SUBJECT_KIND,
    GeneratedDocument,
    generate_claim_documents,
)

__all__ = [
    "AR_01",
    "DV_32",
    "IOT_45",
    "SPECS",
    "SUBJECT_KIND",
    "GeneratedDocument",
    "generate_claim_documents",
    "register",
]
