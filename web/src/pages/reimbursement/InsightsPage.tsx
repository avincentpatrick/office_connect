import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Lightbulb } from "lucide-react";
import { ApiError } from "../../api/http";
import {
  reimbKeys,
  setReasonPromoted,
  type ReasonRank,
  type ReturnInsights,
} from "../../api/reimbursement";
import { Button } from "../../components/Button/Button";
import { Callout } from "../../components/Callout/Callout";
import { RankedBarList } from "../../components/RankedBarList/RankedBarList";
import { ListPage } from "../../layouts/ListPage";
import { countPhrase, insightsSummary, rankMeta } from "./insights-copy";
import { useReturnInsights } from "./use-claim";

/**
 * Insights (R-8) — spec §11's comment-learning loop, and Objective 3 made
 * visible.
 *
 * Every return has recorded its reasons since R-4-screens; this is the first
 * surface that reads them back, and the "Promote" button is what makes the
 * system get better as it is used rather than merely observed.
 *
 * **Aggregates only, and the page holds up its end of that.** There is no
 * claimant on any row, no drill-down from a reason to a claim, and no place to
 * add one — spec §11 mirrors the §14.7 privacy pattern, and the server's scope
 * (you may only aggregate claims you could already open) is what makes it
 * enforceable rather than a promise in the copy.
 *
 * **Nothing here computes anything.** The counts, the trend, the window and the
 * order all arrive decided. The one piece of arithmetic on the whole screen is
 * a bar's width, inside `RankedBarList`, over data it was handed.
 *
 * Reachable by anyone, refused by the server (the R-6-clock doctrine, reaffirmed
 * at R-7-queue and R-7-board): the route carries no role gate, the nav item is
 * gated for discoverability only, and a 403 renders as the server's own
 * sentence.
 */

function PromoteButton({
  item,
  data,
  pending,
  onToggle,
}: {
  item: ReasonRank;
  data: ReturnInsights;
  pending: number | null;
  onToggle: (item: ReasonRank) => void;
}) {
  // Never offered to someone certain to be refused (R-4-screens' doctrine):
  // `can_promote` is the server's answer about an agency-wide grant, and
  // `promotable` is the row's own — a retired reason still ranks but can no
  // longer become a warning.
  if (!data.can_promote) return null;

  const blocked = !item.promoted && !item.promotable;
  return (
    <Button
      variant="secondary"
      className="min-h-11 px-3 py-1 text-sm"
      disabled={blocked}
      loading={pending === item.reason_id}
      onClick={() => onToggle(item)}
    >
      {item.promoted ? "Stop warning" : "Promote to pre-check"}
      <span className="sr-only"> — {item.label}</span>
    </Button>
  );
}

export function InsightsPage() {
  const query = useReturnInsights();
  const queryClient = useQueryClient();

  const toggle = useMutation({
    mutationFn: (item: ReasonRank) =>
      setReasonPromoted(item.reason_id, !item.promoted),
    onSuccess: (updated) => {
      queryClient.setQueryData(reimbKeys.insights(), updated);
      // THE line that makes spec §14's "no deploy" true: the wizard reads the
      // promoted flag off the return-reason taxonomy, so this invalidate is
      // what puts the warning in front of the next claimant. Refreshing only
      // this page would leave the promotion looking applied while changing
      // nothing a claimant sees.
      void queryClient.invalidateQueries({ queryKey: reimbKeys.returnReasons() });
    },
  });

  const denied = query.error instanceof ApiError && query.error.status === 403;

  if (query.isError) {
    return (
      <ListPage
        title="Insights"
        loading={false}
        isEmpty
        emptyState={{
          title: denied
            ? "Insights is not yours to see"
            : "Insights could not load",
          // The server's own words. It names the surface that DOES answer this
          // actor's question (their own claim trackers), and a paraphrase here
          // would be a second copy of a sentence to keep true.
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

  return (
    <ListPage
      title="Insights"
      loading={query.isPending}
      isEmpty={items.length === 0}
      emptyState={{
        icon: Lightbulb,
        title: "No claims have come back yet",
        description:
          "When an approver returns a claim, the reasons they picked are ranked here — and the ones that keep happening can be turned into a warning claimants see before they file.",
      }}
    >
      {data ? (
        <p className="text-sm text-text-muted">{insightsSummary(data)}</p>
      ) : null}

      {toggle.isError ? (
        <Callout status="blocked" title="That change was not saved" live="polite">
          {toggle.error instanceof ApiError
            ? toggle.error.message
            : "Something went wrong. Please try again."}
        </Callout>
      ) : null}

      {data ? (
        <RankedBarList
          label="Return reasons, most cited first"
          items={items.map((item) => ({
            id: item.reason_id,
            label: item.label,
            count: item.count,
            valueText: countPhrase(item),
            meta: rankMeta(item),
            action: (
              <PromoteButton
                item={item}
                data={data}
                pending={toggle.isPending ? toggle.variables.reason_id : null}
                onToggle={(row) => toggle.mutate(row)}
              />
            ),
          }))}
        />
      ) : null}

      {data?.can_promote ? (
        <p className="text-sm text-text-muted">
          A promoted reason appears as a warning on the last step of the claim
          wizard. It never blocks a submit — it tells a claimant what usually
          goes wrong, while they can still fix it.
        </p>
      ) : null}
    </ListPage>
  );
}
