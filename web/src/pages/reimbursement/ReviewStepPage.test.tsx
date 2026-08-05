import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ClaimDetail } from "../../api/reimbursement";
import { renderRoutes, stubFetch } from "../../test/harness";
import {
  completeClaim,
  documentsPending,
  makeReturnReason,
} from "../../test/reimb-fixtures";
import { ClaimConfirmationPage } from "./ClaimConfirmationPage";
import { ReviewStepPage } from "./ReviewStepPage";

const ROUTES = [
  { path: "/reimbursement/claims/:claimId/review", element: <ReviewStepPage /> },
  {
    path: "/reimbursement/claims/:claimId/confirmation",
    element: <ClaimConfirmationPage />,
  },
];

afterEach(() => vi.unstubAllGlobals());

describe("ReviewStepPage", () => {
  it("renders check-your-answers with server totals through formatPeso", async () => {
    stubFetch({
      "GET /api/v1/reimbursement/claims/7": () => ({ body: completeClaim() }),
    });
    renderRoutes(ROUTES, "/reimbursement/claims/7/review");

    expect(await screen.findByText("Regional immunization review")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Change/ }).length).toBeGreaterThan(3);
    // Server strings rendered verbatim through formatPeso — never computed.
    expect(screen.getAllByText("₱6,750.00").length).toBeGreaterThan(0);
    expect(screen.getByText("₱1,100.00")).toBeInTheDocument(); // the 50% return day
    expect(screen.getByRole("button", { name: "Submit claim" })).toBeInTheDocument();
  });

  it("deep-linking the confirmation for a returned claim bounces to review", async () => {
    stubFetch({
      "GET /api/v1/reimbursement/claims/7": () => ({
        body: completeClaim({ status: "returned", status_label: "Returned" }),
      }),
    });
    renderRoutes(ROUTES, "/reimbursement/claims/7/confirmation");
    expect(
      await screen.findByRole("button", { name: "Resubmit claim" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Claim submitted")).not.toBeInTheDocument();
  });

  it("deep-linking the confirmation for a cancelled claim shows the record", async () => {
    stubFetch({
      "GET /api/v1/reimbursement/claims/7": () => ({
        body: completeClaim({
          status: "cancelled",
          status_label: "Cancelled/Void",
          next_action: null,
          holder_kind: null,
          holder_display: null,
        }),
      }),
    });
    renderRoutes(ROUTES, "/reimbursement/claims/7/confirmation");
    expect(await screen.findByText("Cancelled/Void")).toBeInTheDocument();
    expect(screen.queryByText("Claim submitted")).not.toBeInTheDocument();
  });

  it("submits and lands on the confirmation with the RB reference", async () => {
    let claim: ClaimDetail = completeClaim();
    stubFetch({
      "GET /api/v1/reimbursement/claims/7": () => ({ body: claim }),
      "POST /api/v1/reimbursement/claims/7/submit": () => {
        claim = completeClaim({
          ref_no: "RB-2026-0001",
          status: "division_approval",
          status_label: "For Approval",
          next_action: "Approve or return",
          holder_display: "Maria Santos",
        });
        return { body: claim };
      },
    });
    renderRoutes(ROUTES, "/reimbursement/claims/7/review");

    await userEvent.click(await screen.findByRole("button", { name: "Submit claim" }));

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Claim submitted" })).toBeInTheDocument(),
    );
    expect(screen.getByText("RB-2026-0001")).toBeInTheDocument();
    expect(screen.getByText(/Maria Santos/)).toBeInTheDocument();
  });
});

