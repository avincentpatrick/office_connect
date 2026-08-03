import { describe, expect, it } from "vitest";
import {
  completeClaim,
  documentsPending,
  makeChecklistSummary,
  makeClaim,
} from "../../test/reimb-fixtures";
import { buildTaskSections, firstIncompleteStep, stepStatus } from "./wizard-steps";

describe("stepStatus derivation", () => {
  it("gates a fresh draft: only Trip is startable", () => {
    const status = stepStatus(makeClaim());
    expect(status).toEqual({
      trip: "not_started",
      itinerary: "blocked",
      money: "blocked",
      documents: "blocked",
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
      // The checklist HAS materialized on this fixture, so Documents stays open
      // rather than reverting to "cannot start yet".
      documents: "done",
      review: "blocked",
    });

    const ready = completeClaim();
    expect(stepStatus(ready)).toEqual({
      trip: "done",
      itinerary: "done",
      money: "done",
      documents: "done",
      review: "not_started",
    });
    expect(firstIncompleteStep(ready)).toBe("review");
  });

  it("resumes on Documents while required items are outstanding", () => {
    const pending = documentsPending();
    expect(stepStatus(pending).documents).toBe("not_started");
    expect(firstIncompleteStep(pending)).toBe("documents");
  });

  it("marks Documents in progress on a partly-attached packet", () => {
    const half = completeClaim({
      checklist: makeChecklistSummary({ required_total: 2, required_done: 1 }),
    });
    expect(stepStatus(half).documents).toBe("in_progress");
  });

  it("leaves Review startable while documents are outstanding", () => {
    // Spec §9.3 step 5: the PAGE is reachable and lists the blockers inline;
    // the BUTTON is what the gate disables.
    expect(stepStatus(documentsPending()).review).toBe("not_started");
  });

  it("re-opens Money when the server clears stale totals after an edit", () => {
    const stale = completeClaim({ totals: null });
    expect(stepStatus(stale).money).toBe("in_progress");
    expect(stepStatus(stale).review).toBe("blocked");
    // …and Documents, which already holds the claimant's uploads, must NOT
    // revert to "cannot start yet" just because the money snapshot went.
    expect(stepStatus(stale).documents).not.toBe("blocked");
  });

  it("falls open when the server sends no checklist summary", () => {
    // Blocking where the server would allow strands the user with no path; the
    // other way round costs one round trip and shows the server's own words.
    const legacy = completeClaim({ checklist: undefined });
    expect(stepStatus(legacy).documents).toBe("done");
    expect(stepStatus(legacy).review).toBe("not_started");
  });

  it("derives a returned claim as fully editable with Review pending", () => {
    const returned = completeClaim({ status: "returned", status_label: "Returned" });
    expect(stepStatus(returned)).toEqual({
      trip: "done",
      itinerary: "done",
      money: "done",
      documents: "done",
      review: "not_started",
    });
  });
});

describe("buildTaskSections", () => {
  it("links startable steps and leaves blocked ones inert", () => {
    const sections = buildTaskSections(makeClaim());
    expect(sections).toHaveLength(1);
    const [trip, itinerary, money, documents, review] = sections[0].items;
    expect(trip.to).toBe("/reimbursement/claims/7/trip");
    expect(trip.statusLabel).toBe("Not started");
    expect(itinerary.to).toBeUndefined();
    expect(itinerary.statusLabel).toBe("Cannot start yet");
    expect(money.to).toBeUndefined();
    expect(documents.to).toBeUndefined();
    expect(review.to).toBeUndefined();
  });

  it("carries the progress line as the Documents hint", () => {
    // Spec §9.1's always-visible "9 of 12 required items done", in the rail on
    // every step page rather than only on Documents itself.
    const sections = buildTaskSections(
      completeClaim({
        checklist: makeChecklistSummary({ required_total: 2, required_done: 1 }),
      }),
    );
    const documents = sections[0].items[3];
    expect(documents.hint).toBe("1 of 2 required items done");
    expect(sections[0].items[0].hint).toBeUndefined();
  });
});
