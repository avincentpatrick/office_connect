"""The reimbursement module router — the codebase's FIRST module HTTP surface.

Self-prefixed ``/api/v1/reimbursement`` and mounted from ``office_connect/
main.py`` (the composition root): ``core/api/router.py`` may not include it
because core never imports modules (import-linter). This surface sits behind
``require_feature("module.reimbursement")`` — flag OFF → 404 on every route,
fail-safe, before auth (an OFF module is indistinguishable from absent).

R-4-screens split the module's HTTP surface in two: the approver's decision
endpoints live on ``api/actions.py``, a SECOND top-level router mounted
separately and deliberately WITHOUT this gate — the flag blocks new work but
never strands work in progress (workflow-standards §9). It cannot be included
here: a router's ``dependencies`` apply to everything beneath it. Recorded in
api-standards §9 + the module delta register.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from office_connect.core.auth.dependencies import require_feature
from office_connect.modules.reimbursement.api import (
    cash_advances,
    checklist,
    claims,
    external,
    insights,
    my_work,
    queue,
    reference,
    tracking,
)
from office_connect.modules.reimbursement.workflow import FEATURE_FLAG_KEY

router = APIRouter(
    prefix="/api/v1/reimbursement",
    tags=["reimbursement"],
    dependencies=[Depends(require_feature(FEATURE_FLAG_KEY))],
)
router.include_router(claims.router)
router.include_router(cash_advances.router)
router.include_router(checklist.router)
router.include_router(external.router)
router.include_router(insights.router)
router.include_router(my_work.router)
router.include_router(queue.router)
router.include_router(reference.router)
router.include_router(tracking.router)
