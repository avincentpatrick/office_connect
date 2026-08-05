/** ClaimDetail / My-Work fixtures for the reimbursement page tests. */

import type {
  CashAdvance,
  ChecklistFile,
  ChecklistItem,
  ChecklistResponse,
  ChecklistSummary,
  ClaimDetail,
  ClaimQueueResponse,
  ClaimTotals,
  MyWorkResponse,
  PacketSummary,
  QueueItem,
  TimelineEvent,
  WorkItem,
} from "../api/reimbursement";

export function makeClaim(overrides: Partial<ClaimDetail> = {}): ClaimDetail {
  return {
    id: 7,
    ref_no: null,
    kind: "reimbursement",
    status: "draft",
    status_label: "Draft",
    next_action: "Complete your packet",
    holder_kind: "user",
    holder_display: "You",
    holder_since: "2026-07-30T00:00:00Z",
    claimant: {
      staff_id: 3,
      employee_no: "E-0001",
      full_name: "Test Claimant",
      position_title: "Nurse II",
      employment_status: "permanent",
      division: { id: 1, name: "Finance Division" },
      section: null,
    },
    is_jo_cos: false,
    activity_id: null,
    dpo_no: null,
    dpo_date: null,
    purpose: null,
    destination: null,
    destination_region_code: null,
    date_depart: null,
    date_return: null,
    is_within_50km: false,
    overnight_stay: false,
    fund_source: null,
    other_total: "0.00",
    totals: null,
    legs: [],
    // A draft, seen by its owner: the pre-instance action set (R-4-screens).
    available_actions: ["submit", "cancel"],
    row_version: null,
    sla_due_at: null,
    sla_state: null,
    // A fresh draft has no checklist yet — the required SET is unknowable
    // before Money computes (the rules read totals.other and the legs).
    checklist: makeChecklistSummary(),
    // No packet on a fresh draft — nothing has been generated yet. Tests that
    // want one pass `packet: makePacket()`.
    packet: null,
    created_at: "2026-07-30T00:00:00Z",
    updated_at: "2026-07-30T00:00:00Z",
    ...overrides,
  };
}

export function makePacket(overrides: Partial<PacketSummary> = {}): PacketSummary {
  return {
    attachment_id: 42,
    download_path: "/api/v1/attachments/42/content",
    generated_at: "2026-08-04T02:00:00Z",
    is_draft: false,
    content_sha256: "a".repeat(64),
    source_fingerprint: "b".repeat(64),
    ...overrides,
  };
}

export function makeTotals(overrides: Partial<ClaimTotals> = {}): ClaimTotals {
  return {
    version: 1,
    per_diem: "5500.00",
    transport: "1000.00",
    other: "250.00",
    grand: "6750.00",
    advance: "0.00",
    to_reimburse: "6750.00",
    to_refund: "0.00",
    computed_at: "2026-07-30T00:00:00Z",
    days: [
      {
        date: "2026-07-01",
        day_type: "arrival",
        leg_id: 11,
        region_code: "13",
        cluster: "III",
        daily_rate: "2200.00",
        pct: 100,
        components: {},
        deductions: {},
        amount: "2200.00",
        gated_50km: false,
      },
      {
        date: "2026-07-02",
        day_type: "full",
        leg_id: null,
        region_code: "13",
        cluster: "III",
        daily_rate: "2200.00",
        pct: 100,
        components: {},
        deductions: {},
        amount: "2200.00",
        gated_50km: false,
      },
      {
        date: "2026-07-03",
        day_type: "return",
        leg_id: 12,
        region_code: "13",
        cluster: "III",
        daily_rate: "2200.00",
        pct: 50,
        components: {},
        deductions: {},
        amount: "1100.00",
        gated_50km: false,
      },
    ],
    ...overrides,
  };
}

