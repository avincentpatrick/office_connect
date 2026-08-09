/**
 * Calendar of Activities — GET /api/v1/calendar (Stage D-2).
 *
 * Every human-readable string on a row is SERVER-authored (`status_label`) and
 * every colour comes from the server's `tone`/`urgency`. That is not ceremony:
 * the calendar is generic over sources, and a page that mapped
 * `handed_to_fms` to a word or a colour would be a core surface hard-coding one
 * module's vocabulary — the coupling api-standards §9k removes from the
 * backend, smuggled back in through the browser.
 */

import { api } from "./http";

/** ui-standards §2's semantic set, translated BY THE SOURCE. */
export type CalendarTone = "done" | "warn" | "blocked" | "waiting";

/** `services/deadline.py`'s vocabulary. `null` = this row is not a deadline. */
export type CalendarUrgency = "due_soon" | "overdue";

export interface CalendarEvent {
  /** The registry key of the contributing source, `<owner>.<thing>`. */
  source: string;
  ref: string;
  title: string;
  date_start: string;
  date_end: string | null;
  detail: string | null;
  status: string | null;
  status_label: string | null;
  tone: CalendarTone | null;
  urgency: CalendarUrgency | null;
  /** `null` = an inert row; nothing to open yet. */
  href: string | null;
  activity_id: number | null;
}

export interface CalendarDay {
  date: string;
  is_today: boolean;
  is_nonworking: boolean;
  nonworking_label: string | null;
  events: CalendarEvent[];
}

export interface CalendarSource {
  key: string;
  label: string;
  count: number;
  /** This source's window count BEFORE the cap. */
  total: number;
  /**
   * What bounded this source for this viewer, in the SERVER's words — or null
   * when nothing was withheld. Never a count of hidden rows (api-standards §9h).
   */
  bounded_note: string | null;
}

export interface CalendarResponse {
  days: CalendarDay[];
  /** Events in the window before any cap — render this, never re-derive it. */
  total: number;
  start: string;
  end: string;
  window_max_days: number;
  window_clamped: boolean;
  source_cap: number;
  sources: CalendarSource[];
  /** Manila today as the SERVER computed it — not the browser's day. */
  today: string;
}

export interface CalendarWindow {
  start?: string;
  end?: string;
}

export function fetchCalendar(win: CalendarWindow = {}): Promise<CalendarResponse> {
  const params = new URLSearchParams();
  if (win.start) params.set("start", win.start);
  if (win.end) params.set("end", win.end);
  const query = params.toString();
  return api<CalendarResponse>(`/calendar${query ? `?${query}` : ""}`);
}

/**
 * Query keys. The window value is IN the key (ui-standards §4, R-7-queue rule
 * 2): two windows are two different questions, and one cache entry for both
 * shows the viewer the last month they looked at instead of the one they asked
 * for.
 */
export const calendarKeys = {
  all: ["calendar"] as const,
  window: (win: CalendarWindow = {}) =>
    ["calendar", win.start ?? "default", win.end ?? "default"] as const,
};
