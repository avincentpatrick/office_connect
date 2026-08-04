/** ClaimDetail / My-Work fixtures for the reimbursement page tests. */

import type {
  ChecklistFile,
  ChecklistItem,
  ChecklistResponse,
  ChecklistSummary,
  ClaimDetail,
  ClaimTotals,
  MyWorkResponse,
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
    created_at: "2026-07-30T00:00:00Z",
    updated_at: "2026-07-30T00:00:00Z",
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

export function makeTimeline(
  overrides: Partial<TimelineEvent>[] = [],
): TimelineEvent[] {
  const base: TimelineEvent[] = [
    {
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
