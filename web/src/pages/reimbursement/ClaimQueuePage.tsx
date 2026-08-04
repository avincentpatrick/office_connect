import { useState } from "react";
import { Inbox } from "lucide-react";
import { ApiError } from "../../api/http";
import type { ClaimQueueFilters, ClaimStatus } from "../../api/reimbursement";
import { SelectField } from "../../components/SelectField/SelectField";
import { WorkItemRow } from "../../components/WorkItemRow/WorkItemRow";
import { ListPage } from "../../layouts/ListPage";
import { queueChip, queueMeta, workItemTitle } from "./claim-status";
import { useClaimQueue } from "./use-claim";

/**
 * The oversight queue (R-7-queue) — spec §7 rule 5's "stalls are visible, not
 * silent", and the Admin Officer's "External > 10 working days" filter.
 *
 * It exists because of a hole the work-management model leaves by design: a
 * claim handed to FMS is held by `external_fms`, so it is in nobody's My Work
 * and the Admin Officer who sent it had no way to ever see it again. My Work
 * answers "what is mine"; this answers "what is stuck".
 *
 * Reachable by anyone, like the cash-advance register: the SERVER decides who
 * oversees whom, and a 403 renders as a plain explanation rather than a blank
 * page or a nav item we pretended not to have.
 */

/** The lenses, as one closed list — spec §6.1's statuses, in journey order. */
const VIEWS: {
  value: string;
  label: string;
  filters: ClaimQueueFilters;
}[] = [
  { value: "all", label: "Everything in flight", filters: {} },
  {
    value: "external_over",
    label: "With FMS too long",
    filters: { externalOver: true },
  },
  {
    value: "handed_to_fms",
    label: "With FMS",
    filters: { status: "handed_to_fms" as ClaimStatus },
  },
  {
    value: "fms_returned",
    label: "FMS returned",
    filters: { status: "fms_returned" as ClaimStatus },
  },
  {
    value: "admin_review",
    label: "Admin review",
    filters: { status: "admin_review" as ClaimStatus },
  },
  {
    value: "division_approval",
    label: "For approval",
    filters: { status: "division_approval" as ClaimStatus },
  },
];

export function ClaimQueuePage() {
  const [view, setView] = useState("all");
  const selected = VIEWS.find((v) => v.value === view) ?? VIEWS[0];
  const query = useClaimQueue(selected.filters);

  const denied = query.error instanceof ApiError && query.error.status === 403;

  if (query.isError) {
    return (
      <ListPage
        title="Claim queue"
        loading={false}
        isEmpty
        emptyState={{
          title: denied
            ? "This queue is not yours to see"
            : "The queue could not load",
          // The server's own words: it names My Work as the surface that DOES
          // answer the question this actor was asking (§9.1 principle 4), and
          // paraphrasing it here would be a second copy to keep true.
          description:
            query.error instanceof ApiError
              ? query.error.message
              : "Something went wrong. Please try again.",
        }}
      />
    );
  }

  const data = query.data;
  const items = data?.items ?? [];
  const filters = (
    <SelectField
      id="queue-view"
      label="Show"
      options={VIEWS.map(({ value, label }) => ({ value, label }))}
      value={view}
      onChange={(event) => setView(event.target.value)}
    />
  );

  return (
    <ListPage
      title="Claim queue"
      filters={filters}
      loading={query.isPending}
      isEmpty={items.length === 0}
      emptyState={{
        icon: Inbox,
        title:
          selected.value === "external_over"
            ? "Nothing is overdue with FMS"
            : "Nothing here right now",
        description:
          selected.value === "external_over" && data
            ? `No claim has been with FMS longer than ${data.followup_working_days} working days.`
            : "Claims you oversee appear here once they are submitted.",
      }}
    >
      {/* The count is stated because the queue pages: "showing 50 of 214" is
          the difference between a short list and a hidden backlog. */}
      {data && data.total > items.length ? (
        <p className="text-sm text-text-muted">
          Showing {items.length} of {data.total} claims.
        </p>
      ) : null}
      <ul className="divide-y divide-border border-t border-b border-border">
        {items.map((item) => {
          const chip = queueChip(item);
          return (
            <WorkItemRow
              key={item.id}
              refNo={item.ref_no}
              title={workItemTitle(item)}
              status={chip.status}
              statusLabel={chip.label}
              to={`/reimbursement/claims/${item.id}`}
              meta={queueMeta(item)}
            />
          );
        })}
      </ul>
    </ListPage>
  );
}
