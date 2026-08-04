import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expectNoA11yViolations } from "../../test/a11y";
import { renderRoutes, stubFetch } from "../../test/harness";
import {
  RETURN_REASONS,
  awaitingSettlement,
  completeClaim,
  makeCashAdvance,
  makeSettledAdvance,
  makeTimeline,
  makeTotals,
  settledOverAdvance,
} from "../../test/reimb-fixtures";
import { ClaimPage } from "./ClaimPage";

const ROUTES = [
  { path: "/reimbursement/claims/:claimId", element: <ClaimPage /> },
  // The spawn lands on a DRAFT, and ClaimPage redirects an editable claim into
  // the wizard. Stubbed here so the assertion is about where the traveller
  // actually ends up rather than about a 404 the harness invented.
  {
    path: "/reimbursement/claims/:claimId/:step",
    element: <p>Wizard step</p>,
  },
];
const PATH = "/reimbursement/claims/7";

const CLAIM = "GET /api/v1/reimbursement/claims/7";
const TIMELINE = "GET /api/v1/reimbursement/claims/7/timeline";
const REASONS = "GET /api/v1/reimbursement/return-reasons";
const SETTLE = "POST /api/v1/reimbursement/claims/7/settle";
const SPAWN = "POST /api/v1/reimbursement/claims/7/spawn-reimbursement";

