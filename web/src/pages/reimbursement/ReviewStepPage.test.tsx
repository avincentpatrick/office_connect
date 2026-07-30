import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ClaimDetail } from "../../api/reimbursement";
import { renderRoutes, stubFetch } from "../../test/harness";
import { completeClaim } from "../../test/reimb-fixtures";
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
