import type { ReactNode } from "react";
import { EmptyState, type EmptyStateProps } from "../components/EmptyState/EmptyState";
import { Skeleton } from "../components/Skeleton/Skeleton";

export interface ListPageProps {
  title: string;
  /** Filter row above the list. */
  filters?: ReactNode;
  loading: boolean;
  isEmpty: boolean;
  /** Mandatory (§3.11): what will appear + the next action. */
  emptyState: EmptyStateProps;
  /** Pagination slot — envelope convention arrives Stage D; lists are ?limit=&offset= for now. */
  pagination?: ReactNode;
  children?: ReactNode;
}

/** ui-standards §4.2 — List page: filter row → content → pagination; empty state + skeleton mandatory. */
export function ListPage({
  title,
  filters,
  loading,
  isEmpty,
  emptyState,
  pagination,
  children,
}: ListPageProps) {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-bold text-text">{title}</h1>
      {filters ? <div className="flex flex-wrap items-end gap-2">{filters}</div> : null}
      {loading ? (
        <div role="status" aria-busy="true" className="flex flex-col gap-2">
          <span className="sr-only">Loading…</span>
          <Skeleton variant="row" />
          <Skeleton variant="row" />
          <Skeleton variant="row" />
        </div>
      ) : isEmpty ? (
        <EmptyState {...emptyState} />
      ) : (
        <>
          {children}
          {pagination ? <nav aria-label="Pagination">{pagination}</nav> : null}
        </>
      )}
    </div>
  );
}
