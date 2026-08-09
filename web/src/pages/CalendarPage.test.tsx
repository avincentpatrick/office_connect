import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import type { CalendarResponse } from "../api/calendar";
import { expectNoA11yViolations } from "../test/a11y";
import { makeConfig, makeMe } from "../test/auth-fixtures";
import { renderRoutes } from "../test/harness";
import { CalendarPage } from "./CalendarPage";

const ROUTES = [{ path: "/calendar", element: <CalendarPage /> }];
/** The page asks for its default view (next 30 days) on mount. */
const ANY_CALENDAR = /^GET \/api\/v1\/calendar/;

function makeCalendar(over: Partial<CalendarResponse> = {}): CalendarResponse {
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

function event(over: Partial<CalendarResponse["days"][0]["events"][0]> = {}) {
  return {
    source: "core.activity",
    ref: "activity:1",
    title: "Regional health systems review",
    date_start: "2026-08-12",
    date_end: null,
    detail: "Regional Office",
    status: "planned",
    status_label: "Planned",
    tone: "waiting" as const,
    urgency: null,
    href: null,
    activity_id: 1,
    ...over,
  };
}

function day(over: Partial<CalendarResponse["days"][0]> = {}) {
  return {
    date: "2026-08-12",
    is_today: false,
    is_nonworking: false,
    nonworking_label: null,
    events: [event()],
    ...over,
  };
}

/** Stub every calendar URL regardless of its query string — the window is built
 *  from the real clock, so pinning an exact URL would make these tests fail on
 *  a different day for a reason that has nothing to do with the page. */
function stubCalendar(body: unknown, status = 200) {
  const spy = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input.toString();
    if (!ANY_CALENDAR.test(`GET ${url}`)) throw new Error(`unstubbed ${url}`);
    return new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

function render() {
  return renderRoutes(ROUTES, "/calendar", {
    me: makeMe({ permissions: ["activity.calendar.read"] }),
    config: makeConfig(),
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("CalendarPage", () => {
  it("shows the mandatory skeleton while loading", () => {
    stubCalendar(makeCalendar());
    render();
    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
  });

  it("groups events under a date heading, never in a table", async () => {
    stubCalendar(makeCalendar({ days: [day()], total: 1 }));
    render();

    const heading = await screen.findByRole("heading", { name: "Aug 12, 2026" });
    expect(heading.tagName).toBe("H2");
    // A grid of days is the classic screen-reader trap the agenda shape avoids.
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getByText("Regional health systems review")).toBeInTheDocument();
  });

  it("keeps the count and qualifiers OUT of the heading", async () => {
    stubCalendar(
      makeCalendar({
        days: [day({ is_today: true, is_nonworking: true, nonworking_label: "Holiday" })],
        total: 1,
      }),
    );
    render();

    // R-7-board rule 2: a heading list must read "Aug 12, 2026", not
    // "Aug 12, 2026 Today Holiday".
    const heading = await screen.findByRole("heading", { name: "Aug 12, 2026" });
    expect(heading.textContent).toBe("Aug 12, 2026");
    expect(screen.getByText("Today · Holiday")).toBeInTheDocument();
  });

  it("renders an activity as an INERT row — no link to nowhere", async () => {
    stubCalendar(makeCalendar({ days: [day()], total: 1 }));
    render();

    await screen.findByText("Regional health systems review");
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("links a row that has somewhere to go", async () => {
    stubCalendar(
      makeCalendar({
        days: [
          day({
            events: [
              event({
                source: "reimb.travel",
                ref: "claim:88",
                title: "Regional review trip",
                href: "/reimbursement/claims/88",
              }),
            ],
          }),
        ],
        total: 1,
      }),
    );
    render();

    const link = await screen.findByRole("link", { name: "Regional review trip" });
    expect(link).toHaveAttribute("href", "/reimbursement/claims/88");
  });

  it("renders the server's total and never re-derives it from the rows", async () => {
    stubCalendar(makeCalendar({ days: [day()], total: 137 }));
    render();

    // The fixture deliberately disagrees with itself: one visible row, 137 total.
    expect(
      await screen.findByText("Showing 1 of 137. Narrow the window to see the rest."),
    ).toBeInTheDocument();
  });

  it("shows the scope note even when the calendar is EMPTY", async () => {
    // The load-bearing case. A viewer whose travel layer is bounded to nothing
    // must be told why, or an empty calendar reads as "nothing is happening".
    stubCalendar(
      makeCalendar({
        days: [],
        total: 0,
        sources: [
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
    render();

    expect(await screen.findByText("Travel shown here is your own.")).toBeInTheDocument();
    expect(screen.getByText(/Nothing scheduled/)).toBeInTheDocument();
  });

  it("answers the question that was asked in the empty state", async () => {
    stubCalendar(makeCalendar());
    render();

    expect(
      await screen.findByText("Nothing scheduled Aug 9, 2026 to Sep 8, 2026"),
    ).toBeInTheDocument();
  });

  it("renders the SERVER's refusal sentence on a 403, not a paraphrase", async () => {
    stubCalendar(
      { error: { code: "forbidden", message: "You do not have permission to do that." } },
      403,
    );
    render();

    expect(await screen.findByText("This calendar is not yours to see")).toBeInTheDocument();
    expect(
      screen.getByText("You do not have permission to do that."),
    ).toBeInTheDocument();
  });

  it("offers named windows as a select, not ad-hoc toggles", async () => {
    stubCalendar(makeCalendar());
    render();

    const select = await screen.findByLabelText("Show");
    expect(select.tagName).toBe("SELECT");
    expect(within(select).getByRole("option", { name: "Next 30 days" })).toBeInTheDocument();
  });

  it("re-queries when the window changes", async () => {
    // The window value is in the query key (ui-standards §4, R-7-queue rule 2).
    // Without that, switching views would serve the previous window from cache —
    // the user would be shown the last question they asked, not this one.
    const spy = stubCalendar(makeCalendar());
    render();

    const select = await screen.findByLabelText("Show");
    const before = spy.mock.calls.length;
    fireEvent.change(select, { target: { value: "last30" } });

    await waitFor(() => expect(spy.mock.calls.length).toBeGreaterThan(before));
  });

  it("has no accessibility violations while listing a day", async () => {
    stubCalendar(makeCalendar({ days: [day()], total: 1 }));
    const { container } = render();

    await screen.findByRole("heading", { name: "Aug 12, 2026" });
    await expectNoA11yViolations(container);
  });
});
