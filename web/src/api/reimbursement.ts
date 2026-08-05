/**
 * Wire types + client for /api/v1/reimbursement (R-2-wizard). Field names are
 * the backend wire names (office_connect/modules/reimbursement/api/schemas.py).
 * Money crosses as 2-dp strings, server-computed — the client displays, never
 * computes (tech-stack §4 hard prohibition). Also exports `reimbKeys`, the
 * module's react-query key factory (the codebase's first; core keys `["me"]` /
 * `["config"]` stay as literals).
 */

import { api } from "./http";

/**
 * Every state either chain can occupy — the union of both server vocabularies
 * (`services/status.py`). A claim is one `ClaimKind`, so no single claim ever
 * reaches all of these; keeping them in ONE union is what makes the
 * `Record<ClaimStatus, ...>` maps below exhaustive, so adding a state to a
 * chain fails `tsc` here rather than rendering a raw code at a user.
 */
export type ClaimStatus =
  // shared by both chains
  | "draft"
  | "returned"
  | "handed_to_fms"
  | "cancelled"
  // reimbursement (spec §6.1)
  | "division_approval"
  | "admin_review"
  | "fms_returned"
  | "paid_closed"
  // liquidation (spec §6.2) — certification A is the SUBMIT, not a state
  | "certify_b"
  | "certify_c"
  | "settled";

/** Which chain a claim runs. Drives labels, copy and the tracker's heading. */
export type ClaimKind = "reimbursement" | "liquidation";

export type TransportMode =
  | "plane"
  | "bus"
  | "boat"
  | "taxi"
  | "ride_hail"
  | "gov_vehicle"
  | "other";

export type FundSource = "GF_ORS" | "TF_BUR";

export interface OrgUnitRef {
  id: number;
  name: string;
}

/** Directory prefill block — display only, never re-asked (WCAG 2.2 §3.3.7). */
export interface ClaimantBlock {
  staff_id: number;
  employee_no: string | null;
  full_name: string | null;
  position_title: string | null;
  employment_status: string | null;
  division: OrgUnitRef | null;
  section: OrgUnitRef | null;
}

export interface ClaimLeg {
  id: number;
  seq: number;
  leg_date: string | null;
  place: string | null;
  destination_region_code: string | null;
  time_depart: string | null;
  time_arrive: string | null;
  transport_mode: TransportMode | null;
  fare: string | null;
  /** Server-written by /compute — display only. */
  per_diem_pct: number | null;
  per_diem_amount: string | null;
  leg_total: string | null;
  lodging_provided: boolean;
  meals_provided: boolean;
}

export interface TotalsDay {
  date: string;
  day_type: string;
  leg_id: number | null;
  region_code: string | null;
  cluster: string | null;
  daily_rate: string;
  pct: number;
  components: Record<string, string>;
  deductions: Record<string, string>;
  amount: string;
  gated_50km: boolean;
}

/** The compute snapshot verbatim (totals JSONB v1) — 2-dp money strings. */
export interface ClaimTotals {
  version: number;
  per_diem: string;
  transport: string;
  other: string;
  grand: string;
  advance: string;
  to_reimburse: string;
  to_refund: string;
  computed_at: string;
  days: TotalsDay[];
}

// --- R-3: the documentary packet -------------------------------------------

export type ChecklistGroup =
  | "authority"
  | "itinerary"
  | "proof_of_travel"
  | "transport"
  | "lodging_meals"
  | "report"
  | "financial";

export type ChecklistEvidence =
  | "upload"
  | "generated_doc"
  | "external_wet_sign"
  | "data_only";

export type ChecklistItemStatus =
  | "missing"
  | "attached"
  | "generated"
  | "auto_passed"
  | "auto_flagged"
  | "waived";

/** core_attachments.scan_status — a fresh upload lands `pending`. */
export type ScanStatus = "pending" | "clean" | "infected" | "error";

export interface ChecklistFile {
  /** reimb_attachments.id — the join row; what DELETE addresses. */
  id: number;
  /** core_attachments.id — display only; the client never builds the URL. */
  attachment_id: number;
  filename: string;
  byte_size: number;
  scan_status: ScanStatus;
  uploaded_at: string;
  /**
   * Where the bytes came from. 'generated' files are rendered by the server
   * from claim data; they are born scan-clean and are the only ones the
   * download route serves inline, so they are the only ones safe to preview
   * in a frame.
   */
  origin: AttachmentOrigin;
  /** Null until the scan is clean — never offer a link that would 409. */
  download_path: string | null;
}

