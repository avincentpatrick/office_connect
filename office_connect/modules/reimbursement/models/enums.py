"""Native PG enums for the reimbursement module (all named ``reimb_*``).

Verbatim from the build spec §5 (with the delta corrections in
``docs/modules/reimbursement.md`` §2). ``destination_class`` is deliberately absent —
the EO 77 3-cluster model routes rate off a PSGC region → cluster lookup, not a 2-value
enum. ``step_kind`` / approval-step status are absent too — the approval chain runs on
the shared ``core_workflow_*`` engine, not a module-internal runtime table.
"""

from sqlalchemy import Enum

ClaimKind = Enum("reimbursement", "liquidation", name="reimb_claim_kind")
FundSource = Enum("GF_ORS", "TF_BUR", name="reimb_fund_source")
HolderKind = Enum("user", "external_fms", name="reimb_holder_kind")
TransportMode = Enum(
    "plane", "bus", "boat", "taxi", "ride_hail", "gov_vehicle", "other",
    name="reimb_transport_mode",
)
ChecklistGroup = Enum(
    "authority", "itinerary", "proof_of_travel", "transport",
    "lodging_meals", "report", "financial",
    name="reimb_checklist_group",
)
ChecklistEvidence = Enum(
    "upload", "generated_doc", "external_wet_sign", "data_only",
    name="reimb_checklist_evidence",
)
ChecklistItemStatus = Enum(
    "missing", "attached", "generated", "auto_passed", "auto_flagged", "waived",
    name="reimb_checklist_item_status",
)
CashAdvanceStatus = Enum(
    "open", "liquidation_started", "settled", "overdue",
    name="reimb_cash_advance_status",
)
ReturnReasonCategory = Enum(
    "missing_doc", "wrong_amount", "wrong_form", "no_signature", "late",
    "policy", "other",
    name="reimb_return_reason_category",
)
ReturnTarget = Enum("claimant", "previous_step", name="reimb_return_target")
AttachmentCustody = Enum(
    "scanned", "with_accounting", "forwarded_coa", name="reimb_attachment_custody"
)
