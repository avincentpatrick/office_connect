"""The reimbursement module router — the codebase's FIRST module HTTP surface.

Self-prefixed ``/api/v1/reimbursement`` and mounted from ``office_connect/
main.py`` (the composition root): ``core/api/router.py`` may not include it
because core never imports modules (import-linter). The whole surface sits
behind ``require_feature("module.reimbursement")`` — flag OFF → 404 on every
route, fail-safe, before auth (an OFF module is indistinguishable from
absent). Safe for now because no approval-ACTION endpoints exist here yet;
when they land they must NOT sit behind this gate (workflow-standards §9 —
in-flight items always finish). Recorded in api-standards §9 + the module
delta register.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from office_connect.core.auth.dependencies import require_feature
from office_connect.modules.reimbursement.api import claims, my_work, reference
from office_connect.modules.reimbursement.workflow import FEATURE_FLAG_KEY

router = APIRouter(
    prefix="/api/v1/reimbursement",
    tags=["reimbursement"],
    dependencies=[Depends(require_feature(FEATURE_FLAG_KEY))],
)
router.include_router(claims.router)
router.include_router(my_work.router)
router.include_router(reference.router)
