/**
 * Checklist display vocabulary (R-3) — the sibling of `claim-status.ts`.
 *
 * Division of authorship, stated once and applied everywhere:
 * - MACHINE ENUMS (`status`, `group`, `evidence`) come from the server;
 * - VOCABULARY (chip words, group headings, the mapping onto the four platform
 *   semantics) is client-side, here, because ui-standards owns it;
 * - RULE PROSE (`gate_message`, `required_because`, `flag_reason`) comes from
 *   the server and is rendered verbatim, because it cites claim data and
 *   circulars the client cannot see.
 *
 * That last line is what makes wording parity structural rather than a
 * discipline: the client authors no gate wording, so nothing can drift.
 */

import type {
  ChecklistGroup,
  ChecklistItem,
  ChecklistSummary,
  ScanStatus,
} from "../../api/reimbursement";
import type { SemanticStatus } from "../../components/StatusChip/StatusChip";

/** The 7 catalog groups in COA order (models/enums.py::ChecklistGroup). */
export const CHECKLIST_GROUP_ORDER = [
  "authority",
  "itinerary",
  "proof_of_travel",
  "transport",
  "lodging_meals",
  "report",
  "financial",
] as const satisfies readonly ChecklistGroup[];

/** Sentence case (ui-standards §5). */
export const CHECKLIST_GROUP_LABEL: Record<ChecklistGroup, string> = {
  authority: "Authority to travel",
  itinerary: "Itinerary",
  proof_of_travel: "Proof of travel",
  transport: "Transport",
  lodging_meals: "Lodging and meals",
  report: "Report",
  financial: "Financial",
};

export interface ItemPresentation {
  status: SemanticStatus;
  label: string;
}

/**
 * Spec §9.1's six-word chip vocabulary onto the four platform semantics (§2).
 *
 * Required-and-missing is AMBER, not red. On a fresh draft every required item
 * is missing, and a wall of red on a screen you have just arrived at reads as
 * "you did something wrong" — the opposite of §9.1 principle 4. Red is reserved
 * for the moment an item actually blocks a decision: the Review gate panel and
 * the approver's callout. Same item, two contexts; colour follows consequence.
 */
export function itemPresentation(item: ChecklistItem): ItemPresentation {
  switch (item.status) {
    case "missing":
      return item.required
        ? { status: "warn", label: "To do" }
        : { status: "waiting", label: "Optional" };
    case "attached":
      return { status: "done", label: "Attached" };
    case "generated":
      return { status: "done", label: "Generated" };
    case "auto_passed":
      return { status: "done", label: "Checked" };
    // "A flag never blocks alone" (spec §5.3) — amber, never red.
    case "auto_flagged":
      return { status: "warn", label: "Flagged" };
    case "waived":
      return { status: "waiting", label: "Waived" };
  }
}

/**
 * The FILE's state, which is NOT the item's state: an upload lands
 * `scan_status: "pending"` and is not downloadable, while the ITEM already
 * counts as attached. Two facts, two chips — conflating them is the lie.
 */
export const SCAN_PRESENTATION: Record<ScanStatus, ItemPresentation> = {
  pending: { status: "waiting", label: "Checking" },
  clean: { status: "done", label: "Attached" },
  infected: { status: "blocked", label: "Removed" },
  error: { status: "blocked", label: "Check failed" },
};

/** Honest copy for a file that exists but cannot yet be opened. */
export const SCAN_NOTE: Record<ScanStatus, string | null> = {
  pending:
    "We are checking this file for viruses. It is saved and counts towards your packet — you can submit now. It becomes downloadable once the check finishes.",
  clean: null,
  infected:
    "This file failed the security check and was removed. Upload a different copy.",
  error:
    "We could not check this file. Upload it again, or ask the admin officer for help.",
};

/** Copy per evidence kind — what the claimant is being asked for, or not.
 *
 * `generated_doc` is the state BEFORE generation. Once the document exists the
 * Documents step renders a Generated card instead and this line is not shown —
 * see `generatedDocHelp`.
 */
export const EVIDENCE_HELP: Record<string, string | null> = {
  upload: "Attach a scan or a photo.",
  external_wet_sign:
    "Print this, get it signed by hand, then upload a scan or photo of the signed page.",
  generated_doc:
    "The system fills this in from what you have entered. Nothing for you to upload.",
  data_only: "Taken from what you already entered. Nothing to attach.",
};

/**
 * Copy for a `generated_doc` item, which unlike every other evidence kind has
 * three distinct states rather than one.
 *
 * The R-3 placeholder ("the system will generate this with your printable
 * packet") was a promise about a feature that did not exist. Now that it does,
 * the copy has to say which of three situations the claimant is actually in —
 * and crucially, that "not yet" is never their fault and never blocks them
 * (§9.1 principle 4; generated documents are excluded from the submit gate by
 * design, because they are produced downstream of submit).
 */
export function generatedDocHelp(item: ChecklistItem): string {
  if (item.status === "generated") {
    return item.files.some((file) => file.origin === "generated")
      ? "Prepared for you from what you entered. Check it before you submit."
      : "Prepared for you from what you entered.";
  }
  return "Not prepared yet. It is filled in from what you entered — you can still submit without it.";
}

/** Spec §9.1's exact wording: "9 of 12 required items done". */
export function checklistProgress(summary: ChecklistSummary): string {
  return `${summary.required_done} of ${summary.required_total} required items done`;
}

/**
 * Used only when the server sends no `gate_message` (a pre-R-3 cached payload).
 * Mirrors `services/errors.py::packet_incomplete`.
 */
export const GATE_FALLBACK =
  "Attach the missing required documents before you submit this claim.";

export function gateMessage(summary: ChecklistSummary): string {
  return summary.gate_message ?? GATE_FALLBACK;
}

/** An engine with nothing to say. Keeps every consumer on ONE shape. */
export const EMPTY_CHECKLIST_SUMMARY: ChecklistSummary = {
  required_total: 0,
  required_done: 0,
  complete: true,
  blocking: [],
  flags: [],
  gate_message: null,
};

/** The DOM id a Review-step blocker links to on the Documents page. */
export function checklistItemAnchor(catalogId: number): string {
  return `checklist-item-${catalogId}`;
}
