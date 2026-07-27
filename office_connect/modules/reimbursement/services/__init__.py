"""Reimbursement services — the R-2 per-diem computation engine.

Public surface re-exported here (extended by ``compute`` below); the computation
core (``per_diem``) is pure and I/O-free, the ``compute`` wrapper loads/persists.
"""

from office_connect.modules.reimbursement.services.compute import (
    TOTALS_VERSION,
    compute_claim_totals,
)
from office_connect.modules.reimbursement.services.per_diem import (
    ConfigRow,
    DayBreakdown,
    LegInput,
    PerDiemResult,
    RateRow,
    RegionRow,
    compute_per_diem,
    settle,
)

__all__ = [
    "TOTALS_VERSION",
    "ConfigRow",
    "DayBreakdown",
    "LegInput",
    "PerDiemResult",
    "RateRow",
    "RegionRow",
    "compute_claim_totals",
    "compute_per_diem",
    "settle",
]
