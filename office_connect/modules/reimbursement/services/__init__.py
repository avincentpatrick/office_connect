"""Reimbursement services — per-diem computation (R-2) + claim lifecycle (R-4-app).

Public surface re-exported here. The computation core (``per_diem``) is pure and
I/O-free; ``compute`` loads/persists; ``lifecycle`` is the SINGLE sanctioned
mutation path onto the shared workflow engine (submit / act / status sync /
holder resolution); ``drafts`` mutates the claimant-held business fields
(R-2-wizard — never status/holder); ``notify`` delivers the holder-only SLA
nudges; ``status`` is the claim-status vocabulary (engine state codes + labels
+ next-action copy); ``checklist`` + ``checklist_facts`` + ``attachments``
materialize the documentary packet over core-service #7 and take uploads
through core-service #2 (R-3); ``deadline`` is the pure COA 30-day clock and
``cash_advance`` is the SINGLE sanctioned writer of ``reimb_cash_advances``
(R-6-clock) — ``notify`` also carries that clock's D-7/D-3/D-0/overdue ladder.
"""

from office_connect.modules.reimbursement.services.checklist import (
    ChecklistRow,
    ChecklistView,
    assert_packet_complete,
    assert_persisted_packet_complete,
    attach_evidence,
    checklist_summary,
    checklist_view,
    detach_evidence,
    persisted_packet_complete,
    refresh_checklist,
)
from office_connect.modules.reimbursement.services.cash_advance import (
    UNLIQUIDATED_STATUSES,
    create_cash_advance,
    get_cash_advance,
    link_claim,
    list_cash_advances,
    mark_liquidation_started,
    mark_overdue,
    open_cash_advance_for,
    overdue_note,
    remirror_deadline,
    resolve_deadline,
    update_cash_advance,
)
from office_connect.modules.reimbursement.services.checklist_facts import (
    FACTS_VERSION,
    build_claim_facts,
)
from office_connect.modules.reimbursement.services.deadline import (
    DEADLINE_KEY,
    DeadlineRule,
    deadline_state,
    days_remaining,
    liquidation_deadline,
    read_rule,
)
from office_connect.modules.reimbursement.services.compute import (
    TOTALS_VERSION,
    compute_claim_totals,
)
from office_connect.modules.reimbursement.services.drafts import (
    EDITABLE_FIELDS,
    recompute_totals,
    replace_legs,
    update_draft_fields,
)
from office_connect.modules.reimbursement.services.lifecycle import (
    cancel_draft_claim,
    claim_action,
    config_working_days,
    create_draft_claim,
    resolve_holder,
    submit_claim,
)
from office_connect.modules.reimbursement.services.liquidation import (
    liquidation_for_advance,
    start_liquidation,
)
from office_connect.modules.reimbursement.services.notify import (
    notify_escalation,
    sweep_liquidation_reminders,
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
    "assert_packet_complete",
    "liquidation_for_advance",
    "start_liquidation",
    "assert_persisted_packet_complete",
    "attach_evidence",
    "build_claim_facts",
    "cancel_draft_claim",
    "checklist_summary",
    "checklist_view",
    "ChecklistRow",
    "ChecklistView",
    "claim_action",
    "compute_claim_totals",
    "compute_per_diem",
    "config_working_days",
    "ConfigRow",
    "create_cash_advance",
    "create_draft_claim",
    "DayBreakdown",
    "days_remaining",
    "DEADLINE_KEY",
    "deadline_state",
    "DeadlineRule",
    "detach_evidence",
    "EDITABLE_FIELDS",
    "FACTS_VERSION",
    "get_cash_advance",
    "LegInput",
    "link_claim",
    "liquidation_deadline",
    "list_cash_advances",
    "mark_liquidation_started",
    "mark_overdue",
    "notify_escalation",
    "open_cash_advance_for",
    "overdue_note",
    "PerDiemResult",
    "persisted_packet_complete",
    "RateRow",
    "read_rule",
    "recompute_totals",
    "refresh_checklist",
    "RegionRow",
    "remirror_deadline",
    "replace_legs",
    "resolve_deadline",
    "resolve_holder",
    "settle",
    "submit_claim",
    "sweep_liquidation_reminders",
    "sweep_sla_reminders",
    "TOTALS_VERSION",
    "UNLIQUIDATED_STATUSES",
    "update_cash_advance",
    "update_draft_fields",
]
