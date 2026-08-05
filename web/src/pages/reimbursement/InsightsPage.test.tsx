import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expectNoA11yViolations } from "../../test/a11y";
import { renderRoutes, stubFetch } from "../../test/harness";
import { makeReasonRank, makeReturnInsights } from "../../test/reimb-fixtures";
import { InsightsPage } from "./InsightsPage";

const ROUTES = [{ path: "/reimbursement/insights", element: <InsightsPage /> }];

// Exact-URL keys: the harness throws on an unstubbed request, so these ARE the
// assertion that the page asks for the sibling `/insights/...` segment and not
// `/claims/insights` — the literal FastAPI would read as a claim id.
const RANKING = "GET /api/v1/reimbursement/insights/return-reasons";
const PROMOTE = "POST /api/v1/reimbursement/insights/return-reasons/1/promote";
const DEMOTE = "POST /api/v1/reimbursement/insights/return-reasons/1/demote";

afterEach(() => vi.unstubAllGlobals());

describe("InsightsPage", () => {
  it("ranks the reasons with every number in text", async () => {
    stubFetch({ [RANKING]: () => ({ body: makeReturnInsights() }) });
    const { container } = renderRoutes(ROUTES, "/reimbursement/insights");

    expect(
      await screen.findByText("Missing official receipt"),
    ).toBeInTheDocument();
    expect(screen.getByText("12 returns")).toBeInTheDocument();
    expect(screen.getByText("Up from 7")).toBeInTheDocument();
    expect(screen.getByText("Down from 9")).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it("quotes the SERVER's window in the summary, never a literal 90", async () => {
    stubFetch({
      [RANKING]: () => ({
        body: makeReturnInsights({
          window_days: 30,
          period_start: "2026-07-08",
          total_returns: 4,
        }),
      }),
    });
    renderRoutes(ROUTES, "/reimbursement/insights");

    expect(
      await screen.findByText(/4 returns in the last 30 days, since Jul 8, 2026/),
    ).toBeInTheDocument();
  });

  it("never turns a count into a rate", async () => {
    // Spec §13's return RATE is Stage H — it needs a denominator (submissions)
    // this surface does not compute, and half a rate is worse than none.
    stubFetch({ [RANKING]: () => ({ body: makeReturnInsights() }) });
    const { container } = renderRoutes(ROUTES, "/reimbursement/insights");

    await screen.findByText("Missing official receipt");
    expect(container.textContent).not.toMatch(/%/);
  });

  it("promotes a reason and refreshes the taxonomy the WIZARD reads", async () => {
    // The acceptance line: a promotion has to reach the claimant with no
    // deploy, and the invalidate below is the entire mechanism. Refreshing only
    // this page would leave the button looking applied while changing nothing.
    const promoted = makeReturnInsights({
      items: [makeReasonRank({ promoted: true })],
    });
    stubFetch({
      [RANKING]: () => ({ body: makeReturnInsights() }),
      [PROMOTE]: () => ({ body: promoted }),
    });
    const { queryClient } = renderRoutes(ROUTES, "/reimbursement/insights");
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");

    await userEvent.click(
      await screen.findByRole("button", { name: /Promote to pre-check.*Missing official receipt/ }),
    );

    expect(await screen.findByText(/Shown as a warning at step 5/)).toBeInTheDocument();
    await waitFor(() =>
      expect(invalidate).toHaveBeenCalledWith({
        queryKey: ["reimbursement", "return-reasons"],
      }),
    );
  });

  it("offers Stop warning on a reason that is already promoted", async () => {
    stubFetch({
      [RANKING]: () => ({
        body: makeReturnInsights({ items: [makeReasonRank({ promoted: true })] }),
      }),
      [DEMOTE]: () => ({
        body: makeReturnInsights({ items: [makeReasonRank({ promoted: false })] }),
      }),
    });
    renderRoutes(ROUTES, "/reimbursement/insights");

    await userEvent.click(
      await screen.findByRole("button", { name: /Stop warning/ }),
    );
    expect(
      await screen.findByRole("button", { name: /Promote to pre-check/ }),
    ).toBeInTheDocument();
  });

  it("offers no promote control at all when the server says you may not", async () => {
    // R-4-screens' doctrine: never render a button certain to be refused. The
    // rule is the SERVER's `can_promote`, never a role read on the client.
    stubFetch({
      [RANKING]: () => ({ body: makeReturnInsights({ can_promote: false }) }),
    });
    renderRoutes(ROUTES, "/reimbursement/insights");

    await screen.findByText("Missing official receipt");
    expect(
      screen.queryByRole("button", { name: /Promote to pre-check/ }),
    ).not.toBeInTheDocument();
  });

  it("disables promotion on a retired reason rather than letting it 422", async () => {
    stubFetch({
      [RANKING]: () => ({
        body: makeReturnInsights({
          items: [makeReasonRank({ promotable: false })],
        }),
      }),
    });
    renderRoutes(ROUTES, "/reimbursement/insights");

    expect(
      await screen.findByRole("button", { name: /Promote to pre-check/ }),
    ).toBeDisabled();
  });

  it("renders a 403 as the server's own sentence, not a blank page", async () => {
    // The admin-surface doctrine, fourth instance — and here the refusal is a
    // PRIVACY boundary: an empty ranking would assert "nothing comes back for
    // any reason", which is false.
    stubFetch({
      [RANKING]: () => ({
        status: 403,
        body: {
          error: {
            code: "reimb_insights_not_permitted",
            message:
              "Insights summarises why other people's claims were returned, so it is for approvers and the Admin Officer.",
          },
        },
      }),
    });
    renderRoutes(ROUTES, "/reimbursement/insights");

    expect(
      await screen.findByText("Insights is not yours to see"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/summarises why other people's claims were returned/),
    ).toBeInTheDocument();
  });

  it("explains what the surface is for when nothing has come back yet", async () => {
    stubFetch({
      [RANKING]: () => ({
        body: makeReturnInsights({ items: [], total_returns: 0 }),
      }),
    });
    renderRoutes(ROUTES, "/reimbursement/insights");

    expect(
      await screen.findByText("No claims have come back yet"),
    ).toBeInTheDocument();
  });
});
