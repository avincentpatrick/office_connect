import { describe, expect, it } from "vitest";
import { makeChecklistItem, makeChecklistSummary } from "../../test/reimb-fixtures";
import {
  CHECKLIST_GROUP_ORDER,
  GATE_FALLBACK,
  SCAN_NOTE,
  SCAN_PRESENTATION,
  checklistProgress,
  gateMessage,
  itemPresentation,
} from "./checklist-status";

describe("itemPresentation", () => {
  it("maps spec §9.1's six-word vocabulary onto the four platform semantics", () => {
    const cases: Array<[Parameters<typeof makeChecklistItem>[0], string, string]> = [
      [{ status: "missing", required: true }, "warn", "To do"],
      [{ status: "missing", required: false }, "waiting", "Optional"],
      [{ status: "attached" }, "done", "Attached"],
      [{ status: "generated" }, "done", "Generated"],
      [{ status: "auto_passed" }, "done", "Checked"],
      [{ status: "auto_flagged" }, "warn", "Flagged"],
      [{ status: "waived" }, "waiting", "Waived"],
    ];
    for (const [overrides, status, label] of cases) {
      expect(itemPresentation(makeChecklistItem(overrides))).toEqual({
        status,
        label,
      });
    }
  });

  it("keeps a required-and-missing item AMBER, not red", () => {
    // On a fresh draft every required item is missing; a wall of red on arrival
    // reads as "you did something wrong". Red is for where the item actually
    // blocks a decision (the Review gate, the approver's callout).
    expect(itemPresentation(makeChecklistItem()).status).toBe("warn");
  });

  it("keeps a flag amber too — a flag never blocks alone (spec §5.3)", () => {
    expect(itemPresentation(makeChecklistItem({ status: "auto_flagged" })).status).toBe(
      "warn",
    );
  });
});

describe("scan state is not item state", () => {
  it("says a pending file is being checked, not that it is attached", () => {
    expect(SCAN_PRESENTATION.pending).toEqual({
      status: "waiting",
      label: "Checking",
    });
    expect(SCAN_NOTE.pending).toContain("you can submit now");
  });

  it("has honest copy for every scan outcome", () => {
    expect(SCAN_NOTE.clean).toBeNull();
    expect(SCAN_NOTE.infected).toContain("removed");
    expect(SCAN_NOTE.error).toContain("again");
  });
});

describe("progress and gate copy", () => {
  it("uses spec §9.1's exact wording", () => {
    expect(
      checklistProgress(
        makeChecklistSummary({ required_total: 12, required_done: 9 }),
      ),
    ).toBe("9 of 12 required items done");
  });

  it("renders the server's gate sentence verbatim", () => {
    const summary = makeChecklistSummary({ required_total: 2, required_done: 0 });
    expect(gateMessage(summary)).toBe(summary.gate_message);
  });

  it("falls back only when the server sent no sentence", () => {
    expect(
      gateMessage(makeChecklistSummary({ blocking: [], gate_message: null })),
    ).toBe(GATE_FALLBACK);
  });
});

describe("group vocabulary", () => {
  it("covers every catalog group exactly once", () => {
    expect(new Set(CHECKLIST_GROUP_ORDER).size).toBe(CHECKLIST_GROUP_ORDER.length);
    expect(CHECKLIST_GROUP_ORDER).toHaveLength(7);
  });
});
