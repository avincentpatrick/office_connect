import { describe, expect, it } from "vitest";

import type { ClaimStatus } from "../../api/reimbursement";
import {
  CLAIM_STATUS_TO_SEMANTIC,
  actionLabel,
  approveConsequence,
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
