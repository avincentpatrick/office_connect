import type { ReactNode } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ReceiptText } from "lucide-react";
import { useNavigate } from "react-router";
import { ApiError } from "../../api/http";
import { createClaim, reimbKeys, type WorkItem } from "../../api/reimbursement";
import { Button } from "../../components/Button/Button";
import { toast } from "../../components/Toast/toast-bus";
import { WorkItemRow } from "../../components/WorkItemRow/WorkItemRow";
import { ListPage } from "../../layouts/ListPage";
import { CLAIM_STATUS_TO_SEMANTIC, myWorkMeta, workItemTitle } from "./claim-status";
import { useMyWork } from "./use-claim";
import { stepPath } from "./wizard-steps";

/**
 * The module landing (spec §7 rule 3 — My Work is the home surface):
 * "Waiting on you" above "Your claims in flight". Ordering comes from the
 * server (urgency upstream); membership is holder/claimant-keyed there too.
 */
export function MyWorkPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const query = useMyWork();

  const start = useMutation({
    // Button-triggered create (never mutate-on-mount: StrictMode double-fires
    // effects and would mint two drafts). onSuccess seeds the cache and jumps
    // into the wizard.
    mutationFn: createClaim,
    onSuccess: (claim) => {
      queryClient.setQueryData(reimbKeys.claim(claim.id), claim);
      void queryClient.invalidateQueries({ queryKey: reimbKeys.myWork() });
      navigate(stepPath(claim.id, "trip"));
    },
    onError: (error) => {
      toast(
        error instanceof ApiError
          ? error.message
          : "Something went wrong. Please try again.",
      );
    },
  });

  const startButton = (
    <Button onClick={() => start.mutate()} loading={start.isPending}>
      Start a new claim
    </Button>
  );

  if (query.isError) {
    return (
      <ListPage
        title="My work"
        loading={false}
        isEmpty
        emptyState={{
          title: "My Work could not load",
          description:
            query.error instanceof ApiError
              ? query.error.message
              : "Something went wrong. Please try again.",
        }}
      />
    );
  }

  const data = query.data;
  const isEmpty =
    data !== undefined &&
    data.waiting_on_you.length === 0 &&
    data.in_flight.length === 0;

  return (
    <ListPage
      title="My work"
      filters={data && !isEmpty ? <div className="ml-auto">{startButton}</div> : undefined}
      loading={query.isPending}
      isEmpty={isEmpty}
      emptyState={{
        icon: ReceiptText,
        title: "Your travel claims will appear here",
        description:
          "File a local travel reimbursement and track it through approval.",
        action: startButton,
      }}
    >
      {data ? (
        <div className="flex flex-col gap-8">
          <WorkSection
            heading="Waiting on you"
            items={data.waiting_on_you}
            zeroState={
              <p className="text-base text-text-muted">
                Nothing waiting on you<span aria-hidden="true"> 🎉</span>
              </p>
            }
          />
          <WorkSection
            heading="Your claims in flight"
            items={data.in_flight}
            zeroState={
              <p className="text-base text-text-muted">No claims in flight.</p>
            }
          />
        </div>
      ) : null}
    </ListPage>
  );
}

function WorkSection({
  heading,
  items,
  zeroState,
}: {
  heading: string;
  items: WorkItem[];
  zeroState: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-2" aria-label={heading}>
      <h2 className="text-lg font-bold text-text">{heading}</h2>
      {items.length === 0 ? (
        zeroState
      ) : (
        <ul className="divide-y divide-border border-t border-b border-border">
          {items.map((item) => (
            <WorkItemRow
              key={item.id}
              refNo={item.ref_no}
              title={workItemTitle(item)}
              status={CLAIM_STATUS_TO_SEMANTIC[item.status]}
              statusLabel={item.status_label}
              to={`/reimbursement/claims/${item.id}`}
              meta={myWorkMeta(item)}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
