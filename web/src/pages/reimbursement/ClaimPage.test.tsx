import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expectNoA11yViolations } from "../../test/a11y";
import { renderRoutes, stubFetch } from "../../test/harness";
import {
  RETURN_REASONS,
  awaitingApproval,
  completeClaim,
  makeChecklistSummary,
  makeTimeline,
} from "../../test/reimb-fixtures";
import { ClaimPage } from "./ClaimPage";

const ROUTES = [{ path: "/reimbursement/claims/:claimId", element: <ClaimPage /> }];
const PATH = "/reimbursement/claims/7";

const CLAIM = "GET /api/v1/reimbursement/claims/7";
const TIMELINE = "GET /api/v1/reimbursement/claims/7/timeline";
const REASONS = "GET /api/v1/reimbursement/return-reasons";
const APPROVE = "POST /api/v1/reimbursement/claims/7/approve";
const RETURN = "POST /api/v1/reimbursement/claims/7/return";

/** The reads every render of this page performs. */
function reads(claim = awaitingApproval(), timeline = makeTimeline()) {
  return {
    [CLAIM]: () => ({ body: claim }),
    [TIMELINE]: () => ({ body: timeline }),
    [REASONS]: () => ({ body: RETURN_REASONS }),
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("ClaimPage — the approver surface", () => {
  it("renders the decision bar from the server's action set", async () => {
    stubFetch(reads());
    const { container } = renderRoutes(ROUTES, PATH);

    expect(
      await screen.findByRole("button", { name: "Approve" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Return" })).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it("shows NO decision bar when the server offers no actions", async () => {
    // Same claim, same status — the only difference is whose eyes. A claimant
    // watching their own claim at a gate must never see an Approve button.
    stubFetch(reads(awaitingApproval({ available_actions: [] })));
    renderRoutes(ROUTES, PATH);

    await screen.findByText("Regional immunization review");
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Return" })).not.toBeInTheDocument();
  });

  it("labels the approve action for where the claim actually is", async () => {
    stubFetch(
      reads(
        awaitingApproval({ status: "admin_review", status_label: "Admin Review" }),
      ),
    );
    renderRoutes(ROUTES, PATH);

    // Same endpoint, different rung of the chain — the label carries the
    // meaning so an Admin Officer knows the packet is leaving the bureau.
    expect(
      await screen.findByRole("button", { name: "Approve & hand to FMS" }),
    ).toBeInTheDocument();
  });

  it("approves through a confirm dialog and refreshes the claim", async () => {
    const user = userEvent.setup();
    let claim = awaitingApproval();
    const spy = stubFetch({
      [CLAIM]: () => ({ body: claim }),
      [TIMELINE]: () => ({ body: makeTimeline() }),
      [REASONS]: () => ({ body: RETURN_REASONS }),
      [APPROVE]: () => {
        claim = awaitingApproval({
          status: "admin_review",
          status_label: "Admin Review",
          available_actions: [],
          row_version: 3,
        });
        return { body: claim };
      },
    });
    renderRoutes(ROUTES, PATH);

    await user.click(await screen.findByRole("button", { name: "Approve" }));
    await user.click(
      await screen.findByRole("button", { name: "Approve", hidden: false }),
    );

    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument(),
    );
    const approveCall = spy.mock.calls.find(([url]) =>
      String(url).endsWith("/approve"),
    );
    expect(JSON.parse(String(approveCall?.[1]?.body))).toEqual({
      expected_version: 2, // the CAS token the page was rendered from
    });
  });

  it("keeps the return dialog open when no reason is picked", async () => {
    const user = userEvent.setup();
    const spy = stubFetch(reads());
    renderRoutes(ROUTES, PATH);

    await user.click(await screen.findByRole("button", { name: "Return" }));
    await user.type(
      await screen.findByLabelText("What needs fixing?"),
      "Attach the receipt.",
    );
    await user.click(screen.getByRole("button", { name: "Return claim" }));

    expect(
      await screen.findByText("Select at least one reason for returning this claim."),
    ).toBeInTheDocument();
    // The dialog survives, the typed comment survives, and nothing was sent.
    expect(screen.getByRole("dialog", { name: "Return this claim" })).toBeInTheDocument();
    expect(screen.getByLabelText("What needs fixing?")).toHaveValue(
      "Attach the receipt.",
    );
    expect(spy.mock.calls.some(([url]) => String(url).endsWith("/return"))).toBe(false);
  });

  it("requires a comment as well as a reason", async () => {
    const user = userEvent.setup();
    const spy = stubFetch(reads());
    renderRoutes(ROUTES, PATH);

    await user.click(await screen.findByRole("button", { name: "Return" }));
    await user.click(
      await screen.findByRole("checkbox", { name: "Missing official receipt" }),
    );
    await user.click(screen.getByRole("button", { name: "Return claim" }));

    expect(
      await screen.findByText(/Explain what needs fixing/),
    ).toBeInTheDocument();
    expect(spy.mock.calls.some(([url]) => String(url).endsWith("/return"))).toBe(false);
  });

  it("sends the picked reason ids and the comment", async () => {
    const user = userEvent.setup();
    let claim = awaitingApproval();
    const spy = stubFetch({
      [CLAIM]: () => ({ body: claim }),
      [TIMELINE]: () => ({ body: makeTimeline() }),
      [REASONS]: () => ({ body: RETURN_REASONS }),
      [RETURN]: () => {
        claim = awaitingApproval({
          status: "returned",
          status_label: "Returned",
          available_actions: [],
        });
        return { body: claim };
      },
    });
    renderRoutes(ROUTES, PATH);

    await user.click(await screen.findByRole("button", { name: "Return" }));
    await user.click(
      await screen.findByRole("checkbox", { name: "Missing official receipt" }),
    );
    await user.type(
      screen.getByLabelText("What needs fixing?"),
      "Attach the official receipt.",
    );
    await user.click(screen.getByRole("button", { name: "Return claim" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    const returnCall = spy.mock.calls.find(([url]) => String(url).endsWith("/return"));
    expect(JSON.parse(String(returnCall?.[1]?.body))).toEqual({
      comment: "Attach the official receipt.",
      reason_ids: [1],
      expected_version: 2,
    });
  });

  it("surfaces a 409 and keeps the approver on a page it can refresh", async () => {
    const user = userEvent.setup();
    stubFetch({
      ...reads(),
      [APPROVE]: () => ({
        status: 409,
        body: {
          error: {
            code: "stale_workflow_version",
            message: "This claim changed while you were looking at it.",
          },
        },
      }),
    });
    renderRoutes(ROUTES, PATH);

    await user.click(await screen.findByRole("button", { name: "Approve" }));
    await user.click(await screen.findByRole("button", { name: "Approve" }));

    expect(
      await screen.findByText("This claim changed while you were looking at it."),
    ).toBeInTheDocument();
  });
});

describe("ClaimPage — the tracker", () => {
  it("renders the journey with return reasons under the bounce", async () => {
    stubFetch(
      reads(
        awaitingApproval(),
        makeTimeline([
          {},
          {
            id: 2,
            from_status: "division_approval",
            from_status_label: "For Approval",
            to_status: "returned",
            to_status_label: "Returned",
            actor_display: "Maria Santos",
            note: "Attach the official receipt.",
            reasons: RETURN_REASONS,
          },
        ]),
      ),
    );
    const { container } = renderRoutes(ROUTES, PATH);

    // The note rides the event verbatim (spec §12).
    expect(
      await screen.findByText(/Returned — Attach the official receipt\./),
    ).toBeInTheDocument();
    expect(screen.getByText("Missing official receipt")).toBeInTheDocument();
    expect(screen.getByText("Per-diem miscomputed")).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it("degrades to a message when the tracker cannot load — the record still renders", async () => {
    stubFetch({
      [CLAIM]: () => ({ body: awaitingApproval() }),
      [REASONS]: () => ({ body: RETURN_REASONS }),
      [TIMELINE]: () => ({
        status: 500,
        body: { error: { code: "internal_error", message: "boom" } },
      }),
    });
    renderRoutes(ROUTES, PATH);

    expect(await screen.findByText("Regional immunization review")).toBeInTheDocument();
    expect(
      await screen.findByText("Nothing has happened on this claim yet."),
    ).toBeInTheDocument();
  });
});

describe("ClaimPage — the wizard resume redirect", () => {
  it("does NOT drag a reviewer into a stranger's wizard", async () => {
    // A returned claim opened by someone who cannot resubmit it: render the
    // record, never the claimant's form (the server's action set decides).
    stubFetch(
      reads(
        completeClaim({
          status: "returned",
          status_label: "Returned",
          available_actions: [],
          ref_no: "RB-2026-0001",
        }),
      ),
    );
    renderRoutes(ROUTES, PATH);

    expect(
      await screen.findByRole("heading", { name: /RB-2026-0001 — Travel claim/ }),
    ).toBeInTheDocument();
  });
});

describe("ClaimPage — the approver's auto-check callouts (spec §9.4)", () => {
  const FLAG = {
    catalog_id: 5,
    code: "RER-46",
    label: "Reimbursement Expense Receipt for taxi/no-receipt fares",
    check_type: "amount_threshold",
    reason: "amount_over_threshold",
    message:
      "₱500.00 is over the ₱300.00 limit set by 'receipts.cenrr_max'. Attach the receipt the higher amount requires.",
    detail: {},
    remedy: "require_item:RER",
  };

  it("renders an amber callout ABOVE the decision buttons and still offers approve", async () => {
    stubFetch(
      reads(
        awaitingApproval({
          checklist: makeChecklistSummary({
            required_total: 2,
            required_done: 2,
            flags: [FLAG],
          }),
        }),
      ),
    );
    renderRoutes(ROUTES, PATH);

    const callout = await screen.findByRole("region", {
      name: /1 automatic check flagged/,
    });
    expect(screen.getByText(new RegExp(FLAG.label))).toBeInTheDocument();

    // A flag never blocks: approve stays on offer (spec §5.3).
    const approve = screen.getByRole("button", { name: "Approve" });
    expect(approve).toBeInTheDocument();
    // …and the callout sits above it.
    expect(
      callout.compareDocumentPosition(approve) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("states the consequence of approving past a flag before the tap", async () => {
    stubFetch(
      reads(
        awaitingApproval({
          checklist: makeChecklistSummary({
            required_total: 1,
            required_done: 1,
            flags: [FLAG],
          }),
        }),
      ),
    );
    renderRoutes(ROUTES, PATH);
    await userEvent.click(await screen.findByRole("button", { name: "Approve" }));
    // Scoped to the sheet: the callout says it too, and saying it in both
    // places is the point — inform on the page, re-state before the commit.
    const sheet = await screen.findByRole("dialog");
    expect(
      within(sheet).getByText(/recorded against your name/),
    ).toBeInTheDocument();
  });

  it("explains the missing Approve button rather than leaving a silent gap", async () => {
    // The server withholds `approve` when a required document is missing; a
    // vanished button with no explanation is the failure this prevents.
    stubFetch(
      reads(
        awaitingApproval({
          available_actions: ["return"],
          checklist: makeChecklistSummary({ required_total: 2, required_done: 0 }),
        }),
      ),
    );
    renderRoutes(ROUTES, PATH);

    expect(
      await screen.findByRole("region", { name: /Required documents are missing/ }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    // The approver's remedy is untouched.
    expect(screen.getByRole("button", { name: "Return" })).toBeInTheDocument();
  });

  it("does not steal focus the way an ErrorSummary would", async () => {
    stubFetch(
      reads(
        awaitingApproval({
          checklist: makeChecklistSummary({
            required_total: 1,
            required_done: 1,
            flags: [FLAG],
          }),
        }),
      ),
    );
    renderRoutes(ROUTES, PATH);
    const callout = await screen.findByRole("region", {
      name: /1 automatic check flagged/,
    });
    expect(callout).not.toHaveFocus();
    await expectNoA11yViolations(document.body);
  });
});
