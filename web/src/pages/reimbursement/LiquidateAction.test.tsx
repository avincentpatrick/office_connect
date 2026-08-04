import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expectNoA11yViolations } from "../../test/a11y";
import { renderRoutes, stubFetch } from "../../test/harness";
import { completeClaim, makeCashAdvance } from "../../test/reimb-fixtures";
import { LiquidateAction } from "./LiquidateAction";

const PATH = "/reimbursement";
const routes = (advance = makeCashAdvance(), canStart = true) => [
  { path: PATH, element: <LiquidateAction advance={advance} canStart={canStart} /> },
  { path: "/reimbursement/claims/:id", element: <p>Claim page</p> },
];

afterEach(() => vi.unstubAllGlobals());

describe("LiquidateAction", () => {
  it("offers the traveller a way to answer their own countdown", async () => {
    const claim = completeClaim({ id: 88, kind: "liquidation", ref_no: null });
    stubFetch({
      "POST /api/v1/reimbursement/cash-advances/41/liquidate": () => ({
        status: 201,
        body: claim,
      }),
    });
    const { container } = renderRoutes(routes(), PATH);

    const button = await screen.findByRole("button", {
      name: "Liquidate this advance",
    });
    await expectNoA11yViolations(container);
    await userEvent.click(button);

    // Straight into the wizard on the response that created the draft.
    await waitFor(() =>
      expect(screen.getByText("Claim page")).toBeInTheDocument(),
    );
  });

  it("links to the existing liquidation instead of offering a second one", async () => {
    const advance = makeCashAdvance({
      status: "liquidation_started",
      status_label: "Liquidation started",
      liquidation_claim_id: 88,
      liquidation_ref_no: "LQ-2026-0001",
      liquidation_status: "certify_b",
    });
    renderRoutes(routes(advance), PATH);

    // The advance carries the answer, so no request is needed to decide —
    // stubFetch would have thrown on an unstubbed call.
    expect(
      screen.getByRole("link", { name: "Open LQ-2026-0001" }),
    ).toHaveAttribute("href", "/reimbursement/claims/88");
    expect(
      screen.queryByRole("button", { name: "Liquidate this advance" }),
    ).not.toBeInTheDocument();
  });

  it("never offers Accounting a button that would 403", async () => {
    // Filing IS certification A, so the endpoint is owner-only. A clerk sees
    // whether a liquidation exists, never an action certain to fail.
    renderRoutes(routes(makeCashAdvance(), false), PATH);
    expect(
      screen.queryByRole("button", { name: "Liquidate this advance" }),
    ).not.toBeInTheDocument();
  });

  it("offers nothing at all once the advance is settled", () => {
    const settled = makeCashAdvance({ status: "settled", status_label: "Settled" });
    const { container } = renderRoutes(routes(settled), PATH);
    expect(container).toBeEmptyDOMElement();
  });

  it("recovers rather than dead-ending when it loses the race", async () => {
    // Another tab started one first. The user must be left able to act — the
    // page-level proof that the refetch turns this into the link lives in
    // MyWorkPage.test.tsx, where a `useCashAdvances` subscriber exists for the
    // invalidation to reach.
    stubFetch({
      "POST /api/v1/reimbursement/cash-advances/41/liquidate": () => ({
        status: 409,
        body: {
          error: {
            code: "reimb_liquidation_exists",
            message: "This cash advance already has a liquidation.",
            details: [{ claim_id: 88, ref_no: "LQ-2026-0001" }],
          },
        },
      }),
    });
    renderRoutes(routes(), PATH);

    const button = await screen.findByRole("button", {
      name: "Liquidate this advance",
    });
    await userEvent.click(button);
    await waitFor(() => expect(button).not.toBeDisabled());
    // And it did NOT navigate to a claim that is not theirs.
    expect(screen.queryByText("Claim page")).not.toBeInTheDocument();
  });
});
