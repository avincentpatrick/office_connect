import { describe, expect, it } from "vitest";
import { completeClaim, makeClaim } from "../../test/reimb-fixtures";
import { buildTaskSections, firstIncompleteStep, stepStatus } from "./wizard-steps";

describe("stepStatus derivation", () => {
  it("gates a fresh draft: only Trip is startable", () => {
    const status = stepStatus(makeClaim());
    expect(status).toEqual({
      trip: "not_started",
      itinerary: "blocked",
      money: "blocked",
      review: "blocked",
    });
    expect(firstIncompleteStep(makeClaim())).toBe("trip");
  });

  it("marks Trip in progress once any field is set", () => {
    const claim = makeClaim({ purpose: "Site visit" });
    expect(stepStatus(claim).trip).toBe("in_progress");
  });

  it("opens Money after legs exist and Review after totals compute", () => {
    const withLegs = completeClaim({ totals: null, fund_source: null });
    expect(stepStatus(withLegs)).toEqual({
      trip: "done",
      itinerary: "done",
      money: "not_started",
      review: "blocked",
    });

    const ready = completeClaim();
    expect(stepStatus(ready)).toEqual({
      trip: "done",
      itinerary: "done",
      money: "done",
      review: "not_started",
    });
    expect(firstIncompleteStep(ready)).toBe("review");
  });

  it("re-opens Money when the server clears stale totals after an edit", () => {
    const stale = completeClaim({ totals: null });
    expect(stepStatus(stale).money).toBe("in_progress");
    expect(stepStatus(stale).review).toBe("blocked");
  });

  it("derives a returned claim as fully editable with Review pending", () => {
    const returned = completeClaim({ status: "returned", status_label: "Returned" });
    expect(stepStatus(returned)).toEqual({
      trip: "done",
      itinerary: "done",
      money: "done",
      review: "not_started",
    });
  });
});

describe("buildTaskSections", () => {
  it("links startable steps and leaves blocked ones inert", () => {
    const sections = buildTaskSections(makeClaim());
    expect(sections).toHaveLength(1);
    const [trip, itinerary, money, review] = sections[0].items;
    expect(trip.to).toBe("/reimbursement/claims/7/trip");
    expect(trip.statusLabel).toBe("Not started");
    expect(itinerary.to).toBeUndefined();
    expect(itinerary.statusLabel).toBe("Cannot start yet");
    expect(money.to).toBeUndefined();
    expect(review.to).toBeUndefined();
  });
});