export type AttachmentOrigin = "uploaded" | "generated";

export interface ChecklistItem {
  catalog_id: number;
  /** Null until the row is materialized by the first write against it. */
  item_id: number | null;
  code: string;
  label: string;
  group: ChecklistGroup;
  evidence: ChecklistEvidence;
  /** The evaluated `required_rule` — server-side, always. */
  required: boolean;
  /** Why this applies, in plain language. Null for unconditional items. */
  required_because: string | null;
  status: ChecklistItemStatus;
  /** Populated when an auto-check flagged; rendered verbatim. */
  flag_reason: string | null;
  waiver_reason: string | null;
  sort: number;
  files: ChecklistFile[];
}

export interface ChecklistBlocker {
  catalog_id: number;
  item_id: number | null;
  code: string;
  label: string;
  group: ChecklistGroup;
  evidence: ChecklistEvidence;
  reason: string;
}

export interface ChecklistFlag {
  catalog_id: number;
  code: string;
  label: string;
  check_type: string;
  reason: string;
  message: string;
  detail: Record<string, unknown>;
  remedy: string | null;
}

/**
 * The submit gate + the approver's flags (spec §5.3/§9.4). Always present on
 * `ClaimDetail` — an engine with nothing to say answers zeroes, so there is one
 * shape to render, not two.
 */
export interface ChecklistSummary {
  required_total: number;
  required_done: number;
  complete: boolean;
  blocking: ChecklistBlocker[];
  flags: ChecklistFlag[];
  /**
   * VERBATIM the sentence the submit 422 carries. The client authors no gate
   * wording at all, so there is nothing to drift (ui-standards §3.14).
   */
  gate_message: string | null;
}

/** One shape for the GET and for every mutation — one cache write, no divergence. */
export interface ChecklistResponse {
  items: ChecklistItem[];
  summary: ChecklistSummary;
}

export interface ClaimDetail {
  id: number;
  ref_no: string | null;
  kind: ClaimKind;
  status: ClaimStatus;
  status_label: string;
  next_action: string | null;
  holder_kind: string | null;
  holder_display: string | null;
  holder_since: string | null;
  claimant: ClaimantBlock;
  is_jo_cos: boolean;
  activity_id: number | null;
  dpo_no: string | null;
  dpo_date: string | null;
  purpose: string | null;
  destination: string | null;
  destination_region_code: string | null;
  date_depart: string | null;
  date_return: string | null;
  is_within_50km: boolean;
  overnight_stay: boolean;
  fund_source: FundSource | null;
  other_total: string;
  totals: ClaimTotals | null;
  legs: ClaimLeg[];
  /**
   * What THIS user may do to THIS claim right now, computed server-side
   * (workflow-standards §3). Render buttons from this list and nothing else —
   * the client never derives permissions, and `/auth/me` deliberately carries
   * roles rather than permission strings.
   */
  available_actions: ClaimAction[];
  /** CAS token echoed back as `expected_version`; null before submit. */
  row_version: number | null;
  sla_due_at: string | null;
  sla_state: SlaState | null;
  /**
   * The submit gate + the approver's flags, embedded for the same reason
   * `available_actions` is: the button and the reason it is absent must refresh
   * in ONE response. The item LIST is a sibling query (too big to ride every
   * claim read). Optional only defensively — the server always answers.
   */
  checklist?: ChecklistSummary;
  /**
   * The live combined packet (spec §9.2's "packet PDF preview"), or null when
   * none has been generated yet — a real state, not an error: a fresh draft, or
   * a submit that happened while the render worker was down. The UI must say so
   * rather than show an empty frame.
   */
  packet?: PacketSummary | null;
  /**
   * The linked cash advance and its COA countdown (R-6-clock), or null — most
   * claims are not against an advance. Embedded for the same reason `packet`
   * and `available_actions` are: a rail reading "12 days left" that arrived in
   * a second response could disagree with the claim beside it.
   */
  cash_advance?: CashAdvance | null;
  /**
   * The two halves of an over-advance, pointing at each other (R-6-liq-settle).
   * `spawned_claim` rides a settled liquidation so the traveller sees either
   * "₱X is due you" or the claim they already filed for it; `spawned_from`
   * rides the reimbursement so an approver reading its DV can reach the
   * Liquidation Report the figure came from. Both from ONE response, for the
   * same reason `cash_advance` is embedded.
   */
  spawned_claim?: SpawnedClaim | null;
  spawned_from?: SpawnedClaim | null;
  /**
   * What FMS last said about this packet (R-7-events), or null until they have
   * said anything. Embedded for the reason everything above it is: "Handed to
   * FMS" and "…and it is now With Accounting" are one answer to one question,
   * and delivering them in two responses lets the chip and the rail disagree.
   */
  latest_external?: ExternalEvent | null;
  /** What FMS paid against, and when. Null until the claim closes; read-only after. */
  payout_ref?: string | null;
  paid_on?: string | null;
  created_at: string;
  updated_at: string;
}

