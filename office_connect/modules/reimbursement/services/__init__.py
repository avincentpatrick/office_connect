"""Reimbursement services — per-diem computation (R-2) + claim lifecycle (R-4-app).

Public surface re-exported here. The computation core (``per_diem``) is pure and
I/O-free; ``compute`` loads/persists; ``lifecycle`` is the SINGLE sanctioned
mutation path onto the shared workflow engine (submit / act / status sync /
holder resolution); ``notify`` delivers the holder-only SLA nudges; ``status``
is the claim-status vocabulary (engine state codes + labels + next-action copy).
"""

from office_connect.modules.reimbursement.services.compute import (
    TOTALS_VERSION,
    compute_claim_totals,
)
from office_connect.modules.reimbursement.services.lifecycle import (
    cancel_draft_claim,
    claim_action,
    config_working_days,
    resolve_holder,
    submit_claim,
)
from office_connect.modules.reimbursement.services.notify import (
    notify_escalation,
    sweep_sla_reminders,
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
    "cancel_draft_claim",
    "claim_action",
    "compute_claim_totals",
    "compute_per_diem",
    "config_working_days",
    "notify_escalation",
    "resolve_holder",
    "settle",
    "submit_claim",
    "sweep_sla_reminders",
]
