import { formatManilaDateTime } from "../../lib/format";

export interface TimelineEvent {
  id: string | number;
  actor: string;
  /** ISO timestamp (UTC from the server; displayed Manila). */
  timestamp: string;
  description: string;
}

/** ui-standards §3.8 — chronological events with actor + Manila timestamp. */
export function Timeline({ events }: { events: TimelineEvent[] }) {
  return (
    <ol className="flex flex-col">
      {events.map((event, index) => (
        <li key={event.id} className="relative flex gap-3 pb-4">
          <span aria-hidden="true" className="flex flex-col items-center">
            <span className="mt-1.5 size-2 rounded-lg bg-brand" />
            {index < events.length - 1 ? <span className="w-px flex-1 bg-border" /> : null}
          </span>
          <div className="flex flex-col">
            <p className="text-base text-text">{event.description}</p>
            <p className="text-sm text-text-muted">
              {event.actor} · {formatManilaDateTime(event.timestamp)}
            </p>
          </div>
        </li>
      ))}
    </ol>
  );
}