/** A claim with every wizard step complete — Review renders fully. */
export function completeClaim(overrides: Partial<ClaimDetail> = {}): ClaimDetail {
  return makeClaim({
    dpo_no: "DPO-2026-077",
    dpo_date: "2026-06-20",
    purpose: "Regional immunization review",
    destination: "Manila",
    destination_region_code: "13",
    date_depart: "2026-07-01",
    date_return: "2026-07-03",
    fund_source: "GF_ORS",
    other_total: "250.00",
    totals: makeTotals(),
    // Money is computed here, so the packet exists — and is satisfied, so
    // every pre-R-3 Review test still sees an enabled Submit.
    checklist: makeChecklistSummary({
      required_total: 2,
      required_done: 2,
    }),
    legs: [
      {
        id: 11,
        seq: 1,
        leg_date: "2026-07-01",
        place: "To Manila",
        destination_region_code: "13",
        time_depart: "08:00",
        time_arrive: "12:00",
        transport_mode: "bus",
        fare: "500.00",
        per_diem_pct: 100,
        per_diem_amount: "2200.00",
        leg_total: "2700.00",
        lodging_provided: false,
        meals_provided: false,
      },
      {
        id: 12,
        seq: 2,
        leg_date: "2026-07-03",
        place: "Return",
        destination_region_code: null,
        time_depart: "15:00",
        time_arrive: "19:00",
        transport_mode: "bus",
        fare: "500.00",
        per_diem_pct: 50,
        per_diem_amount: "1100.00",
        leg_total: "1600.00",
        lodging_provided: false,
        meals_provided: false,
      },
    ],
    ...overrides,
  });
}

export function makeWorkItem(overrides: Partial<WorkItem> = {}): WorkItem {
  return {
    id: 7,
    ref_no: "RB-2026-0001",
    purpose: "Regional immunization review",
    destination: "Manila",
    status: "division_approval",
    status_label: "For Approval",
    next_action: "Approve or return",
    holder_kind: "user",
    holder_display: "Maria Santos",
    holder_since: "2026-07-28T00:00:00Z",
    days_in_state: 2,
    grand: "6750.00",
    sla_due_at: "2026-08-05T09:00:00Z",
    sla_state: "on_track",
    updated_at: "2026-07-30T00:00:00Z",
    ...overrides,
  };
}

/**
 * An oversight-queue row (R-7-queue). Defaults to a claim sitting with FMS but
 * still inside the follow-up window — the uneventful case, so a test that cares
 * about the stalled one has to say so.
 */
export function makeQueueItem(overrides: Partial<QueueItem> = {}): QueueItem {
  return {
    ...makeWorkItem({
      status: "handed_to_fms",
      status_label: "Handed to FMS",
      next_action: "Waiting on FMS — update status",
      holder_kind: "external_fms",
      holder_display: "FMS",
      sla_due_at: null,
      sla_state: null,
    }),
    claimant_display: "Maria Santos",
    days_with_fms: 4,
    external_followup: false,
    // Null by default: a packet handed over four days ago may genuinely have
    // produced no news, and a fixture that always carries a sub-status would
    // hide the "FMS has said nothing yet" row from every test (R-7-events).
    external_status_label: null,
    ...overrides,
  };
}

export function makeClaimQueue(
  overrides: Partial<ClaimQueueResponse> = {},
): ClaimQueueResponse {
  return {
    items: [makeQueueItem()],
    total: 1,
    followup_working_days: 10,
    ...overrides,
  };
}

export function makeMyWork(overrides: Partial<MyWorkResponse> = {}): MyWorkResponse {
  return {
    waiting_on_you: [
      makeWorkItem({ id: 5, ref_no: null, status: "draft", status_label: "Draft",
        next_action: "Complete your packet", holder_display: "You", days_in_state: 0 }),
    ],
    in_flight: [makeWorkItem()],
    ...overrides,
  };
}

/**
 * A claim sitting at the first gate, as its APPROVER sees it — the approval
 * bar renders from `available_actions`, so this fixture is what makes the
 * approver an approver in a page test (no auth context involved).
 */
