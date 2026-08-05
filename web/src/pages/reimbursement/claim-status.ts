/**
 * Module display logic: claim status → the platform's four semantic statuses
 * (ui-standards §2 — amber = action on someone, grey = in-flight waiting,
 * green = paid, red = void) + the My-Work meta-line composer.
 */

import type {
  ClaimAction,
  ClaimDetail,
  ClaimStatus,
  QueueItem,
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
  // Liquidation (spec §6.2). The certifications are gates like any other —
  // grey/waiting, because the ball is with a named person and the claimant has
  // nothing to do. `settled` is the liquidation's `paid_closed`: done.
  certify_b: "waiting",
  certify_c: "waiting",
  settled: "done",
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
      // The liquidation chain reuses `approve` for its certifications, so the
      // STATUS is again what tells the actor what they are about to do — and
      // here the words matter more than usual: "Approve" and "Certify" are
      // different acts to an auditor.
      case "certify_b":
        return "Certify";
      case "certify_c":
        return "Record certification & hand to FMS";
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
  if (action === "cancel") return "Cancel";
  // `settle` is the liquidation chain's terminal verb (R-6-liq-settle). The
  // server rewrites `approve` into it at handed_to_fms, because the same
  // transition now also has to record the money.
  if (action === "settle") return "Record settlement";
  // The reimbursement chain's, rewritten the same way at the same state
  // (R-7-events). Deliberately the SAME words the `approve` label used to
  // carry there — the act has not changed, only what it now has to record.
  if (action === "mark_paid") return "Mark paid & close";
  // Not a decision and not a transition: it appends to the FMS journey. The
  // verb says "update", never "approve", because nothing moves.
  if (action === "relay_fms") return "Update FMS status";
  // Rendered by SettlementOutcome with the peso figure in it, not by the
  // decision bar — this label is the fallback wording.
  if (action === "spawn") return "Claim the difference";
  // Exhaustive by construction: `action` is `never` here, so adding a verb to
  // the ClaimAction union without labelling it fails `tsc`. The old bare
  // `return "Cancel"` fallthrough silently rendered any new verb as a
  // destructive Cancel button.
  const exhaustive: never = action;
  return exhaustive;
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
      case "certify_b":
        return "You are certifying this liquidation as correct. It goes to the Accounting Unit for certification C.";
      case "certify_c":
        return "You are recording that the Head of the Accounting Unit signed this liquidation. Name whose signature and when in the comment — it is the only record of that certification the system keeps.";
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

/** Actions that imply the generate endpoint will accept this actor. */
const PREPARE_ACTIONS: readonly string[] = [
  "approve",
  "return",
  "submit",
  "resubmit",
];

/**
 * Whether to offer "Prepare the packet" when none exists (R-5-packet).
 *
 * The server owns the real rule (owner-while-editable, or a scoped
 * reviewer/approver). The action set is the closest thing the client honestly
 * knows: anyone the server says may move this claim is someone the generate
 * endpoint also accepts. A scoped reviewer who is not the current holder gets
 * no button — conservative on purpose, per the R-4-screens doctrine that the UI
 * is never offered a button certain to fail.
 */
export function canPreparePacket(claim: ClaimDetail): boolean {
  return claim.available_actions.some((action) => PREPARE_ACTIONS.includes(action));
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

/**
 * The oversight-queue meta line (R-7-queue). Leads with the traveller, because
 * this list mixes them and "whose is it" is the first question an Admin Officer
 * asks; then the FMS working-day count where it applies, in WORKING days
 * because that is the unit the server counted and the unit spec §7 rule 5 uses.
 */
export function queueMeta(item: QueueItem): string {
  const parts: string[] = [];
  if (item.claimant_display) parts.push(item.claimant_display);
  if (item.holder_display) parts.push(`Holder: ${item.holder_display}`);
  if (item.days_with_fms !== null) {
    parts.push(
      `${item.days_with_fms} working ${item.days_with_fms === 1 ? "day" : "days"} with FMS`,
    );
    // What FMS last said, where they have said anything (R-7-events). How long
    // and where are different facts, and the second is what decides whether the
    // follow-up call is worth making: 12 days in Payment Processing is a
    // different conversation from 12 days in Budget.
    if (item.external_status_label) {
      parts.push(`Last: ${item.external_status_label}`);
    }
  } else {
    parts.push(
      `${item.days_in_state} ${item.days_in_state === 1 ? "day" : "days"} in this step`,
    );
  }
  if (item.next_action) parts.push(`Next: ${item.next_action}`);
  if (item.grand) parts.push(formatPeso(item.grand));
  return parts.join(" · ");
}

/**
 * The chip a queue row wears (R-7-queue), most-urgent axis first.
 *
 * Three axes can be true at once — the claim's status, its holder SLA, and how
 * long FMS has had it — and one chip has to carry the most actionable of them.
 * An FMS follow-up outranks an overdue gate here because this is the surface
 * that exists to surface it: the gate ladder already nudges its holder
 * (spec §7 rule 4), while nobody nudges FMS at all.
 */
export function queueChip(item: QueueItem): {
  status: SemanticStatus;
  label: string;
} {
  if (item.external_followup) {
    return { status: "blocked", label: "Chase FMS" };
  }
  if (item.sla_state === "overdue" || item.sla_state === "due_soon") {
    return {
      status: SLA_STATE_TO_SEMANTIC[item.sla_state],
      label: SLA_STATE_LABEL[item.sla_state],
    };
  }
  return {
    status: CLAIM_STATUS_TO_SEMANTIC[item.status],
    label: item.status_label,
  };
}
