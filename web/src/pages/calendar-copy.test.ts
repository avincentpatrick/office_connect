import { describe, expect, it } from "vitest";
import type { CalendarResponse } from "../api/calendar";
import {
  CALENDAR_VIEWS,
  boundedNotes,
  clampNote,
  emptyCalendarState,
  formatRange,
  rowStatus,
  shiftIso,
  truncationNote,
  viewByValue,
} from "./calendar-copy";

function makeResponse(over: Partial<CalendarResponse> = {}): CalendarResponse {
  return {
    days: [],
    total: 0,
    start: "2026-08-09",
    end: "2026-09-08",
    window_max_days: 92,
    window_clamped: false,
    source_cap: 200,
    sources: [],
    today: "2026-08-09",
    ...over,
  };
}

describe("shiftIso", () => {
  it("shifts in UTC so a browser west of Manila cannot move the window a day", () => {
    expect(shiftIso("2026-08-09", 30)).toBe("2026-09-08");
    expect(shiftIso("2026-08-09", -30)).toBe("2026-07-10");
    expect(shiftIso("2026-08-09", 0)).toBe("2026-08-09");
  });

  it("crosses a month and a year boundary", () => {
    expect(shiftIso("2026-12-31", 1)).toBe("2027-01-01");
    expect(shiftIso("2027-01-01", -1)).toBe("2026-12-31");
  });
});

describe("views", () => {
  it("falls back to the first view for an unknown value", () => {
    expect(viewByValue("nonsense")).toBe(CALENDAR_VIEWS[0]);
  });

  it("defaults to a forward-looking window", () => {
    // A calendar opens on "what is coming up". A default that looked backwards
    // would answer a question nobody opens a calendar to ask.
    expect(CALENDAR_VIEWS[0].offsetStart).toBe(0);
    expect(CALENDAR_VIEWS[0].offsetEnd).toBeGreaterThan(0);
  });

  it("keeps every window inside the server's 92-day ceiling", () => {
    // A view that could not be served would clamp on every load and show the
    // clamp note permanently — a page arguing with its own server.
    for (const view of CALENDAR_VIEWS) {
      expect(view.offsetEnd - view.offsetStart).toBeLessThanOrEqual(92);
    }
  });
});

describe("rowStatus", () => {
  it("lets urgency beat the status tone", () => {
    // An overdue liquidation is red even though its advance is merely "open".
    expect(rowStatus("waiting", "overdue")).toBe("blocked");
    expect(rowStatus("done", "due_soon")).toBe("warn");
  });

  it("uses the source's tone when there is no deadline", () => {
    expect(rowStatus("done", null)).toBe("done");
    expect(rowStatus("blocked", null)).toBe("blocked");
  });

  it("falls back to waiting for a tone it does not recognise", () => {
    // A source added later must render as something neutral rather than crash
    // or borrow a colour that means a verdict nobody made.
    expect(rowStatus(null, null)).toBe("waiting");
  });
});

describe("emptyCalendarState", () => {
  it("quotes the server's window rather than saying 'nothing here'", () => {
    const state = emptyCalendarState(makeResponse());
    expect(state.title).toContain("Aug 9, 2026");
    expect(state.title).toContain("Sep 8, 2026");
  });

  it("degrades without data", () => {
    expect(emptyCalendarState(undefined).title).toBe("Nothing scheduled");
  });
});

describe("boundedNotes", () => {
  it("collects only the sources that actually withheld something", () => {
    const notes = boundedNotes(
      makeResponse({
        sources: [
          { key: "core.activity", label: "Activities", count: 2, total: 2, bounded_note: null },
          {
            key: "reimb.travel",
            label: "Travel",
            count: 0,
            total: 0,
            bounded_note: "Travel shown here is your own.",
          },
        ],
      }),
    );
    expect(notes).toEqual(["Travel shown here is your own."]);
  });
});

describe("truncationNote", () => {
  it("quotes the SERVER's total and never re-derives it from the rows", () => {
    const note = truncationNote(
      makeResponse({
        total: 137,
        days: [
          {
            date: "2026-08-10",
            is_today: false,
            is_nonworking: false,
            nonworking_label: null,
            events: [
              {
                source: "core.activity",
                ref: "activity:1",
                title: "One",
                date_start: "2026-08-10",
                date_end: null,
                detail: null,
                status: null,
                status_label: null,
                tone: null,
                urgency: null,
                href: null,
                activity_id: 1,
              },
            ],
          },
        ],
      }),
    );
    expect(note).toBe("Showing 1 of 137. Narrow the window to see the rest.");
  });

  it("says nothing when the page is complete", () => {
    expect(truncationNote(makeResponse({ total: 0 }))).toBeNull();
  });
});

describe("clampNote", () => {
  it("speaks only when the server actually clamped, quoting its ceiling", () => {
    expect(clampNote(makeResponse())).toBeNull();
    const note = clampNote(makeResponse({ window_clamped: true }));
    expect(note).toContain("92 days");
  });
});

describe("formatRange", () => {
  it("uses the ui-standards §5 date format", () => {
    expect(formatRange("2026-07-20", "2026-08-19")).toBe("Jul 20, 2026 to Aug 19, 2026");
  });
});
