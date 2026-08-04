import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expectNoA11yViolations } from "../../test/a11y";
import { renderRoutes, stubFetch } from "../../test/harness";
import { makeCashAdvance } from "../../test/reimb-fixtures";
import { CashAdvancesPage } from "./CashAdvancesPage";

const ROUTES = [
  { path: "/reimbursement/cash-advances", element: <CashAdvancesPage /> },
];
const PATH = "/reimbursement/cash-advances";
const LIST = "GET /api/v1/reimbursement/cash-advances";
const CREATE = "POST /api/v1/reimbursement/cash-advances";

afterEach(() => vi.unstubAllGlobals());

describe("CashAdvancesPage", () => {
  it("renders each advance with its server-derived countdown", async () => {
    stubFetch({
      [LIST]: () => ({ body: { items: [makeCashAdvance()] } }),
    });
    const { container } = renderRoutes(ROUTES, PATH);

    expect(await screen.findByText("DV-2026-0042")).toBeInTheDocument();
    expect(screen.getByText("₱5,000.00")).toBeInTheDocument();
    // The countdown states its facts in TEXT, not only in the ring (§6).
    expect(screen.getByText("On track")).toBeInTheDocument();
    expect(screen.getByText(/12 days left · due Aug 2, 2026/)).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it("shows the COA warning only once the server says it applies", async () => {
    stubFetch({
      [LIST]: () => ({
        body: {
          items: [
            makeCashAdvance({
              days_remaining: -4,
              deadline_state: "overdue",
              status: "overdue",
              status_label: "Overdue",
              overdue_note:
                "Unliquidated advances may accrue 6% interest and be deducted from your salary.",
            }),
          ],
        },
      }),
    });
    renderRoutes(ROUTES, PATH);

    expect(await screen.findByText("Overdue")).toBeInTheDocument();
    expect(screen.getByText(/4 days overdue/)).toBeInTheDocument();
    expect(screen.getByText(/6% interest/)).toBeInTheDocument();
  });

  it("says 'not started' for an advance whose trip has not happened", async () => {
    // A full ring would read as plenty of time and an empty one as overdue.
    stubFetch({
      [LIST]: () => ({
        body: {
          items: [
            makeCashAdvance({
              date_return: null,
              deadline_date: null,
              deadline_basis: null,
              days_remaining: null,
              deadline_state: null,
            }),
          ],
        },
      }),
    });
    renderRoutes(ROUTES, PATH);
    expect(
      await screen.findByText("No liquidation deadline yet"),
    ).toBeInTheDocument();
  });

  it("records an advance and refreshes the list", async () => {
    const user = userEvent.setup();
    let created = false;
    stubFetch({
      [LIST]: () => ({ body: { items: created ? [makeCashAdvance()] : [] } }),
      [CREATE]: () => {
        created = true;
        return { status: 201, body: makeCashAdvance() };
      },
    });
    renderRoutes(ROUTES, PATH);

    await user.click(
      await screen.findByRole("button", { name: "Record a cash advance" }),
    );
    await user.type(await screen.findByLabelText(/Claimant staff ID/), "3");
    await user.type(screen.getByLabelText(/^Amount/), "5000.00");
    await user.click(screen.getByRole("button", { name: "Record advance" }));

    expect(await screen.findByText("DV-2026-0042")).toBeInTheDocument();
  });

  it("renders the §89 refusal as a callout, not a field error", async () => {
    // The 409 names ANOTHER advance, so anchoring it to an input would send
    // the user to fix the wrong thing.
    const user = userEvent.setup();
    stubFetch({
      [LIST]: () => ({ body: { items: [] } }),
      [CREATE]: () => ({
        status: 409,
        body: {
          error: {
            code: "reimb_cash_advance_unliquidated",
            message:
              "This claimant still has an unliquidated cash advance — DV-FIRST (due 2026-08-02). PD 1445 §89 allows only one at a time.",
          },
        },
      }),
    });
    renderRoutes(ROUTES, PATH);

    await user.click(
      await screen.findByRole("button", { name: "Record a cash advance" }),
    );
    await user.type(await screen.findByLabelText(/Claimant staff ID/), "3");
    await user.type(screen.getByLabelText(/^Amount/), "5000.00");
    await user.click(screen.getByRole("button", { name: "Record advance" }));

    expect(await screen.findByText(/DV-FIRST/)).toBeInTheDocument();
    expect(screen.getByText(/PD 1445 §89/)).toBeInTheDocument();
    // The dialog stays OPEN with the user's work intact (FormDialog contract).
    expect(
      screen.getByRole("button", { name: "Record advance" }),
    ).toBeInTheDocument();
  });

  it("validates shape client-side without duplicating a business rule", async () => {
    const user = userEvent.setup();
    stubFetch({ [LIST]: () => ({ body: { items: [] } }) });
    renderRoutes(ROUTES, PATH);

    await user.click(
      await screen.findByRole("button", { name: "Record a cash advance" }),
    );
    // Wait for the dialog to finish mounting before submitting — Radix installs
    // focus guards and a scroll lock on open, and a click that lands mid-mount
    // is dispatched at a form that is not listening yet.
    await screen.findByLabelText(/Claimant staff ID/);
    await user.click(screen.getByRole("button", { name: "Record advance" }));

    expect(
      await screen.findByText("Enter the claimant's staff ID"),
    ).toBeInTheDocument();
    expect(screen.getByText("Enter the advance amount")).toBeInTheDocument();
  });

  it("explains a 403 instead of rendering a blank page", async () => {
    stubFetch({
      [LIST]: () => ({
        status: 403,
        body: {
          error: {
            code: "reimb_not_claim_owner",
            message: "Only the claimant may do this.",
          },
        },
      }),
    });
    renderRoutes(ROUTES, PATH);
    await waitFor(() =>
      expect(
        screen.getByText("You cannot view these cash advances"),
      ).toBeInTheDocument(),
    );
  });
});