/**
 * One FMS journey update (spec §6.1 row 6). `status_label` comes from the
 * SERVER's vocabulary — the browser never authors a status string, so the
 * tracker, the rail, the queue row and the claimant's notification cannot
 * disagree about what "With Accounting" is called.
 */
export interface ExternalEvent {
  id: number;
  status: ExternalStatus;
  status_label: string;
  /** Whoever at FMS said it — free text, because they have no login here. */
  noted_by: string | null;
  note: string | null;
  /** What FMS says the date was, when it differs from when it was relayed. */
  event_date: string | null;
  created_at: string;
}

/**
 * The closed set an Admin Officer may relay. **Order is not a rule** — spec
 * §6.1 row 6 says "any order/skips allowed", so this is a set of options, never
 * a sequence to walk. `paid` is absent on purpose: it closes the claim and goes
 * through `markPaid`, which carries the payment reference.
 */
export type ExternalStatus =
  | "with_budget"
  | "with_accounting"
  | "payment_processing";

/** A thin pointer between the two halves of an over-advance. */
export interface SpawnedClaim {
  claim_id: number;
  ref_no: string | null;
  status: ClaimStatus;
  status_label: string;
}

/**
 * One PDF: cover sheet, COA checklist, evidence manifest, then the three
 * generated forms in full. A claim-level artifact, which is why it rides
 * `ClaimDetail` rather than appearing as a checklist row.
 */
export interface PacketSummary {
  attachment_id: number;
  /**
   * Always present. Generated PDFs are born scan-clean, so unlike an upload
   * there is no window where the row exists but the bytes are unservable — and
   * the server serves them `inline`, which is what lets a frame render one.
   */
  download_path: string;
  generated_at: string;
  /** The PDF carries a DRAFT watermark and no reference number. Say so. */
  is_draft: boolean;
  content_sha256: string;
  source_fingerprint: string;
}

export type ClaimAction =
  | "submit"
  | "approve"
  | "return"
  | "resubmit"
  | "cancel"
  /**
   * The liquidation chain's terminal verb (R-6-liq-settle). NOT a new engine
   * action — the graph still authors `approve` at `handed_to_fms` and the
   * engine still authorizes it. The server rewrites the verb because clearing
   * that gate now also has to record the money, which is a different ROUTE
   * (`POST /claims/{id}/settle`) driving the same transition.
   */
  | "settle"
  /**
   * The reimbursement chain's terminal verb (R-7-events) — the same rewrite as
   * `settle`, one chain over. `POST /claims/{id}/mark-paid` clears
   * `handed_to_fms` while recording the payment reference spec §6.1 row 8 asks
   * for, because the engine's `approve` carries no payload.
   */
  | "mark_paid"
  /**
   * Relay what FMS says (spec §6.1 row 6). Not a transition at all — it appends
   * to the FMS journey and moves nothing — but it rides the action set for the
   * same reason `spawn` does: that set is the client's ONLY sanctioned answer
   * to "what may I do here" (workflow-standards §3), and the alternative is the
   * browser inferring a permission from a role name.
   */
  | "relay_fms"
  /**
   * Spec §6.2's "one tap": claim the difference an over-advance left owing.
   * Also not an engine action — it happens after the chain is terminal and it
   * creates a NEW claim. It rides the action set anyway, because that set is
   * the client's only sanctioned answer to "what may I do here"
   * (workflow-standards §3); the alternative is the browser inferring
   * ownership from a claimant id, which is the client computing permissions.
   */
  | "spawn";

