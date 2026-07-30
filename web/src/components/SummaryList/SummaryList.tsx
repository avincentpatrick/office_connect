import type { ReactNode } from "react";
import { Link } from "react-router";
import { cx } from "../../lib/cx";

export interface SummaryListRow {
  key: string;
  value: ReactNode;
  /** Optional per-row "Change" link back into the wizard step. */
  action?: {
    label: string;
    to: string;
    /** Screen-reader context suffix, e.g. "purpose" → "Change purpose". */
    visuallyHidden: string;
  };
}

/**
 * ui-standards §3.15 (R-2-wizard) — GOV.UK check-your-answers summary list:
 * `<dl>` of key/value rows with optional Change links. Empty values render
 * "Not provided" (muted) — never a blank `<dd>`.
 */
export function SummaryList({
  rows,
  className,
}: {
  rows: SummaryListRow[];
  className?: string;
}) {
  return (
    <dl className={cx("divide-y divide-border", className)}>
      {rows.map((row) => (
        <div
          key={row.key}
          className="flex flex-col gap-1 py-2 sm:grid sm:grid-cols-[1fr_2fr_auto] sm:items-baseline sm:gap-4"
        >
          <dt className="text-sm font-medium text-text-muted">{row.key}</dt>
          <dd className="text-base text-text">
            {row.value === null || row.value === undefined || row.value === "" ? (
              <span className="text-text-muted">Not provided</span>
            ) : (
              row.value
            )}
          </dd>
          {row.action ? (
            <dd>
              <Link
                to={row.action.to}
                className="text-base text-link underline"
                aria-label={`${row.action.label} ${row.action.visuallyHidden}`}
              >
                {row.action.label}
              </Link>
            </dd>
          ) : null}
        </div>
      ))}
    </dl>
  );
}
