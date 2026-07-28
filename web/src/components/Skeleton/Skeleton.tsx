import { cx } from "../../lib/cx";

/**
 * Loading placeholder (ui-standards §3.12) — mandatory on every list/detail
 * while loading. Blocks are aria-hidden; wrap a loading region with
 * role="status" (see PageSkeleton) so the state is announced once.
 */
export function Skeleton({
  variant = "block",
  className,
}: {
  variant?: "block" | "row";
  className?: string;
}) {
  return (
    <div
      aria-hidden="true"
      className={cx(
        "animate-pulse rounded-md bg-surface",
        variant === "block" ? "h-24" : "h-6",
        className,
      )}
    />
  );
}

/** Full-page loading state (config/auth bootstrap, route guards). */
export function PageSkeleton({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" aria-busy="true" className="mx-auto flex max-w-3xl flex-col gap-4 p-6">
      <span className="sr-only">{label}…</span>
      <Skeleton variant="row" className="w-1/3" />
      <Skeleton />
      <Skeleton />
    </div>
  );
}