describe("the documentary submit gate (spec §2 / §9.3 step 5)", () => {
  it("disables submit and lists every blocking document inline", async () => {
    const claim = documentsPending();
    stubFetch({ "GET /api/v1/reimbursement/claims/7": () => ({ body: claim }) });
    renderRoutes(ROUTES, "/reimbursement/claims/7/review");

    const button = await screen.findByRole("button", { name: "Submit claim" });
    // Visible, so the goal stays legible; disabled, per the spec's wording.
    expect(button).toBeDisabled();

    // The reason is the SERVER's sentence, verbatim, and is id-linked to the
    // button so it is not lost to a disabled control's missing focus.
    const heading = screen.getByText(claim.checklist!.gate_message!);
    expect(button).toHaveAttribute("aria-describedby", heading.id);

    // Every blocker links to its own fix on the Documents step.
    const link = screen.getByRole("link", {
      name: "Approved Travel Order / Authority to Travel",
    });
    expect(link).toHaveAttribute(
      "href",
      "/reimbursement/claims/7/documents#checklist-item-1",
    );
  });

  it("enables submit once the packet is clear", async () => {
    stubFetch({
      "GET /api/v1/reimbursement/claims/7": () => ({ body: completeClaim() }),
    });
    renderRoutes(ROUTES, "/reimbursement/claims/7/review");
    expect(await screen.findByRole("button", { name: "Submit claim" })).toBeEnabled();
  });

  it("surfaces a 422 from the gate verbatim and re-reads the claim", async () => {
    let reads = 0;
    stubFetch({
      "GET /api/v1/reimbursement/claims/7": () => {
        reads += 1;
        return { body: completeClaim() };
      },
      "POST /api/v1/reimbursement/claims/7/submit": () => ({
        status: 422,
        body: {
          error: {
            code: "reimb_packet_incomplete",
            message:
              "1 required document still missing: TO-01 (Approved Travel Order). Attach them on the Documents step, then submit again.",
          },
        },
      }),
    });
    renderRoutes(ROUTES, "/reimbursement/claims/7/review");

    await userEvent.click(
      await screen.findByRole("button", { name: "Submit claim" }),
    );

    expect(
      await screen.findByText(/1 required document still missing/),
    ).toBeInTheDocument();
    // The panel may be empty precisely because we believed it was clear —
    // refetching is what makes the path appear.
    await waitFor(() => expect(reads).toBeGreaterThan(1));
  });
});

describe("the promoted pre-check at step 5 (spec §11, R-8)", () => {
  const REASONS = "GET /api/v1/reimbursement/return-reasons";

  it("warns about promoted reasons WITHOUT blocking the submit", async () => {
    // Spec §11's advisory, and the line it must never cross. R-3's hard gate is
    // about MISSING DOCUMENTS; letting a statistic refuse a legitimate claim
    // would be conflating "often returned" with "incomplete".
    stubFetch({
      "GET /api/v1/reimbursement/claims/7": () => ({ body: completeClaim() }),
      [REASONS]: () => ({
        body: [
          makeReturnReason({ id: 1, promoted: true }),
          makeReturnReason({
            id: 2, code: "PER_DIEM_CALC", label: "Per-diem miscomputed",
            category: "wrong_amount", promoted: false,
          }),
        ],
      }),
    });
    renderRoutes(ROUTES, "/reimbursement/claims/7/review");

    expect(
      await screen.findByText(/Claims like yours are often returned because/),
    ).toBeInTheDocument();
    expect(screen.getByText("Missing official receipt")).toBeInTheDocument();
    // Only the PROMOTED ones — the rest of the taxonomy is the approver's
    // picker, not a list of things to worry a claimant with.
    expect(screen.queryByText("Per-diem miscomputed")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Submit claim" })).toBeEnabled();
  });

  it("carries the reason and never a count", async () => {
    // Spec §11 is aggregates-only and oversight-scoped: what usually goes wrong
    // is guidance a claimant needs; how many colleagues it caught is other
    // people's failures, and this surface is not scoped to show them.
    stubFetch({
      "GET /api/v1/reimbursement/claims/7": () => ({ body: completeClaim() }),
      [REASONS]: () => ({ body: [makeReturnReason({ promoted: true })] }),
    });
    const { container } = renderRoutes(ROUTES, "/reimbursement/claims/7/review");

    await screen.findByText(/often returned because/);
    expect(container.textContent).not.toMatch(/\d+ returns/);
  });

  it("says nothing at all when no reason is promoted", async () => {
    stubFetch({
      "GET /api/v1/reimbursement/claims/7": () => ({ body: completeClaim() }),
      [REASONS]: () => ({ body: [makeReturnReason({ promoted: false })] }),
    });
    renderRoutes(ROUTES, "/reimbursement/claims/7/review");

    await screen.findByRole("button", { name: "Submit claim" });
    expect(
      screen.queryByText(/often returned because/),
    ).not.toBeInTheDocument();
  });

  it("stays silent when the taxonomy cannot be read", async () => {
    // The fail-safe direction here is the OPPOSITE of the usual one. Everywhere
    // else the safe answer is to block or to flag; for an advisory it is to say
    // nothing, because an unexplained warning is worse than no warning.
    stubFetch({
      "GET /api/v1/reimbursement/claims/7": () => ({ body: completeClaim() }),
      [REASONS]: () => ({ status: 500, body: { error: { code: "x", message: "boom" } } }),
    });
    renderRoutes(ROUTES, "/reimbursement/claims/7/review");

    expect(
      await screen.findByRole("button", { name: "Submit claim" }),
    ).toBeEnabled();
    expect(screen.queryByText(/often returned because/)).not.toBeInTheDocument();
  });
});
