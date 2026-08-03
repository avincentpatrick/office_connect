/**
 * Module display logic: claim status → the platform's four semantic statuses
 * (ui-standards §2 — amber = action on someone, grey = in-flight waiting,
 * green = paid, red = void) + the My-Work meta-line composer.
 */

import type {
  ClaimAction,
  ClaimStatus,
  SlaState,
  WorkItem,
} from "../../api/reimbursement";
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

/**
 * The SLA badge (spec §6.3) is a SECOND axis from claim status: status says
 * where the claim is, the badge says how late it is. Both map onto the same
 * four platform semantics so a red chip means the same thing everywhere.
 */
export const SLA_STATE_TO_SEMANTIC: Record<SlaState, SemanticStatus> = {
  on_track: "done",
  due_soon: "warn",
  overdue: "blocked",
};

export const SLA_STATE_LABEL: Record<SlaState, string> = {
  on_track: "On track",
  due_soon: "Due soon",
  overdue: "Overdue",
};

/**
 * The label for a server-offered action. `approve` is the same action at every
 * rung of the chain, so the CLAIM'S CURRENT STATUS is what tells the approver
 * what they are actually about to do — "Approve" and "Mark paid & close" are
 * one endpoint (spec §6.1 rows 3/5/6).
 */
export function actionLabel(action: ClaimAction, status: ClaimStatus): string {
  if (action === "approve") {
    switch (status) {
      case "admin_review":
        return "Approve & hand to FMS";
      case "handed_to_fms":
        return "Mark paid & close";
      default:
        return "Approve";
    }
  }
  if (action === "return") {
    // From fms_returned the Admin Officer is relaying FMS's comments onward,
    // not bouncing the packet themselves (spec §6.1 row 7).
    return status === "fms_returned" ? "Return to claimant" : "Return";
  }
  if (action === "resubmit") return "Resubmit";
  if (action === "submit") return "Submit";
  return "Cancel";
}

/** The plain-language consequence the approve confirm states (ui-standards §3.10). */
export function approveConsequence(
  status: ClaimStatus,
  flagCount = 0,
): string {
  const base = (() => {
    switch (status) {
      case "admin_review":
        return "The packet leaves the bureau and goes to FMS for payment processing. You cannot pull it back.";
      case "handed_to_fms":
        return "This closes the claim as paid. It becomes read-only for everyone.";
      default:
        return "The claim moves to the next approver and leaves your queue.";
    }
  })();
  if (flagCount === 0) return base;
  // Spec §9.4's "(logged)" turned into informed consent: the confirm sheet is
  // where §3.10's "state the consequence in plain language" meets it.
  const subject =
    flagCount === 1
      ? "1 automatic check is"
      : `${flagCount} automatic checks are`;
  return `${subject} flagged on this claim. Approving past a flag is recorded against your name. ${base}`;
}

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