/** Spec §6.3 derived badge — computed on view, never stored as a status. */
export type SlaState = "on_track" | "due_soon" | "overdue";

export interface ReturnReason {
  id: number;
  code: string;
  label: string;
  category: string;
}

/**
 * One row of the claim tracker (spec §9.2) — a workflow transition from
 * `reimb_status_histories`, or since R-7-events an FMS update from
 * `reimb_external_events`, merged into ONE chronology.
 *
 * `to_status` is **null on an external row**, and that is load-bearing rather
 * than lazy: an FMS sub-status is deliberately not a workflow state (they ride
 * the event table over the single `handed_to_fms` state), so letting
 * `with_accounting` into the `ClaimStatus` union is exactly how that
 * distinction would quietly stop being true. Render `to_status_label`.
 */
export interface TimelineEvent {
  kind: "status" | "external";
  id: number;
  from_status: ClaimStatus | null;
  from_status_label: string | null;
  to_status: ClaimStatus | null;
  to_status_label: string;
  actor_display: string | null;
  note: string | null;
  /** Populated on the rows a return produced — shown to the claimant verbatim. */
  reasons: ReturnReason[];
  /** What FMS says the date was, on an external row. */
  event_date?: string | null;
  created_at: string;
}

export interface WorkItem {
  id: number;
  ref_no: string | null;
  purpose: string | null;
  destination: string | null;
  status: ClaimStatus;
  status_label: string;
  next_action: string | null;
  holder_kind: string | null;
  holder_display: string | null;
  holder_since: string | null;
  days_in_state: number;
  grand: string | null;
  sla_due_at: string | null;
  sla_state: SlaState | null;
  updated_at: string;
}

/**
 * An oversight-queue row (R-7-queue): a work item plus the two things you only
 * need when the claim is somebody else's. `days_with_fms` is null unless FMS
 * actually holds it — the server counts Manila working days off the holiday
 * calendar, and the browser is never allowed to guess at that.
 */
export interface QueueItem extends WorkItem {
  claimant_display: string | null;
  days_with_fms: number | null;
  external_followup: boolean;
  /**
   * The last thing FMS said (R-7-events), or null if they have said nothing.
   * "12 working days with FMS" and "…and it was last With Accounting" are
   * different facts, and the second is what decides whether the follow-up call
   * is worth making.
   */
  external_status_label: string | null;
}

export interface ClaimQueueResponse {
  items: QueueItem[];
  /** The count BEFORE limit/offset — a queue that hides work must say so. */
  total: number;
  followup_working_days: number;
}

/** Filters the queue accepts. All optional; all narrow, none widen. */
export interface ClaimQueueFilters {
  status?: ClaimStatus;
  kind?: ClaimKind;
  claimantId?: number;
  externalOver?: boolean;
}

export interface MyWorkResponse {
  waiting_on_you: WorkItem[];
  in_flight: WorkItem[];
}

export interface Region {
  region_code: string;
  region_name: string | null;
  cluster: string;
}

/** PATCH body — send only the fields the step edits (partial by omission). */
export type ClaimPatch = Partial<{
  activity_id: number | null;
  dpo_no: string | null;
  dpo_date: string | null;
  purpose: string | null;
  destination: string | null;
  destination_region_code: string | null;
  date_depart: string | null;
  date_return: string | null;
  is_within_50km: boolean;
  overnight_stay: boolean;
  fund_source: FundSource;
  other_total: string;
}>;

/** PUT legs body row — `id` present updates that leg, absent inserts. */
export interface LegInput {
  id?: number;
  leg_date: string | null;
  place: string | null;
  destination_region_code: string | null;
  time_depart: string | null;
  time_arrive: string | null;
  transport_mode: TransportMode | null;
  fare: string | null;
  lodging_provided: boolean;
  meals_provided: boolean;
}