export function awaitingApproval(
  overrides: Partial<ClaimDetail> = {},
): ClaimDetail {
  return completeClaim({
    ref_no: "RB-2026-0001",
    status: "division_approval",
    status_label: "For Approval",
    next_action: "Approve or return",
    holder_display: "Maria Santos",
    available_actions: ["approve", "return"],
    row_version: 2,
    sla_due_at: "2026-08-05T09:00:00Z",
    sla_state: "on_track",
    ...overrides,
  });
}

/**
 * A liquidation one rung short of the money (R-6-liq-settle): FMS has it, and
 * the server has REWRITTEN `approve` into `settle` — clearing that gate now has
 * to record how the advance came out.
 *
 * ₱8,000 advanced against the ₱6,750 fixture trip is the REFUND branch, the one
 * with a receipt to get right.
 */
export function awaitingSettlement(
  overrides: Partial<ClaimDetail> = {},
): ClaimDetail {
  return completeClaim({
    ref_no: "LQ-2026-0001",
    kind: "liquidation",
    status: "handed_to_fms",
    status_label: "With FMS",
    next_action: "Record the settlement",
    available_actions: ["settle", "return"],
    row_version: 4,
    totals: makeTotals({
      advance: "8000.00",
      to_reimburse: "0.00",
      to_refund: "1250.00",
    }),
    cash_advance: makeCashAdvance({
      amount: "8000.00",
      status: "liquidation_started",
      status_label: "Liquidation started",
    }),
    ...overrides,
  });
}

/**
 * A reimbursement with FMS (R-7-events): the server has rewritten `approve`
 * into `mark_paid` — clearing that gate now has to record the payment reference
 * spec §6.1 row 8 asks for — and added `relay_fms`, which moves nothing.
 *
 * `latest_external` is null by default: a packet handed over this morning has
 * genuinely produced no news yet, and that is the state most of the FMS leg is
 * actually in.
 */
export function awaitingPayment(
  overrides: Partial<ClaimDetail> = {},
): ClaimDetail {
  return completeClaim({
    ref_no: "RB-2026-0001",
    status: "handed_to_fms",
    status_label: "Handed to FMS",
    next_action: "Waiting on FMS — update status",
    holder_kind: "external_fms",
    holder_display: "FMS",
    available_actions: ["mark_paid", "return", "relay_fms"],
    row_version: 5,
    latest_external: null,
    ...overrides,
  });
}

/** The same claim once FMS paid it — terminal, and read-only for everyone. */
export function paidClaim(overrides: Partial<ClaimDetail> = {}): ClaimDetail {
  return completeClaim({
    ref_no: "RB-2026-0001",
    status: "paid_closed",
    status_label: "Paid / Closed",
    next_action: null,
    holder_kind: null,
    holder_display: null,
    available_actions: [],
    payout_ref: "ADA-2026-00417",
    paid_on: "2026-07-03",
    ...overrides,
  });
}

/** One FMS journey update, for the rail and the tracker. */
export function makeExternalEvent(
  overrides: Partial<NonNullable<ClaimDetail["latest_external"]>> = {},
): NonNullable<ClaimDetail["latest_external"]> {
  return {
    id: 1,
    status: "with_accounting",
    status_label: "With Accounting",
    noted_by: "Ms. Reyes, Accounting",
    note: null,
    event_date: null,
    created_at: "2026-07-30T02:00:00Z",
    ...overrides,
  };
}

/** The same liquidation after Accounting closed it as an over-advance. */
export function settledOverAdvance(
  overrides: Partial<ClaimDetail> = {},
): ClaimDetail {
  return completeClaim({
    ref_no: "LQ-2026-0001",
    kind: "liquidation",
    status: "settled",
    status_label: "Settled",
    next_action: null,
    // The traveller's one tap, offered by the SERVER — never inferred here.
    available_actions: ["spawn"],
    totals: makeTotals({
      advance: "6000.00",
      to_reimburse: "750.00",
      to_refund: "0.00",
    }),
    cash_advance: makeSettledAdvance({
      amount: "6000.00",
      settlement_mode: "over_advance",
      refund_or_no: null,
      refund_or_date: null,
      refund_amount: null,
    }),
    ...overrides,
  });
}

