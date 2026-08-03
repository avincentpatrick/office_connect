"""Wire schemas for the reimbursement HTTP surface (api-standards §3).

Plain pydantic models, hand-mapped in ``api/deps.py`` (house style — no
``model_validate``). Money crosses the wire as 2-dp STRINGS, server-computed —
the client never does arithmetic (api-standards §2); ``totals`` is the compute
snapshot verbatim. Request models are the wire whitelist: field names mirror
``services/drafts.py::EDITABLE_FIELDS`` exactly.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

TransportMode = Literal[
    "plane", "bus", "boat", "taxi", "ride_hail", "gov_vehicle", "other"
]
FundSource = Literal["GF_ORS", "TF_BUR"]

_TIME_RE = r"^\d{2}:\d{2}$"


# --- Requests ---------------------------------------------------------------


class ClaimDraftIn(BaseModel):
    """Optional prefill accepted at draft creation (same whitelist as PATCH).
    The router applies ``model_dump(exclude_unset=True)``, so an omitted field
    is not a write; explicit null on a NOT NULL column means "no change"."""

    activity_id: int | None = None
    dpo_no: str | None = Field(default=None, max_length=100)
    dpo_date: date | None = None
    purpose: str | None = Field(default=None, max_length=2000)
    destination: str | None = Field(default=None, max_length=2000)
    destination_region_code: str | None = Field(default=None, max_length=10)
    date_depart: date | None = None
    date_return: date | None = None
    is_within_50km: bool | None = None
    overnight_stay: bool | None = None
    fund_source: FundSource | None = None
    other_total: Decimal | None = Field(default=None, ge=0)


class ClaimPatch(ClaimDraftIn):
    """Partial update of a claimant-held claim — identical whitelist."""


class LegIn(BaseModel):
    """One itinerary row. ``id`` present = update that leg of THIS claim;
    absent = insert. ``per_diem_*``/``leg_total`` are server-written and not
    accepted here."""

    id: int | None = None
    leg_date: date | None = None
    place: str | None = Field(default=None, max_length=500)
    destination_region_code: str | None = Field(default=None, max_length=10)
    time_depart: str | None = Field(default=None, pattern=_TIME_RE)
    time_arrive: str | None = Field(default=None, pattern=_TIME_RE)
    transport_mode: TransportMode | None = None
    fare: Decimal | None = Field(default=None, ge=0)
    lodging_provided: bool = False
    meals_provided: bool = False


class LegsReplaceIn(BaseModel):
    legs: list[LegIn] = Field(max_length=50)


class CancelIn(BaseModel):
    comment: str = Field(min_length=1, max_length=2000)


class ApproveIn(BaseModel):
    """Clear the current gate. ``expected_version`` is the CAS token from
    ``ClaimDetail.row_version`` (workflow-standards §4) — omit it and you race
    whoever else holds the claim; send it and a moved claim 409s
    ``stale_workflow_version`` instead of acting on a stale screen."""

    comment: str | None = Field(default=None, max_length=2000)
    expected_version: int | None = None


class ReturnIn(BaseModel):
    """Bounce the claim back. ≥1 taxonomy reason (spec §5.6) AND a comment (the
    engine's ``requires_comment`` on every authored return transition) — the
    service re-validates both against the live catalog, so this is the wire
    whitelist, not the enforcement."""

    comment: str = Field(min_length=1, max_length=2000)
    reason_ids: list[int] = Field(min_length=1, max_length=20)
    expected_version: int | None = None


# --- Responses ---------------------------------------------------------------


class OrgUnitRef(BaseModel):
    id: int
    name: str


class ClaimantOut(BaseModel):
    """Directory prefill block (WCAG 2.2 §3.3.7 — the FE displays, never
    re-asks; ``/auth/me`` carries no staff identity by design)."""

    staff_id: int
    employee_no: str | None = None
    full_name: str | None = None
    position_title: str | None = None
    employment_status: str | None = None
    division: OrgUnitRef | None = None
    section: OrgUnitRef | None = None


class LegOut(BaseModel):
    id: int
    seq: int
    leg_date: date | None = None
    place: str | None = None
    destination_region_code: str | None = None
    time_depart: str | None = None
    time_arrive: str | None = None
    transport_mode: str | None = None
    fare: str | None = None
    per_diem_pct: int | None = None
    per_diem_amount: str | None = None
    leg_total: str | None = None
    lodging_provided: bool
    meals_provided: bool


# --- R-3: the documentary packet -------------------------------------------


class ChecklistBlockerOut(BaseModel):
    """One reason submit is refused — everything the UI needs to link to the fix."""

    catalog_id: int
    item_id: int | None = None
    code: str
    label: str
    group: str
    evidence: str
    reason: str = "missing"


class ChecklistFlagOut(BaseModel):
    """An auto-check that flagged. Never blocks (spec §5.3) — it informs."""

    catalog_id: int
    code: str
    label: str
    check_type: str
    reason: str
    message: str
    detail: dict[str, Any] = {}
    remedy: str | None = None


class ChecklistSummaryOut(BaseModel):
    """The gate's answer + the progress line + the approver's flags.

    Always present on ``ClaimDetail``, never null: an engine with nothing to say
    answers zeroes, so the client has one shape to render rather than two.
    """

    required_total: int = 0
    required_done: int = 0
    complete: bool = True
    blocking: list[ChecklistBlockerOut] = []
    flags: list[ChecklistFlagOut] = []
    #: Verbatim the sentence the submit 422 carries, so the client never authors
    #: gate wording and the two can't drift (ui-standards §3.14).
    gate_message: str | None = None


class ChecklistFileOut(BaseModel):
    id: int  # reimb_attachments.id — what DELETE addresses
    attachment_id: int  # core_attachments.id — display only
    filename: str
    byte_size: int
    scan_status: str
    uploaded_at: datetime
    #: Null until the scan is clean — an unservable file must not offer a link.
    download_path: str | None = None


class ChecklistItemOut(BaseModel):
    catalog_id: int
    item_id: int | None = None  # null until the row is materialized on first write
    code: str
    label: str
    group: str
    evidence: str
    required: bool
    #: Why this applies, in plain language. Null for unconditional items.
    required_because: str | None = None
    status: str
    #: Populated when an auto-check flagged; rendered verbatim.
    flag_reason: str | None = None
    waiver_reason: str | None = None
    sort: int = 0
    files: list[ChecklistFileOut] = []


class ChecklistOut(BaseModel):
    """The Documents step's whole payload — and every mutation's response, so
    the rows and the progress line always refresh together."""

    items: list[ChecklistItemOut]
    summary: ChecklistSummaryOut


class ClaimDetail(BaseModel):
    id: int
    ref_no: str | None = None
    kind: str
    status: str  # legacy NULL rows coalesce to "draft" in the mapper
    status_label: str
    next_action: str | None = None
    holder_kind: str | None = None
    holder_display: str | None = None
    holder_since: datetime | None = None
    claimant: ClaimantOut
    is_jo_cos: bool
    activity_id: int | None = None
    dpo_no: str | None = None
    dpo_date: date | None = None
    purpose: str | None = None
    destination: str | None = None
    destination_region_code: str | None = None
    date_depart: date | None = None
    date_return: date | None = None
    is_within_50km: bool
    overnight_stay: bool
    fund_source: str | None = None
    other_total: str
    totals: dict[str, Any] | None = None  # compute snapshot verbatim; {} → None
    legs: list[LegOut]
    # --- R-4-screens: the approver read-model, embedded rather than a second
    # endpoint. Every mutation returns ClaimDetail, so the action set and the
    # CAS token refresh in lockstep with the claim they describe.
    available_actions: list[str] = []
    row_version: int | None = None
    sla_due_at: datetime | None = None
    sla_state: str | None = None
    # --- R-3: the submit gate + the approver's amber flags, on the record they
    # describe. The item LIST is a sibling endpoint (too big to ride every claim
    # read); the SUMMARY rides here because the button and the reason it is
    # absent must refresh in one response.
    checklist: ChecklistSummaryOut = ChecklistSummaryOut()
    created_at: datetime
    updated_at: datetime


class WorkItemOut(BaseModel):
    id: int
    ref_no: str | None = None
    purpose: str | None = None
    destination: str | None = None
    status: str
    status_label: str
    next_action: str | None = None
    holder_kind: str | None = None
    holder_display: str | None = None
    holder_since: datetime | None = None
    days_in_state: int
    grand: str | None = None
    sla_due_at: datetime | None = None
    sla_state: str | None = None  # spec §6.3 derived badge — never a status
    updated_at: datetime


class MyWorkOut(BaseModel):
    waiting_on_you: list[WorkItemOut]
    in_flight: list[WorkItemOut]


class RegionOut(BaseModel):
    region_code: str
    region_name: str | None = None
    cluster: str


class ReturnReasonOut(BaseModel):
    """One row of the seeded return-reason taxonomy — the dialog's chips."""

    id: int
    code: str
    label: str
    category: str


class TimelineEventOut(BaseModel):
    """One tracker row (spec §9.2 claim tracker), from
    ``reimb_status_histories``. ``reasons`` is populated on the rows a return
    produced — spec §12 says the claimant sees the reasons verbatim."""

    id: int
    from_status: str | None = None
    from_status_label: str | None = None
    to_status: str
    to_status_label: str
    actor_display: str | None = None
    note: str | None = None
    reasons: list[ReturnReasonOut] = []
    created_at: datetime
