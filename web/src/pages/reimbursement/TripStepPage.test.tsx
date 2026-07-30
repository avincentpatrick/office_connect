import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ClaimPatch } from "../../api/reimbursement";
import { renderRoutes, stubFetch } from "../../test/harness";
import { makeClaim } from "../../test/reimb-fixtures";
import { TripStepPage } from "./TripStepPage";

const ROUTES = [
  { path: "/reimbursement/claims/:claimId/trip", element: <TripStepPage /> },
  { path: "/reimbursement/claims/:claimId/itinerary", element: <p>itinerary page</p> },
];

const REGIONS = [{ region_code: "13", region_name: "NCR", cluster: "III" }];

afterEach(() => vi.unstubAllGlobals());

describe("TripStepPage", () => {
  it("blocks an empty submit with an ErrorSummary and fires no PATCH", async () => {
    const spy = stubFetch({
      "GET /api/v1/reimbursement/claims/7": () => ({ body: makeClaim() }),
      "GET /api/v1/reimbursement/regions": () => ({ body: REGIONS }),
    });
    renderRoutes(ROUTES, "/reimbursement/claims/7/trip");

    const submit = await screen.findByRole("button", { name: "Continue" });
    await userEvent.click(submit);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("There is a problem");
    expect(alert).toHaveTextContent("Enter the DPO number");
    // Inline wording identical to the summary (GOV.UK rule).
    expect(screen.getAllByText("Enter the DPO number")).toHaveLength(2);
    expect(spy.mock.calls.filter(([, init]) => init?.method === "PATCH")).toHaveLength(0);
  });

  it("saves the step on Continue (server-side save-and-return) and advances", async () => {
    let patched: ClaimPatch | null = null;
    stubFetch({
      "GET /api/v1/reimbursement/claims/7": () => ({ body: makeClaim() }),
      "GET /api/v1/reimbursement/regions": () => ({ body: REGIONS }),
      "PATCH /api/v1/reimbursement/claims/7": (init) => {
        patched = JSON.parse(String(init?.body)) as ClaimPatch;
        return {
          body: makeClaim({
            dpo_no: "DPO-1",
            dpo_date: "2026-06-20",
            purpose: "Site visit",
            destination: "Manila",
            destination_region_code: "13",
            date_depart: "2026-07-01",
            date_return: "2026-07-03",
          }),
        };
      },
    });
    renderRoutes(ROUTES, "/reimbursement/claims/7/trip");

    await userEvent.type(await screen.findByLabelText(/DPO number/), "DPO-1");
    fireEvent.change(screen.getByLabelText(/DPO date/), {
      target: { value: "2026-06-20" },
    });
    await userEvent.type(screen.getByLabelText(/Purpose of travel/), "Site visit");
    await userEvent.type(screen.getByLabelText(/^Destination \*/), "Manila");
    await userEvent.selectOptions(screen.getByLabelText(/Destination region/), "13");
    fireEvent.change(screen.getByLabelText(/Departure date/), {
      target: { value: "2026-07-01" },
    });
    fireEvent.change(screen.getByLabelText(/Return date/), {
      target: { value: "2026-07-03" },
    });
    // Attestations start UNANSWERED on a fresh draft — answer both "No".
    const noRadios = screen.getAllByRole("radio", { name: "No" });
    await userEvent.click(noRadios[0]);
    await userEvent.click(noRadios[1]);
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));

    await waitFor(() => expect(screen.getByText("itinerary page")).toBeInTheDocument());
    expect(patched).toMatchObject({
      dpo_no: "DPO-1",
      destination_region_code: "13",
      date_depart: "2026-07-01",
      date_return: "2026-07-03",
      is_within_50km: false,
      overnight_stay: false,
    });
  });
});
