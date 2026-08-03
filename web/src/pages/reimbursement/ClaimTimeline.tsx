import type { TimelineEvent } from "../../api/reimbursement";
import { Card } from "../../components/Card/Card";
import { Skeleton } from "../../components/Skeleton/Skeleton";
import { StatusChip } from "../../components/StatusChip/StatusChip";
import { Timeline } from "../../components/Timeline/Timeline";
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
                key={`reasons-${event.id}`}
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
    id: event.id,
    actor: event.actor_display ?? "System",
    timestamp: event.created_at,
    description: event.note
      ? `${event.to_status_label} — ${event.note}`
      : event.to_status_label,
  };
}