export const reimbKeys = {
  all: ["reimbursement"] as const,
  myWork: () => [...reimbKeys.all, "my-work"] as const,
  claim: (id: number) => [...reimbKeys.all, "claim", id] as const,
  timeline: (id: number) => [...reimbKeys.all, "claim", id, "timeline"] as const,
  // Nested under the claim(id) prefix on purpose: one invalidate after a 409
  // sweeps the claim, its timeline AND its checklist together.
  checklist: (id: number) => [...reimbKeys.all, "claim", id, "checklist"] as const,
  regions: () => [...reimbKeys.all, "regions"] as const,
  returnReasons: () => [...reimbKeys.all, "return-reasons"] as const,
  // `claimantId` is part of the key because the same endpoint serves both the
  // traveller's own list and Accounting's view of someone else's — caching them
  // under one key would show an Admin Officer the last claimant they looked at.
  cashAdvances: (claimantId?: number) =>
    [...reimbKeys.all, "cash-advances", claimantId ?? "mine"] as const,
  cashAdvance: (id: number) =>
    [...reimbKeys.all, "cash-advance", id] as const,
  // The prefix over every filter combination. React Query matches keys by
  // prefix, so this is what an invalidate-after-write uses: relaying an FMS
  // status or closing a claim changes which lens it belongs to, and refreshing
  // only the lens the writer happened to be on would leave the other five
  // showing a claim that has moved (R-7-events).
  queues: () => [...reimbKeys.all, "queue"] as const,
  // Every filter value is in the key, for the same reason `cashAdvances` puts
  // the claimant id in its own: two filters are two different lists, and one
  // cache entry for both shows the Admin Officer the last question they asked
  // rather than the one they are asking.
  queue: (filters: ClaimQueueFilters = {}) =>
    [
      ...reimbKeys.all,
      "queue",
      filters.status ?? "any",
      filters.kind ?? "any",
      filters.claimantId ?? "any",
      filters.externalOver ? "external-over" : "all-ages",
    ] as const,
};

// --- R-6-clock: cash advances + the COA 30-day liquidation clock ------------

/** Spec §5.4 statuses. `overdue` is a real stored status, not a derived badge —
 *  spec §13 asks for the count and peso total of overdue advances. */
export type CashAdvanceStatus =
  | "open"
  | "liquidation_started"
  | "settled"
  | "overdue";

/** The server's urgency verdict (`services/deadline.py`). Never recomputed. */
export type DeadlineState = "on_track" | "due_soon" | "overdue";

/**
 * Which branch of spec §6.2 a settlement took, decided server-side by
 * `per_diem.settle` and PINNED on the advance. The client never derives it from
 * the totals — two implementations of one decision would eventually disagree.
 */
export type SettlementMode = "refund" | "exact" | "over_advance";

