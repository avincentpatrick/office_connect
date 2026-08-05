import { describe, expect, it } from "vitest";

import type { ClaimStatus } from "../../api/reimbursement";
import { makeQueueItem } from "../../test/reimb-fixtures";
import {
  CLAIM_STATUS_TO_SEMANTIC,
  actionLabel,
  approveConsequence,
  queueMeta,
} from "./claim-status";

/**
 * R-6-liq-chain: the display logic now spans TWO chains.
 *
 * `approve` is one endpoint at every rung of both, so the STATUS is the only
 * thing telling an actor what they are about to do. On the liquidation chain
 * that is not cosmetic — "Approve" and "Certify" are different acts to an
 * auditor, and the words on the button are what the person read before signing.
 */

const REIMBURSEMENT: ClaimStatus[] = [
  "draft",
  "division_approval",
  "admin_review",
  "handed_to_fms",
  "fms_returned",
  "returned",
  "paid_closed",
  "cancelled",
];
const LIQUIDATION: ClaimStatus[] = [
  "draft",
  "certify_b",
  "certify_c",
  "handed_to_fms",
  "returned",
  "settled",
  "cancelled",
];

describe("claim-status", () => {
  it("maps every state of both chains onto a semantic", () => {
    for (const status of [...REIMBURSEMENT, ...LIQUIDATION]) {
      expect(CLAIM_STATUS_TO_SEMANTIC[status]).toBeTruthy();
    }
    // The certifications are gates: the ball is with a named person and the
    // claimant has nothing to do, which is grey/waiting, not amber.
    expect(CLAIM_STATUS_TO_SEMANTIC.certify_b).toBe("waiting");
    expect(CLAIM_STATUS_TO_SEMANTIC.certify_c).toBe("waiting");
    // `settled` is the liquidation's `paid_closed`.
    expect(CLAIM_STATUS_TO_SEMANTIC.settled).toBe(
      CLAIM_STATUS_TO_SEMANTIC.paid_closed,
    );
  });

  it("labels the liquidation certifications as certifications", () => {
    expect(actionLabel("approve", "certify_b")).toBe("Certify");
    expect(actionLabel("approve", "certify_c")).toBe(
      "Record certification & hand to FMS",
    );
    // The shared states keep the claim chain's wording — `handed_to_fms` is the
    // same external leg in both, and the claim chain's copy came from spec §6.1.
    expect(actionLabel("approve", "division_approval")).toBe("Approve");
    expect(actionLabel("approve", "admin_review")).toBe("Approve & hand to FMS");
  });

  it("tells the Admin Officer what certification C actually commits them to", () => {
    const copy = approveConsequence("certify_c");
    // The comment is the ONLY record of C the system keeps (the wet signature
    // is on paper, and snapshot-binding is core-service #3's unbuilt half), so
    // the confirm sheet must say so — ui-standards §3.10.
    expect(copy).toMatch(/signed/i);
    expect(copy).toMatch(/comment/i);
    expect(approveConsequence("certify_b")).toMatch(/Accounting Unit/);
  });

  it("still folds the flag warning into either chain's consequence", () => {
    expect(approveConsequence("certify_b", 2)).toMatch(
      /2 automatic checks are flagged/,
    );
    expect(approveConsequence("certify_b", 0)).not.toMatch(/flagged/);
  });
});

/**
 * R-7-events: the FMS leg. Two verbs the server rewrites or synthesizes, and
 * one queue line that has to carry "how long" and "where" as separate facts.
 */
describe("claim-status — the FMS leg", () => {
  it("labels the two verbs the server invents for the FMS leg", () => {
    // `mark_paid` deliberately reads the SAME as the old `approve` label at
    // this state: the act has not changed, only what it now has to record.
    expect(actionLabel("mark_paid", "handed_to_fms")).toBe("Mark paid & close");
    expect(actionLabel("approve", "handed_to_fms")).toBe("Mark paid & close");
    // The relay is not a decision and moves nothing — the verb says so.
    expect(actionLabel("relay_fms", "handed_to_fms")).toBe("Update FMS status");
    expect(actionLabel("relay_fms", "handed_to_fms")).not.toMatch(/approve/i);
  });

  it("puts the last FMS word beside the working-day count", () => {
    // Two different facts: 12 days in Payment Processing is a different
    // conversation from 12 days in Budget, and the second is what decides
    // whether the follow-up call is worth making.
    const meta = queueMeta(
      makeQueueItem({
        days_with_fms: 12,
        external_followup: true,
        external_status_label: "Payment processing",
      }),
    );
    expect(meta).toContain("12 working days with FMS");
    expect(meta).toContain("Last: Payment processing");
  });

  it("says nothing about a status FMS has not given", () => {
    // Absence is honest here — a packet handed over this morning has no news,
    // and inventing "Last: With Budget" would report a call nobody made.
    const meta = queueMeta(
      makeQueueItem({ days_with_fms: 1, external_status_label: null }),
    );
    expect(meta).toContain("1 working day with FMS");
    expect(meta).not.toContain("Last:");
  });

  it("falls back to days-in-state for a claim the bureau still holds", () => {
    const meta = queueMeta(
      makeQueueItem({
        status: "admin_review",
        status_label: "Admin Review",
        holder_kind: "user",
        days_with_fms: null,
        days_in_state: 3,
        external_status_label: null,
      }),
    );
    expect(meta).toContain("3 days in this step");
    expect(meta).not.toContain("with FMS");
  });
});
