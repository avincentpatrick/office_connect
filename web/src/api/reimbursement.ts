/**
 * Wire types + client for /api/v1/reimbursement (R-2-wizard). Field names are
 * the backend wire names (office_connect/modules/reimbursement/api/schemas.py).
 * Money crosses as 2-dp strings, server-computed — the client displays, never
 * computes (tech-stack §4 hard prohibition). Also exports `reimbKeys`, the
 * module's react-query key factory (the codebase's first; core keys `["me"]` /
 * `["config"]` stay as literals).
 */

import { api } from "./http";

export type ClaimStatus =
  | "draft"
  | "division_approval"
  | "admin_review"
  | "handed_to_fms"
  | "fms_returned"
  | "returned"
  | "paid_closed"
  | "cancelled";

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
  kind: string;
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
  created_at: string;
  updated_at: string;
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
  | "cancel";

/** Spec §6.3 derived badge — computed on view, never stored as a status. */
export type SlaState = "on_track" | "due_soon" | "overdue";

export interface ReturnReason {
  id: number;
  code: string;
  label: string;
  category: string;
}

/** One row of the claim tracker (spec §9.2), from reimb_status_histories. */
export interface TimelineEvent {
  id: number;
  from_status: ClaimStatus | null;
  from_status_label: string | null;
  to_status: ClaimStatus;
  to_status_label: string;
  actor_display: string | null;
  note: string | null;
  /** Populated on the rows a return produced — shown to the claimant verbatim. */
  reasons: ReturnReason[];
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
};

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
