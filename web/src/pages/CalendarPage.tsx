/**
 * Calendar of Activities — the agenda surface (Stage D-2).
 *
 * ui-standards §4's **List page**, unchanged: its mandatory `loading` /
 * `isEmpty` / `emptyState` structure is exactly what a calendar needs. What
 * differs is only the arrangement of the children slot — an `<ol>` of DAY
 * GROUPS, each an `<h2>` date over a `<ul>` of rows.
 *
 * **Never a `<table>` of days** (the classic screen-reader trap), and empty days
 * are never rendered: the server omits them, and an agenda is a list of days
 * that have something. See the §4 template note, 2026-08-09.
 */

import { useState } from "react";
import { CalendarDays } from "lucide-react";
import { Link } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { ApiError } from "../api/http";
import {
  calendarKeys,
  fetchCalendar,
  type CalendarDay,
  type CalendarEvent,
} from "../api/calendar";
import { SelectField } from "../components/SelectField/SelectField";
import { StatusChip } from "../components/StatusChip/StatusChip";
import { ListPage } from "../layouts/ListPage";
import { formatManilaDate } from "../lib/format";
import {
  CALENDAR_VIEWS,
  boundedNotes,
  clampNote,
  emptyCalendarState,
  rowStatus,
  shiftIso,
  truncationNote,
  viewByValue,
} from "./calendar-copy";

/** Today in Manila, as an ISO date, for building the requested window.
 *  The SERVER still decides the real window and echoes it back — this only
 *  chooses which question to ask. */
function manilaToday(): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Manila",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

function EventRow({ event }: { event: CalendarEvent }) {
  const label = event.status_label ?? event.status ?? "Scheduled";
  const meta = [event.detail, event.date_end ? `to ${formatManilaDate(event.date_end)}` : null]
    .filter(Boolean)
    .join(" · ");

  return (
    <li className="flex min-h-11 flex-col gap-1 py-3">
      <div className="flex items-baseline justify-between gap-2">
        {/* An activity has nowhere to go — no detail screen exists — so the row
            is inert rather than a link to nowhere. WorkItemRow was deliberately
            NOT widened for this: its `to` is required and its identity is
            "linked ref + title" (ui-standards §4 note, 2026-08-09). */}
        {event.href ? (
          <Link to={event.href} className="text-base font-medium text-link underline">
            {event.title}
          </Link>
        ) : (
          <span className="text-base font-medium text-text">{event.title}</span>
        )}
        <StatusChip status={rowStatus(event.tone, event.urgency)}>{label}</StatusChip>
      </div>
      {meta ? <p className="text-sm text-text-muted">{meta}</p> : null}
    </li>
  );
}

function DayGroup({ day }: { day: CalendarDay }) {
  const heading = formatManilaDate(day.date);
  // The count and the qualifiers go BELOW the h2, never inside it: a
  // screen-reader heading list must read "Aug 12, 2026", not
  // "Aug 12, 2026 3 events Holiday" (ui-standards §4, R-7-board rule 2).
  const qualifiers = [
    day.is_today ? "Today" : null,
    day.nonworking_label ?? (day.is_nonworking ? "Non-working day" : null),
  ].filter(Boolean);

  return (
    <li className="flex flex-col gap-1">
      <h2 className="text-sm font-semibold text-text">{heading}</h2>
      {qualifiers.length ? (
        <p className="text-xs text-text-muted">{qualifiers.join(" · ")}</p>
      ) : null}
      <ul className="divide-y divide-border border-t border-b border-border">
        {day.events.map((event) => (
          <EventRow key={`${event.source}:${event.ref}`} event={event} />
        ))}
      </ul>
    </li>
  );
}

export function CalendarPage() {
  const [view, setView] = useState(CALENDAR_VIEWS[0].value);
  const selected = viewByValue(view);
  const today = manilaToday();
  const win = {
    start: shiftIso(today, selected.offsetStart),
    end: shiftIso(today, selected.offsetEnd),
  };

  const query = useQuery({
    queryKey: calendarKeys.window(win),
    queryFn: () => fetchCalendar(win),
    // A 403 is an ANSWER, not a blip.
    retry: false,
  });

  const filters = (
    <SelectField
      id="calendar-view"
      label="Show"
      options={CALENDAR_VIEWS.map(({ value, label }) => ({ value, label }))}
      value={view}
      onChange={(event) => setView(event.target.value)}
    />
  );

  if (query.isError) {
    return (
      <ListPage
        title="Calendar"
        filters={filters}
        loading={false}
        isEmpty
        emptyState={{
          icon: CalendarDays,
          title:
            query.error instanceof ApiError && query.error.status === 403
              ? "This calendar is not yours to see"
              : "The calendar could not load",
          // The SERVER's sentence, never a paraphrase the page has to keep true.
          description:
            query.error instanceof ApiError
              ? query.error.message
              : "Something went wrong. Please try again.",
        }}
      />
    );
  }

  const data = query.data;
  const notes = boundedNotes(data);
  const truncation = truncationNote(data);
  const clamp = clampNote(data);

  return (
    <>
      <ListPage
        title="Calendar"
        filters={filters}
        loading={query.isPending}
        isEmpty={(data?.days.length ?? 0) === 0}
        emptyState={{ icon: CalendarDays, ...emptyCalendarState(data) }}
      >
        {clamp ? <p className="text-sm text-text-muted">{clamp}</p> : null}
        {truncation ? <p className="text-sm text-text-muted">{truncation}</p> : null}
        <ol className="flex flex-col gap-4">
          {(data?.days ?? []).map((day) => (
            <DayGroup key={day.date} day={day} />
          ))}
        </ol>
      </ListPage>
      {/*
        A SIBLING of ListPage, not a child — and that is load-bearing, not
        layout. `ListPage` renders `children` only when the list is NON-empty
        (the same quirk CashAdvancesPage records), so a scope footnote placed
        inside would vanish in exactly the state where it matters most: a viewer
        whose travel layer is bounded to nothing needs to be told WHY, or an
        empty calendar reads as "nothing is happening".
      */}
      {notes.length ? (
        <section
          aria-label="What this calendar is showing you"
          className="flex flex-col gap-1 pt-4"
        >
          {notes.map((note) => (
            <p key={note} className="text-sm text-text-muted">
              {note}
            </p>
          ))}
        </section>
      ) : null}
    </>
  );
}