/**
 * One FMS journey row for the merged tracker (R-7-events). `to_status` is null
 * because a sub-status is not a workflow state — the display string rides
 * `to_status_label`, which is what the tracker renders.
 */
export function makeExternalTimelineEvent(
  overrides: Partial<TimelineEvent> = {},
): TimelineEvent {
  return {
    kind: "external",
    id: 1,
    from_status: null,
    from_status_label: null,
    to_status: null,
    to_status_label: "With Accounting",
    actor_display: "Ms. Reyes, Accounting",
    note: null,
    event_date: null,
    reasons: [],
    created_at: "2026-07-30T02:00:00Z",
    ...overrides,
  };
}

export function makeTimeline(
  overrides: Partial<TimelineEvent>[] = [],
): TimelineEvent[] {
  const base: TimelineEvent[] = [
    {
      kind: "status",
      id: 1,
      from_status: null,
      from_status_label: null,
      to_status: "draft",
      to_status_label: "Draft",
      actor_display: "Test Claimant",
      note: null,
      reasons: [],
      created_at: "2026-07-28T01:00:00Z",
    },
    {
      kind: "status",
      id: 2,
      from_status: "draft",
      from_status_label: "Draft",
      to_status: "division_approval",
      to_status_label: "For Approval",
      actor_display: "Test Claimant",
      note: null,
      reasons: [],
      created_at: "2026-07-28T02:00:00Z",
    },
  ];
  return overrides.length === 0
    ? base
    : base.map((event, index) => ({ ...event, ...overrides[index] }));
}

export const RETURN_REASONS = [
  { id: 1, code: "MISSING_OR", label: "Missing official receipt", category: "missing_doc" },
  { id: 2, code: "PER_DIEM_CALC", label: "Per-diem miscomputed", category: "wrong_amount" },
];

// --- R-3: the documentary packet -------------------------------------------

export function makeChecklistSummary(
  overrides: Partial<ChecklistSummary> = {},
): ChecklistSummary {
  const summary: ChecklistSummary = {
    required_total: 0,
    required_done: 0,
    complete: true,
    blocking: [],
    flags: [],
    gate_message: null,
    ...overrides,
  };
  // Keep the fixture self-consistent with the server's own invariant:
  // blocking is empty IFF required_done === required_total.
  if (overrides.blocking === undefined) {
    const missing = summary.required_total - summary.required_done;
    summary.blocking = Array.from({ length: Math.max(missing, 0) }, (_, i) => ({
      catalog_id: i + 1,
      item_id: null,
      code: i === 0 ? "TO-01" : "CTC-47",
      label:
        i === 0
          ? "Approved Travel Order / Authority to Travel"
          : "Certificate of Travel Completed (GAM App 47)",
      group: "authority" as const,
      evidence: "upload" as const,
      reason: "missing",
    }));
  }
  summary.complete = summary.blocking.length === 0;
  if (!summary.complete && overrides.gate_message === undefined) {
    summary.gate_message =
      "2 required documents still missing: TO-01 (Approved Travel Order / " +
      "Authority to Travel), CTC-47 (Certificate of Travel Completed (GAM App " +
      "47)). Attach them on the Documents step, then submit again.";
  }
  return summary;
}

export function makeChecklistItem(
  overrides: Partial<ChecklistItem> = {},
): ChecklistItem {
  return {
    catalog_id: 1,
    item_id: null,
    code: "TO-01",
    label: "Approved Travel Order / Authority to Travel",
    group: "authority",
    evidence: "upload",
    required: true,
    required_because: null,
    status: "missing",
    flag_reason: null,
    waiver_reason: null,
    sort: 1,
    files: [],
    ...overrides,
  };
}

