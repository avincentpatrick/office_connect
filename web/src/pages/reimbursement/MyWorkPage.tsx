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
import { CashAdvanceCard } from "./CashAdvanceCard";
import { LiquidateAction } from "./LiquidateAction";
import {
  CLAIM_STATUS_TO_SEMANTIC,
  SLA_STATE_LABEL,
  SLA_STATE_TO_SEMANTIC,
  myWorkMeta,
  workItemTitle,
} from "./claim-status";
import { useCashAdvances, useMyWork } from "./use-claim";
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
            urgency
            zeroState={
              <p className="text-base text-text-muted">
                Nothing waiting on you<span aria-hidden="true"> 🎉</span>
              </p>
            }
          />
          <CashAdvanceSection />
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

/**
 * Spec §6.2: the 30-day countdown "shows on every liquidation surface from CA
 * creation" — and the module home is the first surface a traveller sees.
 *
 * Placed BETWEEN "Waiting on you" and "Your claims in flight" deliberately: an
 * unliquidated advance IS waiting on you, but it is not a claim and does not
 * belong in a list of claim rows. Below the inbox, above the tracker.
 *
 * Renders nothing at all when there are no advances (the common case, since
 * most travellers never take one) — an empty "Your cash advances" heading on
 * every visit would be permanent furniture reporting nothing.
 */
function CashAdvanceSection() {
  const query = useCashAdvances();
  const advances = query.data ?? [];
  // Settled advances are closed records; the clock section is about live ones.
  const live = advances.filter((a) => a.status !== "settled");
  if (query.isPending || live.length === 0) return null;

  return (
    <section className="flex flex-col gap-2" aria-label="Your cash advances">
      <h2 className="text-lg font-bold text-text">Your cash advances</h2>
      <p className="text-sm text-text-muted">
        A travel cash advance must be liquidated within the COA deadline shown.
      </p>
      <ul className="flex flex-col gap-3">
        {live.map((advance) => (
          <li key={advance.id}>
            {/* The card counts down; this is what ANSWERS it (R-6-liq-chain).
                The action lives with the advance, not in the New Claim wizard:
                the ring in front of the traveller is the moment spec §9.3
                step 1's "Liquidate that instead?" actually means something. */}
            <CashAdvanceCard
              advance={advance}
              actions={<LiquidateAction advance={advance} />}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}

function WorkSection({
  heading,
  items,
  zeroState,
  urgency = false,
}: {
  heading: string;
  items: WorkItem[];
  zeroState: ReactNode;
  /**
   * "Waiting on you" swaps the status chip for the SLA urgency chip (spec §9.2
   * — "urgency chips"): the section heading already says these are yours, so
   * the one chip is better spent on how late they are. Only when the server
   * says a row is slipping — an on-track row keeps its status.
   */
  urgency?: boolean;
}) {
  return (
    <section className="flex flex-col gap-2" aria-label={heading}>
      <h2 className="text-lg font-bold text-text">{heading}</h2>
      {items.length === 0 ? (
        zeroState
      ) : (
        <ul className="divide-y divide-border border-t border-b border-border">
          {items.map((item) => {
            const slipping =
              urgency &&
              (item.sla_state === "overdue" || item.sla_state === "due_soon");
            return (
              <WorkItemRow
                key={item.id}
                refNo={item.ref_no}
                title={workItemTitle(item)}
                status={
                  slipping
                    ? SLA_STATE_TO_SEMANTIC[item.sla_state!]
                    : CLAIM_STATUS_TO_SEMANTIC[item.status]
                }
                statusLabel={
                  slipping ? SLA_STATE_LABEL[item.sla_state!] : item.status_label
                }
                to={`/reimbursement/claims/${item.id}`}
                meta={myWorkMeta(item)}
              />
            );
          })}
        </ul>
      )}
    </section>
  );
}
