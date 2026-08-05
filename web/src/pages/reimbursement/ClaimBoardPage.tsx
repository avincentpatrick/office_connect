import { LayoutGrid } from "lucide-react";
import { ApiError } from "../../api/http";
import type { ClaimBoardColumn } from "../../api/reimbursement";
import { PipelineCard } from "../../components/PipelineCard/PipelineCard";
import { BoardPage, type BoardColumn } from "../../layouts/BoardPage";
import { formatPeso } from "../../lib/format";
import { boardMeta, queueChip, workItemTitle } from "./claim-status";
import { useClaimBoard } from "./use-claim";

/**
 * The pipeline board (R-7-board) — spec §9.6, "the module's public face".
 *
 * My Work answers "what is mine" and the Claim queue answers "what is stuck".
 * This answers the question a bureau chief asks from across the room: **how
 * much is where.** So the headline of every column is a count and a peso total,
 * and the cards below it are context — three columns of at most `card_limit`
 * each, not a list.
 *
 * Reachable by anyone, like the queue and the cash-advance register: the SERVER
 * decides who oversees whom, and a 403 renders as its own explanation rather
 * than a blank page.
 *
 * Nothing here adds anything up. `count` and `total` are the whole column,
 * computed in SQL over rows this page never sees, and re-deriving either from
 * the visible cards would under-report the bureau's exposure by exactly the
 * amount that did not fit on screen — while looking entirely correct.
 */

/** Per-column empty copy: each answers the question that column asks. */
const EMPTY_COLUMN: Record<ClaimBoardColumn["key"], string> = {
  in_bureau: "Nothing is waiting on a desk.",
  with_fms: "Nothing is with FMS.",
  done: "Nothing has closed in this period.",
};

export function ClaimBoardPage() {
  const query = useClaimBoard();
  const denied = query.error instanceof ApiError && query.error.status === 403;
  const data = query.data;

  if (query.isError) {
    return (
      <BoardPage
        title="Pipeline board"
        columns={[]}
        loading={false}
        isEmpty
        emptyState={{
          title: denied
            ? "This board is not yours to see"
            : "The board could not load",
          // The server's own words. It names My Work as the surface that DOES
          // answer this actor's question (§9.1 principle 4), and paraphrasing
          // it here would be a second copy to keep true.
          description:
            query.error instanceof ApiError
              ? query.error.message
              : "Something went wrong. Please try again.",
        }}
      />
    );
  }

  const columns: BoardColumn[] = (data?.columns ?? []).map((column) => ({
    key: column.key,
    // The Done column says out loud that it is a window, using the SERVER's
    // number — an unqualified "Done" beside a peso total reads as all-time,
    // which it deliberately is not.
    title:
      column.key === "done" && data
        ? `${column.label} · last ${data.done_window_days} days`
        : column.label,
    count: column.count,
    total: formatPeso(column.total),
    footer:
      column.count > column.items.length
        ? `Showing ${column.items.length} of ${column.count}. Open the claim queue for the rest.`
        : undefined,
    children:
      column.items.length === 0 ? (
        <p className="p-2 text-xs text-text-muted">{EMPTY_COLUMN[column.key]}</p>
      ) : (
        column.items.map((item) => {
          const chip = queueChip(item);
          return (
            <PipelineCard
              key={item.id}
              refNo={item.ref_no ?? "—"}
              title={workItemTitle(item)}
              status={chip.status}
              statusLabel={chip.label}
              meta={boardMeta(item)}
              to={`/reimbursement/claims/${item.id}`}
            />
          );
        })
      ),
  }));

  return (
    <BoardPage
      title="Pipeline board"
      columns={columns}
      loading={query.isPending}
      // Only when the whole board is empty. A single empty column keeps its
      // header — "₱0.00 is with FMS" is an answer, and hiding the column would
      // make the chief wonder whether it failed to load.
      isEmpty={!!data && data.columns.every((column) => column.count === 0)}
      emptyState={{
        icon: LayoutGrid,
        title: "Nothing is in the pipeline",
        description:
          "Claims you oversee appear here once they are submitted, grouped by where they are.",
      }}
    />
  );
}
