import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { expectNoA11yViolations } from "../../test/a11y";
import { renderRoutes, stubFetch } from "../../test/harness";
import { makeMyWork } from "../../test/reimb-fixtures";
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
});
