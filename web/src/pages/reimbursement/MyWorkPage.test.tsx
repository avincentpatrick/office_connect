import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expectNoA11yViolations } from "../../test/a11y";
import { renderRoutes, stubFetch } from "../../test/harness";
import { makeCashAdvance, makeMyWork } from "../../test/reimb-fixtures";
import { MyWorkPage } from "./MyWorkPage";

const ROUTES = [{ path: "/reimbursement", element: <MyWorkPage /> }];

afterEach(() => vi.unstubAllGlobals());

describe("MyWorkPage", () => {
  it("renders 'Waiting on you' above 'Your claims in flight' with linked rows", async () => {
    stubFetch({
      "GET /api/v1/reimbursement/my-work": () => ({ body: makeMyWork() }),
    });
    const { container } = renderRoutes(ROUTES, "/reimbursement");

    const waiting = await screen.findByRole("region", { name: "Waiting on you" });
    const flight = screen.getByRole("region", { name: "Your claims in flight" });
    expect(
      waiting.compareDocumentPosition(flight) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      screen.getByRole("link", { name: /RB-2026-0001 — Regional immunization review/ }),
    ).toHaveAttribute("href", "/reimbursement/claims/7");
    expect(screen.getByText(/Maria Santos · 2 days in this step/)).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it("shows the celebration zero-state when nothing waits on you", async () => {
    stubFetch({
      "GET /api/v1/reimbursement/my-work": () => ({
        body: makeMyWork({ waiting_on_you: [] }),
      }),
    });
    renderRoutes(ROUTES, "/reimbursement");
    expect(await screen.findByText(/Nothing waiting on you/)).toBeInTheDocument();
  });

  it("renders the module empty state when both lists are empty", async () => {
    stubFetch({
      "GET /api/v1/reimbursement/my-work": () => ({
        body: { waiting_on_you: [], in_flight: [] },
      }),
    });
    renderRoutes(ROUTES, "/reimbursement");
    expect(
      await screen.findByText("Your travel claims will appear here"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start a new claim" })).toBeInTheDocument();
  });

  it("shows live cash advances with their COA countdown between the two lists", async () => {
    // Spec §6.2: the countdown shows on every liquidation surface from CA
    // creation, and the module home is the first surface a traveller sees.
    stubFetch({
      "GET /api/v1/reimbursement/my-work": () => ({ body: makeMyWork() }),
      "GET /api/v1/reimbursement/cash-advances": () => ({
        body: { items: [makeCashAdvance({ days_remaining: 3, deadline_state: "due_soon" })] },
      }),
    });
    const { container } = renderRoutes(ROUTES, "/reimbursement");

    const advances = await screen.findByRole("region", {
      name: "Your cash advances",
    });
    const waiting = screen.getByRole("region", { name: "Waiting on you" });
    const flight = screen.getByRole("region", { name: "Your claims in flight" });
    // Below the inbox, above the tracker: an unliquidated advance IS waiting on
    // you, but it is not a claim and does not belong in a list of claim rows.
    expect(
      waiting.compareDocumentPosition(advances) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      advances.compareDocumentPosition(flight) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(screen.getByText("Due soon")).toBeInTheDocument();
    expect(screen.getByText(/3 days left/)).toBeInTheDocument();
    // R-6-liq-chain: the card counts down and now carries the ANSWER to it.
    expect(
      screen.getByRole("button", { name: "Liquidate this advance" }),
    ).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it("turns Liquidate into a link once the advance names its liquidation", async () => {
    // The page-level half of LiquidateAction's race test: a `useCashAdvances`
    // subscriber exists here, so the 409's invalidation actually refetches, and
    // the refreshed advance renders the link the button should have been.
    let listed = 0;
    stubFetch({
      "GET /api/v1/reimbursement/my-work": () => ({ body: makeMyWork() }),
      "GET /api/v1/reimbursement/cash-advances": () => {
        listed += 1;
        return {
          body: {
            items: [
              listed === 1
                ? makeCashAdvance()
                : makeCashAdvance({
                    status: "liquidation_started",
                    status_label: "Liquidation started",
                    liquidation_claim_id: 88,
                    liquidation_ref_no: "LQ-2026-0001",
                    liquidation_status: "certify_b",
                  }),
            ],
          },
        };
      },
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
    renderRoutes(ROUTES, "/reimbursement");

    await userEvent.click(
      await screen.findByRole("button", { name: "Liquidate this advance" }),
    );
    expect(
      await screen.findByRole("link", { name: "Open LQ-2026-0001" }),
    ).toHaveAttribute("href", "/reimbursement/claims/88");
  });

  it("renders no cash-advance furniture when there are none", async () => {
    // Most travellers never take an advance; an empty heading on every visit
    // would be permanent furniture reporting nothing.
    stubFetch({
      "GET /api/v1/reimbursement/my-work": () => ({ body: makeMyWork() }),
      "GET /api/v1/reimbursement/cash-advances": () => ({ body: { items: [] } }),
    });
    renderRoutes(ROUTES, "/reimbursement");
    await screen.findByRole("region", { name: "Waiting on you" });
    expect(
      screen.queryByRole("region", { name: "Your cash advances" }),
    ).not.toBeInTheDocument();
  });

  it("hides a settled advance — the clock section is about live ones", async () => {
    stubFetch({
      "GET /api/v1/reimbursement/my-work": () => ({ body: makeMyWork() }),
      "GET /api/v1/reimbursement/cash-advances": () => ({
        body: { items: [makeCashAdvance({ status: "settled", status_label: "Settled" })] },
      }),
    });
    renderRoutes(ROUTES, "/reimbursement");
    await screen.findByRole("region", { name: "Waiting on you" });
    expect(
      screen.queryByRole("region", { name: "Your cash advances" }),
    ).not.toBeInTheDocument();
  });
});
