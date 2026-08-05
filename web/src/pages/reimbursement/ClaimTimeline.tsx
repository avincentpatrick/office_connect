import type { TimelineEvent } from "../../api/reimbursement";
import { Card } from "../../components/Card/Card";
import { Skeleton } from "../../components/Skeleton/Skeleton";
import { StatusChip } from "../../components/StatusChip/StatusChip";
import { Timeline } from "../../components/Timeline/Timeline";
import { formatManilaDate } from "../../lib/format";
import { useTimeline } from "./use-claim";

/**
 * The claim tracker (spec §9.2) — "where is my money and whose move is it?"
 * answered as a chronology rather than a single status word.
 *
 * Return reasons render UNDER their event as chips: they belong to that one
 * bounce, and spec §12 requires the claimant sees them verbatim, so they are
 * shown rather than summarized. The tracker is best-effort chrome — if it
 * fails to load the claim itself still renders (the rail degrades, the record
 * does not).
 */
export function ClaimTimeline({ claimId }: { claimId: number }) {
  const query = useTimeline(claimId);

  return (
    <Card title="Tracker">
      {query.isPending ? (
        <Skeleton variant="row" />
      ) : query.isError || query.data.length === 0 ? (
        <p className="text-sm text-text-muted">
          Nothing has happened on this claim yet.
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          <Timeline events={query.data.map(toTimelineEvent)} />
          {query.data
            .filter((event) => event.reasons.length > 0)
            .map((event) => (
              <section
                key={`reasons-${event.kind}-${event.id}`}
                aria-label={`Reasons for the return on ${event.to_status_label}`}
                className="flex flex-col gap-2 border-t border-border pt-3"
              >
                <h3 className="text-sm font-medium text-text">
                  Why it came back
                </h3>
                <div className="flex flex-wrap gap-2">
                  {event.reasons.map((reason) => (
                    <StatusChip key={reason.id} status="warn">
                      {reason.label}
                    </StatusChip>
                  ))}
                </div>
              </section>
            ))}
        </div>
      )}
    </Card>
  );
}

function toTimelineEvent(event: TimelineEvent) {
  return {
    // The two lanes have independent id spaces (`reimb_status_histories` and
    // `reimb_external_events`), so the kind has to be in the React key or a
    // transition and an FMS update can collide (R-7-events).
    id: `${event.kind}-${event.id}`,
    // "System" is the honest fallback for an automatic transition. An FMS row
    // always has a person behind it — whoever at FMS said it, or the Admin
    // Officer who wrote it down — and the server already picked between them.
    actor: event.actor_display ?? "System",
    timestamp: event.created_at,
    description: describe(event),
  };
}

/**
 * One line of the story. An FMS row is prefixed rather than shown bare: the
 * feed mixes "this claim moved to Admin Review" with "FMS says it is With
 * Accounting", and without the attribution the second reads as a claim status
 * the platform controls — which is exactly what a sub-status is not.
 */
function describe(event: TimelineEvent): string {
  const headline =
    event.kind === "external"
      ? `FMS: ${event.to_status_label}`
      : event.to_status_label;
  // What FMS says the date was, when it differs from when it was relayed —
  // a packet moved on Friday and phoned through on Monday is two facts.
  const dated =
    event.kind === "external" && event.event_date
      ? `${headline} (${formatManilaDate(event.event_date)})`
      : headline;
  return event.note ? `${dated} — ${event.note}` : dated;
}