export interface CashAdvance {
  id: number;
  claimant_id: number;
  claimant_name: string | null;
  dv_no: string | null;
  dv_date: string | null;
  dpo_no: string | null;
  /** 2-dp string — server-computed money, displayed never calculated. */
  amount: string;
  date_return: string | null;
  status: CashAdvanceStatus;
  status_label: string;
  settled_at: string | null;
  /**
   * How the liquidation's money came out (R-6-liq-settle, spec §6.2). Null
   * until settled. `refund_*` are populated on the `refund` mode only — on the
   * other two nothing came back, and a receipt for a payment that never
   * happened is exactly what the server refuses to record.
   */
  settlement_mode: SettlementMode | null;
  refund_or_no: string | null;
  refund_or_date: string | null;
  refund_amount: string | null;
  /**
   * The clock. All four are null together when there is no return date yet —
   * a trip that has not happened has no deadline, and a zero would be a lie.
   * They also go null once SETTLED: a closed advance is not counting down to
   * anything, so the card must not keep threatening a traveller who answered.
   */
  deadline_date: string | null;
  deadline_basis: string | null;
  days_remaining: number | null;
  deadline_state: DeadlineState | null;
  /** COA consequence copy from config — present only once it applies. */
  overdue_note: string | null;
  /**
   * The liquidation started against this advance (R-6-liq-chain), if any.
   * Rides the advance so the card decides between "Liquidate" and "Open
   * LQ-…" from ONE response — two requests could disagree, and the
   * disagreement would show as a button that 409s.
   */
  liquidation_claim_id: number | null;
  liquidation_ref_no: string | null;
  liquidation_status: ClaimStatus | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface CashAdvanceInput {
  claimant_id: number;
  amount: string;
  dv_no?: string | null;
  dv_date?: string | null;
  dpo_no?: string | null;
  date_return?: string | null;
}

export type CashAdvancePatch = Partial<Omit<CashAdvanceInput, "claimant_id">>;

export function fetchCashAdvances(claimantId?: number): Promise<CashAdvance[]> {
  const query = claimantId === undefined ? "" : `?claimant_id=${claimantId}`;
  return api<{ items: CashAdvance[] }>(
    `/reimbursement/cash-advances${query}`,
  ).then((r) => r.items);
}

export function fetchCashAdvance(id: number): Promise<CashAdvance> {
  return api<CashAdvance>(`/reimbursement/cash-advances/${id}`);
}

export function createCashAdvance(body: CashAdvanceInput): Promise<CashAdvance> {
  return api<CashAdvance>("/reimbursement/cash-advances", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateCashAdvance(
  id: number,
  patch: CashAdvancePatch,
): Promise<CashAdvance> {
  return api<CashAdvance>(`/reimbursement/cash-advances/${id}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

/** Spec §9.3 step 1's "Liquidate that instead?" — 201 with the fresh draft. */
export function liquidateCashAdvance(id: number): Promise<ClaimDetail> {
  return api<ClaimDetail>(`/reimbursement/cash-advances/${id}/liquidate`, {
    method: "POST",
  });
}

/**
 * Record how a liquidation settled, and close it — spec §6.2 (R-6-liq-settle).
 *
 * Note what this body does NOT carry: the settlement mode, or the amount as a
 * proposal. Both are the server's (`per_diem.settle`). `refund_amount` is an
 * ECHO only — send it and a stale screen is caught before it records a receipt
 * against the wrong figure; omit it and the server figure stands regardless.
 */
export interface SettlementInput {
  or_no?: string | null;
  or_date?: string | null;
  refund_amount?: string | null;
  comment?: string | null;
  expected_version?: number | null;
}

export function settleClaim(
  id: number,
  body: SettlementInput = {},
): Promise<ClaimDetail> {
  return api<ClaimDetail>(`/reimbursement/claims/${id}/settle`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/**
 * Relay one FMS journey update (spec §6.1 row 6) — R-7-events.
 *
 * Appends and moves nothing: the sub-statuses are not workflow states, they
 * ride an append-only event table over the single `handed_to_fms` state. The
 * response is the whole claim, because the relay changes what the rail says and
 * what the tracker shows.
 */
export interface ExternalEventInput {
  status: ExternalStatus;
  noted_by?: string | null;
  note?: string | null;
  event_date?: string | null;
}

export function recordExternalEvent(
  id: number,
  body: ExternalEventInput,
): Promise<ClaimDetail> {
  return api<ClaimDetail>(`/reimbursement/claims/${id}/external-events`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function fetchExternalEvents(id: number): Promise<ExternalEvent[]> {
  return api<ExternalEvent[]>(`/reimbursement/claims/${id}/external-events`);
}

/**
 * Close a claim, recording what FMS paid (spec §6.1 row 8) — R-7-events.
 *
 * Note what this body does NOT carry: the amount. What was owed is the claim's
 * own server-computed `totals`, and a client that could post "paid ₱6,750"
 * could close a claim on a figure the claim never said. The reference and the
 * date are facts only FMS can supply, which is why they are the inputs.
 */
export interface MarkPaidInput {
  payout_ref: string;
  paid_on: string;
  comment?: string | null;
  expected_version?: number | null;
}

export function markPaid(
  id: number,
  body: MarkPaidInput,
): Promise<ClaimDetail> {
  return api<ClaimDetail>(`/reimbursement/claims/${id}/mark-paid`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Spec §6.2's "one tap, pre-filled" — 201 with the fresh draft. */
export function spawnReimbursement(id: number): Promise<ClaimDetail> {
  return api<ClaimDetail>(`/reimbursement/claims/${id}/spawn-reimbursement`, {
    method: "POST",
  });
}

export function createClaim(): Promise<ClaimDetail> {
  return api<ClaimDetail>("/reimbursement/claims", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function fetchClaim(id: number): Promise<ClaimDetail> {
  return api<ClaimDetail>(`/reimbursement/claims/${id}`);
}

export function updateClaim(id: number, patch: ClaimPatch): Promise<ClaimDetail> {
  return api<ClaimDetail>(`/reimbursement/claims/${id}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export function replaceLegs(id: number, legs: LegInput[]): Promise<ClaimDetail> {
  return api<ClaimDetail>(`/reimbursement/claims/${id}/legs`, {
    method: "PUT",
    body: JSON.stringify({ legs }),
  });
}

export function computeClaim(id: number): Promise<ClaimDetail> {
  return api<ClaimDetail>(`/reimbursement/claims/${id}/compute`, {
    method: "POST",
  });
}

export function submitClaim(id: number): Promise<ClaimDetail> {
  return api<ClaimDetail>(`/reimbursement/claims/${id}/submit`, {
    method: "POST",
  });
}

export function cancelClaim(id: number, comment: string): Promise<ClaimDetail> {
  return api<ClaimDetail>(`/reimbursement/claims/${id}/cancel`, {
    method: "POST",
    body: JSON.stringify({ comment }),
  });
}

export function fetchMyWork(): Promise<MyWorkResponse> {
  return api<MyWorkResponse>("/reimbursement/my-work");
}

/**
 * The oversight queue (R-7-queue). Unlike My Work this lists other people's
 * claims, so the server answers 403 to anyone who oversees nobody — the page
 * renders that as an explanation rather than an empty list.
 */
export function fetchClaimQueue(
  filters: ClaimQueueFilters = {},
): Promise<ClaimQueueResponse> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.kind) params.set("kind", filters.kind);
  if (filters.claimantId !== undefined)
    params.set("claimant_id", String(filters.claimantId));
  if (filters.externalOver) params.set("external_over", "true");
  const query = params.toString();
  return api<ClaimQueueResponse>(
    `/reimbursement/claims${query ? `?${query}` : ""}`,
  );
}

export function fetchRegions(): Promise<Region[]> {
  return api<Region[]>("/reimbursement/regions");
}

/**
 * Clear the current gate. The same call at every rung of the chain — the
 * server decides where the claim lands; only the button label differs
 * (see `actionLabel` in pages/reimbursement/claim-status.ts).
 */
export function approveClaim(
  id: number,
  body: { comment?: string; expected_version?: number | null } = {},
): Promise<ClaimDetail> {
  return api<ClaimDetail>(`/reimbursement/claims/${id}/approve`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Bounce the claim back. ≥1 taxonomy reason AND a comment, both server-enforced. */
export function returnClaim(
  id: number,
  body: {
    comment: string;
    reason_ids: number[];
    expected_version?: number | null;
  },
): Promise<ClaimDetail> {
  return api<ClaimDetail>(`/reimbursement/claims/${id}/return`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function fetchTimeline(id: number): Promise<TimelineEvent[]> {
  return api<TimelineEvent[]>(`/reimbursement/claims/${id}/timeline`);
}

export function fetchReturnReasons(): Promise<ReturnReason[]> {
  return api<ReturnReason[]>("/reimbursement/return-reasons");
}

// --- R-3: the documentary packet -------------------------------------------

export function fetchChecklist(id: number): Promise<ChecklistResponse> {
  return api<ChecklistResponse>(`/reimbursement/claims/${id}/checklist`);
}

/**
 * The one multipart call in the app. `api()` leaves Content-Type unset for a
 * FormData body so the browser writes its own boundary.
 */
export function uploadChecklistFile(
  id: number,
  catalogId: number,
  file: File,
): Promise<ChecklistResponse> {
  const body = new FormData();
  body.append("file", file);
  return api<ChecklistResponse>(
    `/reimbursement/claims/${id}/checklist/${catalogId}/attachments`,
    { method: "POST", body },
  );
}

/**
 * Ask the server to prepare the claim's generated documents.
 *
 * Returns 202, not 200: rendering runs in the worker (WeasyPrint never sits in
 * a request path), so the response carries the packet as it stands plus whether
 * a worker actually took the job. `queued: false` is not an error — it is the
 * honest signal that generation is unavailable, which the UI shows as a
 * non-blocking notice rather than a spinner that never resolves.
 */
export function generateClaimDocuments(
  id: number,
): Promise<GenerateDocumentsResponse> {
  return api<GenerateDocumentsResponse>(
    `/reimbursement/claims/${id}/documents/generate`,
    { method: "POST" },
  );
}

export interface GenerateDocumentsResponse {
  checklist: ChecklistResponse;
  queued: boolean;
}

/** `fileId` is the reimb_attachments join row, not the core attachment id. */
export function removeChecklistFile(
  id: number,
  catalogId: number,
  fileId: number,
): Promise<ChecklistResponse> {
  return api<ChecklistResponse>(
    `/reimbursement/claims/${id}/checklist/${catalogId}/attachments/${fileId}`,
    { method: "DELETE" },
  );
}
