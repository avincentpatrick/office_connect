import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expectNoA11yViolations } from "../../test/a11y";
import { renderRoutes, stubFetch } from "../../test/harness";
import { makeClaimQueue, makeQueueItem } from "../../test/reimb-fixtures";
import { ClaimQueuePage } from "./ClaimQueuePage";

const ROUTES = [{ path: "/reimbursement/queue", element: <ClaimQueuePage /> }];

// Exact-URL keys, because the harness throws on an unstubbed request: each of
// these IS the assertion that the filter row builds the query string the API
// expects, and a typo shows up as a failure rather than as a silent no-op.
const ALL = "GET /api/v1/reimbursement/claims";
const OVERDUE = "GET /api/v1/reimbursement/claims?external_over=true";
const RETURNED = "GET /api/v1/reimbursement/claims?status=fms_returned";

afterEach(() => vi.unstubAllGlobals());

describe("ClaimQueuePage", () => {
  it("lists claims FMS is holding, with the working-day count on the row", async () => {
    stubFetch({ [ALL]: () => ({ body: makeClaimQueue() }) });
    const { container } = renderRoutes(ROUTES, "/reimbursement/queue");

    expect(
      await screen.findByRole("link", {
        name: /RB-2026-0001 — Regional immunization review/,
      }),
    ).toHaveAttribute("href", "/reimbursement/claims/7");
    // The traveller leads the meta line: this list mixes them, and My Work
    // never has to say whose claim it is.
    expect(
      screen.getByText(/Maria Santos · Holder: FMS · 4 working days with FMS/),
    ).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it("wears the chase chip when the server says a claim is overdue with FMS", async () => {
    // `external_followup` is the SERVER's verdict — it counted Manila working
    // days off the holiday calendar. The page never re-derives it from
    // `days_with_fms`, so this fixture deliberately disagrees with itself.
    stubFetch({
      [ALL]: () => ({
        body: makeClaimQueue({
          items: [makeQueueItem({ days_with_fms: 3, external_followup: true })],
        }),
      }),
    });
    renderRoutes(ROUTES, "/reimbursement/queue");
    expect(await screen.findByText("Chase FMS")).toBeInTheDocument();
  });

  it("asks the server for the >N-working-day filter when that view is chosen", async () => {
    const fetchSpy = stubFetch({
      [ALL]: () => ({ body: makeClaimQueue() }),
      [OVERDUE]: () => ({
        body: makeClaimQueue({
          items: [makeQueueItem({ days_with_fms: 14, external_followup: true })],
        }),
      }),
    });
    renderRoutes(ROUTES, "/reimbursement/queue");
    await screen.findByRole("link", { name: /RB-2026-0001/ });

    await userEvent.selectOptions(screen.getByLabelText("Show"), "external_over");
    expect(await screen.findByText("Chase FMS")).toBeInTheDocument();
    const urls = fetchSpy.mock.calls.map((call) => String(call[0]));
    expect(urls).toContain("/api/v1/reimbursement/claims?external_over=true");
  });

  it("filters by status without sending the follow-up flag", async () => {
    const fetchSpy = stubFetch({
      [ALL]: () => ({ body: makeClaimQueue() }),
      [RETURNED]: () => ({
        body: makeClaimQueue({
          items: [
            makeQueueItem({
              id: 9,
              ref_no: "RB-2026-0009",
              status: "fms_returned",
              status_label: "FMS Returned",
              next_action: "Relay FMS comments",
              holder_kind: "user",
              holder_display: "Ana Reyes",
              days_with_fms: null,
            }),
          ],
        }),
      }),
    });
    renderRoutes(ROUTES, "/reimbursement/queue");
    await screen.findByRole("link", { name: /RB-2026-0001/ });

    await userEvent.selectOptions(screen.getByLabelText("Show"), "fms_returned");
    expect(await screen.findByText("FMS Returned")).toBeInTheDocument();
    // No FMS clock on a claim FMS has handed back — the row falls back to
    // days-in-state rather than printing a 0 that would read as "just arrived".
    expect(screen.getByText(/2 days in this step/)).toBeInTheDocument();
    const urls = fetchSpy.mock.calls.map((call) => String(call[0]));
    expect(urls.every((url) => !url.includes("external_over"))).toBe(true);
  });

  it("says how much it is hiding when the queue pages", async () => {
    stubFetch({ [ALL]: () => ({ body: makeClaimQueue({ total: 214 }) }) });
    renderRoutes(ROUTES, "/reimbursement/queue");
    expect(
      await screen.findByText("Showing 1 of 214 claims."),
    ).toBeInTheDocument();
  });

  it("names the follow-up threshold in that view's empty state", async () => {
    stubFetch({
      [ALL]: () => ({ body: makeClaimQueue() }),
      [OVERDUE]: () => ({
        body: makeClaimQueue({ items: [], total: 0, followup_working_days: 10 }),
      }),
    });
    renderRoutes(ROUTES, "/reimbursement/queue");
    await screen.findByRole("link", { name: /RB-2026-0001/ });

    await userEvent.selectOptions(screen.getByLabelText("Show"), "external_over");
    expect(
      await screen.findByText(
        "No claim has been with FMS longer than 10 working days.",
      ),
    ).toBeInTheDocument();
  });

  it("renders the server's own refusal for an actor who oversees nobody", async () => {
    // The queue lists OTHER people's claims, so a plain traveller gets a 403.
    // Its message names My Work as the surface that does answer their question;
    // the page must not paraphrase it into a second copy to keep true.
    stubFetch({
      [ALL]: () => ({
        status: 403,
        body: {
          error: {
            code: "reimb_queue_not_permitted",
            message:
              "This queue shows other people's claims, so it is for approvers and the Admin Officer. Your own claims are on My Work.",
          },
        },
      }),
    });
    const { container } = renderRoutes(ROUTES, "/reimbursement/queue");

    expect(
      await screen.findByText("This queue is not yours to see"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Your own claims are on My Work/),
    ).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });
});
