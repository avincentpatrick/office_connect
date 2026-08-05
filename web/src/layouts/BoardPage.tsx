import type { ReactNode } from "react";
import { EmptyState, type EmptyStateProps } from "../components/EmptyState/EmptyState";
import { Skeleton } from "../components/Skeleton/Skeleton";

export interface BoardColumn {
  key: string;
  title: string;
  count?: number;
  /**
   * The column's money, ALREADY FORMATTED by the caller from a server-computed
   * 2-dp string. The layout never sees a number and never adds anything up
   * (tech-stack §4 hard prohibition).
   */
  total?: string;
  /** Shown under the cards — "Showing 20 of 137." when the column is capped. */
  footer?: ReactNode;
  children: ReactNode;
}

export interface BoardPageProps {
  title: string;
  columns: BoardColumn[];
  loading: boolean;
  /** True when EVERY column is empty — a per-column empty line is the caller's. */
  isEmpty: boolean;
  /** Mandatory (§3.11), like List page's: what will appear + the next action. */
  emptyState: EmptyStateProps;
}

/**
 * ui-standards §4.5 — Board page: pipeline columns of board cards; scrolls
 * horizontally on phones.
 *
 * **Template amendment (R-7-board):** gains `loading` + a mandatory
 * `emptyState`, matching List page. §3 makes a skeleton and an empty state
 * mandatory on every list, and api-standards §9f's own words are that a board
 * is a list with headers — an un-skeletoned board flashes three empty columns
 * on every load, which reads as "there is no work" rather than "not yet".
 *
 * The count and the money sit in a `<p>` BELOW the `<h2>`, not inside it: a
 * screen-reader heading list has to read "With FMS", not
 * "With FMS 24 ₱1,284,300.00".
 */
export function BoardPage({
  title,
  columns,
  loading,
  isEmpty,
  emptyState,
}: BoardPageProps) {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-bold text-text">{title}</h1>
      {loading ? (
        <div role="status" aria-busy="true" className="flex gap-4 overflow-x-auto pb-2">
          <span className="sr-only">Loading…</span>
          {columns.map((column) => (
            <div key={column.key} className="flex min-w-64 flex-1 flex-col gap-2">
              <Skeleton variant="row" />
              <Skeleton variant="block" />
            </div>
          ))}
        </div>
      ) : isEmpty ? (
        <EmptyState {...emptyState} />
      ) : (
        <div className="flex gap-4 overflow-x-auto pb-2">
          {columns.map((column) => (
            <section key={column.key} className="flex min-w-64 flex-1 flex-col gap-2">
              <h2 className="text-sm font-bold text-text-muted">{column.title}</h2>
              {column.count !== undefined ? (
                <p className="text-sm text-text-muted">
                  {column.count} {column.count === 1 ? "claim" : "claims"}
                  {column.total ? ` · ${column.total}` : null}
                </p>
              ) : null}
              <div className="flex flex-col gap-2 rounded-md bg-surface p-2">
                {column.children}
              </div>
              {column.footer ? (
                <p className="text-xs text-text-muted">{column.footer}</p>
              ) : null}
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
