"""Claim status vocabulary — the module's read-model of the workflow states.

``reimb_claims.status`` stores the engine state code VERBATIM (identity mapping —
one vocabulary, no translation table). Legality of every move is the engine's
closed transitions set (workflow-standards.md §1), not DDL: the column stays a
plain varchar by decision (delta register; db-standards §5 deviation recorded).
Display strings live here so the future wizard/My-Work UI renders labels, never
raw codes, and spec §6.1's "one next action, always" auto-copy is a lookup.

The FMS journey sub-statuses (With Budget / With Accounting / Payment
Processing) are NOT states — they ride ``reimb_external_events`` at R-7; the
engine holds one ``handed_to_fms`` state for the whole external leg (delta
register).
"""

from __future__ import annotations

# --- Engine state codes (the status vocabulary) ---------------------------
DRAFT = "draft"
DIVISION_APPROVAL = "division_approval"
ADMIN_REVIEW = "admin_review"
HANDED_TO_FMS = "handed_to_fms"
FMS_RETURNED = "fms_returned"
RETURNED = "returned"
PAID_CLOSED = "paid_closed"
CANCELLED = "cancelled"

ALL_STATES: tuple[str, ...] = (
    DRAFT,
    DIVISION_APPROVAL,
    ADMIN_REVIEW,
    HANDED_TO_FMS,
    FMS_RETURNED,
    RETURNED,
    PAID_CLOSED,
    CANCELLED,
)

TERMINAL_STATES: frozenset[str] = frozenset({PAID_CLOSED, CANCELLED})

# States where the claimant holds the ball (owner-held; holder = claimant's user).
CLAIMANT_STATES: frozenset[str] = frozenset({DRAFT, RETURNED})

# The one state held by FMS — outside the platform (spec §6.1 row 6).
EXTERNAL_STATES: frozenset[str] = frozenset({HANDED_TO_FMS})

# --- Display labels (spec §6.1 status names) -------------------------------
STATUS_LABELS: dict[str, str] = {
    DRAFT: "Draft",
    DIVISION_APPROVAL: "For Approval",
    ADMIN_REVIEW: "Admin Review",
    HANDED_TO_FMS: "Handed to FMS",
    FMS_RETURNED: "FMS Returned",
    RETURNED: "Returned",
    PAID_CLOSED: "Paid / Closed",
    CANCELLED: "Cancelled/Void",
}

# --- "One next action, always" (spec §7 rule 2; §6.1 auto-copy, verbatim) ---
# Terminal states carry None — the journey is over (spec shows "—").
NEXT_ACTION: dict[str, str | None] = {
    DRAFT: "Complete your packet",
    DIVISION_APPROVAL: "Approve or return",
    ADMIN_REVIEW: "Final check & print packet",
    HANDED_TO_FMS: "Waiting on FMS — update status",
    FMS_RETURNED: "Relay FMS comments",
    RETURNED: "Fix and resubmit",
    PAID_CLOSED: None,
    CANCELLED: None,
}