function reads(claim = awaitingSettlement()) {
  return {
    [CLAIM]: () => ({ body: claim }),
    [TIMELINE]: () => ({ body: makeTimeline() }),
    [REASONS]: () => ({ body: RETURN_REASONS }),
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("Recording a settlement", () => {
  it("offers Record settlement, never a bare Approve", async () => {
    // The server rewrote the verb because clearing this gate now has to carry
    // the money. A rendered "Approve" here would be a button certain to 409.
    stubFetch(reads());
    const { container } = renderRoutes(ROUTES, PATH);

    expect(
      await screen.findByRole("button", { name: "Record settlement" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /^Approve/ }),
    ).not.toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it("asks for the official receipt when money is coming back", async () => {
    stubFetch(reads());
    renderRoutes(ROUTES, PATH);
    await userEvent.click(
      await screen.findByRole("button", { name: "Record settlement" }),
    );

    // The server's figure, displayed — never a subtraction done here.
    expect(
      await screen.findByText(/₱1,250.00 is refundable/),
    ).toBeInTheDocument();
    expect(
      await screen.findByLabelText(/Official receipt number/),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText(/Official receipt date/),
    ).toBeInTheDocument();
  });

  it("does NOT ask for a receipt when nothing came back", async () => {
    // An OR on a settlement that refunded nothing is a receipt for a payment
    // that never happened — the server refuses one, so the form must not
    // invite it (never render an input whose only outcome is a 422).
    stubFetch(
      reads(
        awaitingSettlement({
          totals: makeTotals({
            advance: "6000.00",
            to_reimburse: "750.00",
            to_refund: "0.00",
          }),
        }),
      ),
    );
    renderRoutes(ROUTES, PATH);
    await userEvent.click(
      await screen.findByRole("button", { name: "Record settlement" }),
    );

    expect(await screen.findByText(/No receipt to record/)).toBeInTheDocument();
    expect(
      screen.queryByLabelText(/Official receipt number/),
    ).not.toBeInTheDocument();
  });

  it("posts the receipt and the echoed figure, and closes the advance", async () => {
    let sent: unknown;
    stubFetch({
      ...reads(),
      [SETTLE]: (init?: RequestInit) => {
        sent = JSON.parse(String(init?.body ?? "{}"));
        return {
          body: completeClaim({
            ref_no: "LQ-2026-0001",
            kind: "liquidation",
            status: "settled",
            status_label: "Settled",
            available_actions: [],
            cash_advance: makeSettledAdvance(),
          }),
        };
      },
    });
    renderRoutes(ROUTES, PATH);
    await userEvent.click(
      await screen.findByRole("button", { name: "Record settlement" }),
    );
    await userEvent.type(
      await screen.findByLabelText(/Official receipt number/),
      "OR-2026-1234",
    );
    await userEvent.type(
      screen.getByLabelText(/Official receipt date/),
      "2026-07-09",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Record and close" }),
    );

    await waitFor(() =>
      expect(screen.getByText(/Settled — excess refunded/)).toBeInTheDocument(),
    );
    expect(sent).toMatchObject({
      or_no: "OR-2026-1234",
      or_date: "2026-07-09",
      // Echoed back verbatim so a stale screen is caught — never re-derived.
      refund_amount: "1250.00",
    });
  });

  it("keeps the dialog open and explains a stale screen", async () => {
    stubFetch({
      ...reads(),
      [SETTLE]: () => ({
        status: 422,
        body: {
          error: {
            code: "reimb_refund_amount_mismatch",
            message:
              "The refund on this liquidation is ₱1,500.00, not ₱1,250.00 — your screen is out of date. Reload and record it again.",
          },
        },
      }),
    });
    renderRoutes(ROUTES, PATH);
    await userEvent.click(
      await screen.findByRole("button", { name: "Record settlement" }),
    );
    await userEvent.type(
      await screen.findByLabelText(/Official receipt number/),
      "OR-2026-1234",
    );
    await userEvent.type(
      screen.getByLabelText(/Official receipt date/),
      "2026-07-09",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Record and close" }),
    );

    expect(
      await screen.findByText(/your screen is out of date/),
    ).toBeInTheDocument();
    // The operator's typing survives — that is the whole reason this is a
    // FormDialog and not a ConfirmDialog.
    expect(screen.getByLabelText(/Official receipt number/)).toHaveValue(
      "OR-2026-1234",
    );
  });
});

describe("A settled liquidation", () => {
  it("states the refund and its receipt, and offers nothing", async () => {
    stubFetch(
      reads(
        completeClaim({
          ref_no: "LQ-2026-0001",
          kind: "liquidation",
          status: "settled",
          status_label: "Settled",
          available_actions: [],
          cash_advance: makeSettledAdvance(),
        }),
      ),
    );
    const { container } = renderRoutes(ROUTES, PATH);

    expect(
      await screen.findByText(/Settled — excess refunded/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/against official receipt OR-2026-1234/),
    ).toBeInTheDocument();
    // A closed advance is not counting down to anything.
    expect(screen.queryByText(/days left/)).not.toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it("offers the traveller one tap for an over-advance", async () => {
    const draft = completeClaim({
      id: 9,
      ref_no: null,
      kind: "reimbursement",
      status: "draft",
      status_label: "Draft",
      available_actions: ["submit", "cancel"],
    });
    stubFetch({
      ...reads(settledOverAdvance()),
      [SPAWN]: () => ({ status: 201, body: draft }),
      // The spawn navigates to the new draft, which resumes the wizard.
      "GET /api/v1/reimbursement/claims/9": () => ({ body: draft }),
      "GET /api/v1/reimbursement/claims/9/timeline": () => ({ body: [] }),
      "GET /api/v1/reimbursement/claims/9/checklist": () => ({
        body: { items: [], status: {} },
      }),
    });
    const { router } = renderRoutes(ROUTES, PATH);

    expect(await screen.findByText(/₱750.00 is due you/)).toBeInTheDocument();
    // Honest copy: the spawn is a pre-filled DRAFT, not a finished claim — the
    // traveller still walks it through the wizard.
    await userEvent.click(
      screen.getByRole("button", { name: /Start your claim for ₱750.00/ }),
    );

    // Straight into the new claim — and because a spawn is editable, on into
    // the wizard, exactly where the traveller has work left to do.
    await waitFor(() =>
      expect(router.state.location.pathname).toMatch(
        /^\/reimbursement\/claims\/9/,
      ),
    );
    expect(await screen.findByText("Wizard step")).toBeInTheDocument();
  });

  it("shows the claim already filed instead of a second button", async () => {
    stubFetch(
      reads(
        settledOverAdvance({
          // The server withholds `spawn` once one exists — this is the client
          // rendering the server's answer, not deciding for itself.
          available_actions: [],
          spawned_claim: {
            claim_id: 9,
            ref_no: "RB-2026-0055",
            status: "draft",
            status_label: "Draft",
          },
        }),
      ),
    );
    renderRoutes(ROUTES, PATH);

    expect(await screen.findByText(/RB-2026-0055/)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Start your claim/ }),
    ).not.toBeInTheDocument();
  });

  it("says nothing at all on an unsettled advance", async () => {
    stubFetch(
      reads(
        completeClaim({
          kind: "liquidation",
          status: "certify_b",
          status_label: "For Certification B",
          available_actions: [],
          cash_advance: makeCashAdvance(),
        }),
      ),
    );
    renderRoutes(ROUTES, PATH);

    await screen.findByText(/Cash advance|DV-2026-0042/);
    expect(screen.queryByText(/is due you/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Settled/)).not.toBeInTheDocument();
  });
});