/** A file row. Defaults to an upload mid-scan — the common, awkward case. */
export function makeChecklistFile(
  overrides: Partial<ChecklistFile> = {},
): ChecklistFile {
  return {
    id: 9,
    attachment_id: 90,
    filename: "travel-order.jpg",
    byte_size: 120,
    scan_status: "pending",
    uploaded_at: "2026-08-03T01:00:00Z",
    origin: "uploaded",
    download_path: null,
    ...overrides,
  };
}

/** A system-rendered PDF: born scan-clean, so its link exists immediately. */
export function makeGeneratedFile(
  overrides: Partial<ChecklistFile> = {},
): ChecklistFile {
  return makeChecklistFile({
    id: 21,
    attachment_id: 210,
    filename: "RB-2026-0007_20260803_090000_IOT-45.pdf",
    scan_status: "clean",
    origin: "generated",
    download_path: "/api/v1/attachments/210/content",
    ...overrides,
  });
}

/** One item per evidence kind, plus the summary that matches them. */
export function makeChecklist(
  overrides: Partial<ChecklistResponse> = {},
): ChecklistResponse {
  return {
    items: [
      makeChecklistItem(),
      makeChecklistItem({
        catalog_id: 3,
        code: "IOT-45",
        label: "Itinerary of Travel (GAM App 45)",
        group: "itinerary",
        evidence: "generated_doc",
        sort: 3,
      }),
      makeChecklistItem({
        catalog_id: 4,
        code: "CTC-47",
        label: "Certificate of Travel Completed (GAM App 47)",
        group: "proof_of_travel",
        evidence: "external_wet_sign",
        sort: 4,
      }),
    ],
    summary: makeChecklistSummary({ required_total: 2, required_done: 0 }),
    ...overrides,
  };
}

/** A claim whose Documents step is outstanding — the submit gate's fixture. */
export function documentsPending(
  overrides: Partial<ClaimDetail> = {},
): ClaimDetail {
  return completeClaim({
    checklist: makeChecklistSummary({ required_total: 2, required_done: 0 }),
    ...overrides,
  });
}


/**
 * A live cash advance with its COA countdown (R-6-clock). Defaults to the
 * seeded calendar basis, 12 days out — comfortably on track, so a test that
 * cares about urgency has to say so.
 */
export function makeCashAdvance(
  overrides: Partial<CashAdvance> = {},
): CashAdvance {
  return {
    id: 41,
    claimant_id: 3,
    claimant_name: "Maria Santos",
    dv_no: "DV-2026-0042",
    dv_date: "2026-06-25",
    dpo_no: "DPO-2026-0100",
    amount: "5000.00",
    date_return: "2026-07-03",
    status: "open",
    status_label: "Open",
    settled_at: null,
    // Unsettled: the settlement record is empty until Accounting closes it
    // (R-6-liq-settle). `makeSettledAdvance` below is the other side.
    settlement_mode: null,
    refund_or_no: null,
    refund_or_date: null,
    refund_amount: null,
    deadline_date: "2026-08-02",
    deadline_basis: "calendar",
    days_remaining: 12,
    deadline_state: "on_track",
    overdue_note: null,
    // No liquidation started yet — the card's default offer is "Liquidate".
    liquidation_claim_id: null,
    liquidation_ref_no: null,
    liquidation_status: null,
    created_at: "2026-06-25T02:00:00+00:00",
    updated_at: "2026-06-25T02:00:00+00:00",
    ...overrides,
  };
}

/**
 * A settled advance (R-6-liq-settle). Note the clock fields: the SERVER nulls
 * them once an advance closes, so a fixture that kept them would let a test
 * pass against a card the real API can never produce.
 */
export function makeSettledAdvance(
  overrides: Partial<CashAdvance> = {},
): CashAdvance {
  return makeCashAdvance({
    status: "settled",
    status_label: "Settled",
    settled_at: "2026-07-09T02:00:00+00:00",
    settlement_mode: "refund",
    refund_or_no: "OR-2026-1234",
    refund_or_date: "2026-07-09",
    refund_amount: "1500.00",
    deadline_state: null,
    days_remaining: null,
    overdue_note: null,
    ...overrides,
  });
}
