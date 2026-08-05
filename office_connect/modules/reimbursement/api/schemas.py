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


# --- R-6-clock: cash advances ------------------------------------------------


class CashAdvanceIn(BaseModel):
    """Record a travel cash advance (Accounting's data, Accounting's act).

    ``deadline_date``/``deadline_basis``/``status`` are deliberately ABSENT from
    the wire: the clock is computed and pinned by ``services/cash_advance.py``
    from ``date_return``, and a client that could post a deadline could post one
    COA never gave. Same doctrine as money — the server computes, the UI
    displays (api-standards §2).
    """

    claimant_id: int
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    dv_no: str | None = Field(default=None, max_length=100)
    dv_date: date | None = None
    dpo_no: str | None = Field(default=None, max_length=100)
    date_return: date | None = None


class CashAdvancePatch(BaseModel):
    """Edit the recorded facts. ``exclude_unset`` at the router keeps "cleared
    to null" and "not mentioned" distinct — the ``drafts.py`` convention.
    ``claimant_id`` is absent: re-pointing an advance at a different person
    would move the §89 slot silently. Void and re-record instead."""

    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    dv_no: str | None = Field(default=None, max_length=100)
    dv_date: date | None = None
    dpo_no: str | None = Field(default=None, max_length=100)
    date_return: date | None = None


class CashAdvanceOut(BaseModel):
    """One advance plus its SERVER-DERIVED countdown.

    ``days_remaining``/``deadline_state`` ride the record rather than being
    computed client-side for the same reason ``sla_state`` does (delta row 60):
    a browser with a wrong clock, or one running outside Manila, must not be
    able to tell a traveller they still have time to liquidate.
    """

    id: int
    claimant_id: int
    claimant_name: str | None = None
    dv_no: str | None = None
    dv_date: date | None = None
    dpo_no: str | None = None
    amount: str
    date_return: date | None = None
    status: str
    status_label: str
    settled_at: datetime | None = None
    #: The settlement record (R-6-liq-settle). All four are null until the
    #: advance is settled; `refund_or_*`/`refund_amount` stay null on the
    #: `exact` and `over_advance` modes, where no money came back.
    settlement_mode: str | None = None
    refund_or_no: str | None = None
    refund_or_date: date | None = None
    refund_amount: str | None = None
    # The clock. All three are null together when there is no return date yet —
    # a trip that has not happened has no deadline, and a zero would be a lie.
    # All three also go null once SETTLED: a closed advance is not counting down
    # to anything, and leaving a red "Overdue" ring on a settled-but-late record
    # would keep threatening a traveller who already answered.
    deadline_date: date | None = None
    deadline_basis: str | None = None
    days_remaining: int | None = None
    deadline_state: str | None = None
    #: The COA consequence copy, from config with its legal source — present
    #: only once it applies (due-soon or past), so it reads as a warning rather
    #: than boilerplate every advance carries from birth.
    overdue_note: str | None = None
    #: The liquidation started against this advance, if any (R-6-liq-chain).
    #: Rides the advance rather than a sibling lookup so the card can offer
    #: "Liquidate" or "Open LQ-2026-0001" from ONE response — two requests could
    #: disagree, and the disagreement would show as a button that 409s (the same
    #: reasoning that embeds `available_actions` in ClaimDetail, delta row 59).
    liquidation_claim_id: int | None = None
    liquidation_ref_no: str | None = None
    liquidation_status: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CashAdvanceListOut(BaseModel):
    items: list[CashAdvanceOut]


# --- R-6-liq-settle: recording the settlement --------------------------------


class SettleIn(BaseModel):
    """Close a liquidation and record how its money came out (spec §6.2).

    Note what is deliberately ABSENT: the settlement MODE, and the figures. Both
    are read from the claim's server-computed ``totals`` — a client that could
    post "this was a refund of ₱1,266" could post a refund that never happened.
    ``refund_amount`` is accepted only as an ECHO: supply it and the server
    refuses on mismatch, which catches a stale screen recording a receipt
    against the wrong number. Omit it and the server figure stands either way.
    """

    or_no: str | None = Field(default=None, max_length=100)
    or_date: date | None = None
    refund_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=12, decimal_places=2
    )
    comment: str | None = None
    expected_version: int | None = None


class SpawnedClaimOut(BaseModel):
    """A pointer between the two halves of an over-advance (R-6-liq-settle)."""

    claim_id: int
    ref_no: str | None = None
    status: str
    status_label: str


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
    #: 'uploaded' (a human sent it) | 'generated' (the system rendered it). The
    #: Documents step branches on this to render a Generated card rather than a
    #: file row, and only a generated PDF previews inline.
    origin: str = "uploaded"
    #: Null until the scan is clean — an unservable file must not offer a link.
    #: Generated PDFs are born clean, so theirs is populated immediately.
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


class PacketOut(BaseModel):
    """The live combined packet — spec §9.2's "packet PDF preview" (R-5-packet).

    A claim-level artifact, not a checklist row: it satisfies no COA code, so it
    rides ``ClaimDetail`` rather than the item list. ``null`` on ``ClaimDetail``
    means no packet has been generated yet — a real state (a fresh draft, or a
    submit that happened while the worker was down), which the UI must render as
    an honest notice rather than an empty frame.
    """

    attachment_id: int
    #: Always populated: a generated PDF is born scan-clean, so unlike an upload
    #: there is no window where the row exists but the bytes are unservable.
    download_path: str
    generated_at: datetime
    #: True while the claim was still editable — the PDF carries the DRAFT
    #: watermark and no reference number, and the UI must say so.
    is_draft: bool
    content_sha256: str
    source_fingerprint: str


