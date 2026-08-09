/**
 * Copy + view definitions for the Calendar of Activities (Stage D-2).
 *
 * Pure functions, tested separately, mirroring `landing-copy.ts`. Anything that
 * quotes a number quotes the SERVER's number — an empty state that invents its
 * own date range is a page telling the user about a window nobody queried.
 */

import type { CalendarResponse, CalendarTone } from "../api/calendar";
import type { SemanticStatus } from "../components/StatusChip/StatusChip";

/**
 * The named windows, per ui-standards §4 (R-7-queue rule 1): a `SelectField` of
 * named QUESTIONS, never a row of ad-hoc toggles. `offsetStart`/`offsetEnd` are
 * days from today; the page turns them into dates.
 */
export interface CalendarView {
  value: string;
  label: string;
  offsetStart: number;
  offsetEnd: number;
}

export const CALENDAR_VIEWS: CalendarView[] = [
  { value: "next30", label: "Next 30 days", offsetStart: 0, offsetEnd: 30 },
  { value: "next90", label: "Next 90 days", offsetStart: 0, offsetEnd: 90 },
  { value: "last30", label: "Last 30 days", offsetStart: -30, offsetEnd: 0 },
  { value: "around", label: "Two weeks either side", offsetStart: -14, offsetEnd: 14 },
];

export function viewByValue(value: string): CalendarView {
  return CALENDAR_VIEWS.find((v) => v.value === value) ?? CALENDAR_VIEWS[0];
}

/** `YYYY-MM-DD` for a day offset from an ISO date, computed in UTC so a
 *  browser west of Manila cannot shift the window by a day. */
export function shiftIso(iso: string, days: number): string {
  const base = new Date(`${iso}T00:00:00Z`);
  base.setUTCDate(base.getUTCDate() + days);
  return base.toISOString().slice(0, 10);
}

/** The server's `tone`, narrowed to the StatusChip contract. */
export function chipStatus(tone: CalendarTone | null): SemanticStatus {
  switch (tone) {
    case "done":
      return "done";
    case "warn":
      return "warn";
    case "blocked":
      return "blocked";
    default:
      return "waiting";
  }
}

/** Urgency wins over status tone: an overdue row is red whatever its state. */
export function rowStatus(
  tone: CalendarTone | null,
  urgency: string | null,
): SemanticStatus {
  if (urgency === "overdue") return "blocked";
  if (urgency === "due_soon") return "warn";
  return chipStatus(tone);
}

export function formatRange(startIso: string, endIso: string): string {
  const fmt = (iso: string) =>
    new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-US", {
      timeZone: "UTC",
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  return `${fmt(startIso)} to ${fmt(endIso)}`;
}

/**
 * The empty state must answer the question that was ASKED (ui-standards §4,
 * R-7-queue rule 3) — quoting the server's own window rather than "Nothing
 * here", which is wrong under every filter.
 */
export function emptyCalendarState(data: CalendarResponse | undefined): {
  title: string;
  description: string;
} {
  if (!data) {
    return {
      title: "Nothing scheduled",
      description: "Activities, travel and liquidation deadlines appear here.",
    };
  }
  return {
    title: `Nothing scheduled ${formatRange(data.start, data.end)}`,
    description:
      "Activities appear here as they are recorded, along with travel you can " +
      "see and your own liquidation deadlines.",
  };
}

/**
 * The "what you are not seeing" footnote, assembled from the server's own
 * sentences. Rendered whether or not the list is empty: a scope note shown only
 * in the empty state hides at exactly the moment it is load-bearing — when the
 * page has rows and therefore looks complete.
 */
export function boundedNotes(data: CalendarResponse | undefined): string[] {
  if (!data) return [];
  return data.sources
    .map((source) => source.bounded_note)
    .filter((note): note is string => Boolean(note));
}

/**
 * "Showing N of M" — only when they differ, and always from the server's
 * `total` (api-standards §9g: a page given both must never re-derive it).
 */
export function truncationNote(data: CalendarResponse | undefined): string | null {
  if (!data) return null;
  const shown = data.days.reduce((sum, day) => sum + day.events.length, 0);
  if (shown >= data.total) return null;
  return `Showing ${shown} of ${data.total}. Narrow the window to see the rest.`;
}

/** Stated only when the server actually clamped, quoting its ceiling. */
export function clampNote(data: CalendarResponse | undefined): string | null {
  if (!data?.window_clamped) return null;
  return `Windows are limited to ${data.window_max_days} days, so this view ends ${formatRange(
    data.start,
    data.end,
  )}.`;
}
