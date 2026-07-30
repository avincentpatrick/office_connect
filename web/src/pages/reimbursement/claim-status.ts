/**
 * Module display logic: claim status → the platform's four semantic statuses
 * (ui-standards §2 — amber = action on someone, grey = in-flight waiting,
 * green = paid, red = void) + the My-Work meta-line composer.
 */

import type { ClaimStatus, WorkItem } from "../../api/reimbursement";
import type { SemanticStatus } from "../../components/StatusChip/StatusChip";
import { formatPeso } from "../../lib/format";

export const CLAIM_STATUS_TO_SEMANTIC: Record<ClaimStatus, SemanticStatus> = {
  draft: "warn",
  returned: "warn",
  fms_returned: "warn",
  division_approval: "waiting",
  admin_review: "waiting",
  handed_to_fms: "waiting",
  paid_closed: "done",
  cancelled: "blocked",
};

export function workItemTitle(item: WorkItem): string {
  return item.purpose || item.destination || "Travel claim";
}

/** "Holder: Maria Santos · 3 days in this step · Next: Approve or return · ₱6,750.00" */
export function myWorkMeta(item: WorkItem): string {
  const parts: string[] = [];
  if (item.holder_display) parts.push(`Holder: ${item.holder_display}`);
  parts.push(
    `${item.days_in_state} ${item.days_in_state === 1 ? "day" : "days"} in this step`,
  );
  if (item.next_action) parts.push(`Next: ${item.next_action}`);
  if (item.grand) parts.push(formatPeso(item.grand));
  return parts.join(" · ");
}