class GenerateDocumentsOut(BaseModel):
    """The 202 body of ``POST /claims/{id}/documents/generate``.

    Carries the packet as it stands (so the client can refresh its cache without
    a second round trip) plus whether a worker actually took the job. ``queued:
    false`` is not an error — it is the honest signal that generation is
    unavailable right now, which the UI shows as a non-blocking notice rather
    than a spinner that never resolves.
    """

    checklist: ChecklistOut
    queued: bool


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
    # --- R-5-packet: the §9.2 preview. Embedded for the same reason the action
    # set is (delta row 59) — the approver's decision and the document they are
    # deciding on must never arrive in two responses that can disagree.
    packet: PacketOut | None = None
    # --- R-6-clock: the linked cash advance and its countdown. Embedded on the
    # same reasoning again — a claim rail showing "12 days left" that came from
    # a second request could disagree with the claim it sits beside. `None` is
    # the ordinary case: most claims are not against an advance.
    cash_advance: CashAdvanceOut | None = None
    # --- R-6-liq-settle: the two halves of an over-advance, pointing at each
    # other. `spawned_claim` rides a settled liquidation so the traveller sees
    # either "₱X is due you" or the claim they already filed for it, from ONE
    # response; `spawned_from` rides the reimbursement so an approver reading
    # its DV can find the Liquidation Report the figure came from.
    spawned_claim: SpawnedClaimOut | None = None
    spawned_from: SpawnedClaimOut | None = None
    # --- R-7-events: what FMS last said, and what FMS finally did. The latest
    # sub-status rides the claim for the same one-response reason as everything
    # above it — "With Accounting" arriving separately from the status chip that
    # says "Handed to FMS" is two half-answers to one question. The payout fields
    # are null until the claim closes, and read-only forever after.
    latest_external: ExternalEventOut | None = None
    payout_ref: str | None = None
    paid_on: date | None = None
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


class QueueItemOut(WorkItemOut):
    """An oversight-queue row: a My-Work row plus the two things you only need
    when the claim is somebody ELSE's (R-7-queue).

    ``claimant_display`` because this list mixes travellers — My Work never has
    to say whose claim it is. ``days_with_fms`` because spec §7 rule 5's
    follow-up is counted in Manila WORKING days and no browser may compute that
    (api-standards §9e); it is null unless FMS actually holds the claim, since
    0 would be a false answer to a question that does not apply.
    """

    claimant_display: str | None = None
    days_with_fms: int | None = None
    external_followup: bool = False
    #: The latest FMS sub-status, as a label (R-7-events). "12 working days with
    #: FMS" and "…and the last we heard it was With Accounting" are different
    #: facts, and the second is what decides whether a follow-up call is worth
    #: making. Null when FMS has said nothing yet.
    external_status_label: str | None = None


class ClaimQueueOut(BaseModel):
    """``total`` is the count BEFORE ``limit``/``offset`` — a queue that says
    "50 items" while hiding 200 is worse than no number at all."""

    items: list[QueueItemOut]
    total: int
    followup_working_days: int


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
    """One tracker row (spec §9.2 claim tracker) — from ``reimb_status_histories``
    OR, since R-7-events, from ``reimb_external_events``.

    ``reasons`` is populated on the rows a return produced — spec §12 says the
    claimant sees the reasons verbatim.

    ``kind`` discriminates the two lanes, and ``to_status`` is **null on an
    external row**. That is not a shortcut: an FMS sub-status is deliberately NOT
    a workflow state (delta row 38 — they ride the event table over the single
    ``handed_to_fms`` state), so letting ``with_accounting`` travel in the field
    every consumer reads as a claim status is how that distinction would quietly
    stop being true. The display string rides ``to_status_label``, which is what
    the tracker renders anyway.
    """

    kind: str = "status"
    id: int
    from_status: str | None = None
    from_status_label: str | None = None
    to_status: str | None = None
    to_status_label: str
    actor_display: str | None = None
    note: str | None = None
    reasons: list[ReturnReasonOut] = []
    #: What FMS says the date was, when it differs from when it was relayed.
    event_date: date | None = None
    created_at: datetime


class ExternalEventOut(BaseModel):
    """The latest FMS word on a claim, for the rail and the queue row."""

    id: int
    status: str
    status_label: str
    noted_by: str | None = None
    note: str | None = None
    event_date: date | None = None
    created_at: datetime


class ExternalEventIn(BaseModel):
    """Relay one FMS journey update (spec §6.1 row 6).

    ``status`` is validated against the closed set in the service, not here: the
    refusal has to explain that ORDER is not enforced ("in any order, and
    skipping any of them is fine"), and a pydantic ``Literal`` would produce a
    generic enum error that says the opposite by omission.

    ``noted_by`` is free text because the person at FMS has no login here — it is
    a name an Admin Officer writes down, not an actor this system can resolve.
    """

    status: str
    noted_by: str | None = Field(default=None, max_length=200)
    note: str | None = None
    event_date: date | None = None


class MarkPaidIn(BaseModel):
    """Close a claim, recording what FMS paid (spec §6.1 row 8).

    Note what is deliberately ABSENT: the amount. What was owed is the claim's
    own server-computed ``totals``, and a client that could post "paid ₱6,750"
    could close a claim on a figure the claim never said. The reference and the
    date are facts only FMS can supply, which is exactly why they are inputs.
    """

    payout_ref: str | None = Field(default=None, max_length=100)
    paid_on: date | None = None
    comment: str | None = None
    expected_version: int | None = None
