import type { ReactNode } from "react";
import { cx } from "../../lib/cx";

/**
 * ui-standards §3.23 — a ranked list of counts, largest first, with a bar
 * showing each row's share of the largest.
 *
 * Spec §9.2's Insights row names a "ranked return-reasons bar list", and
 * nothing in the inventory covered it. Built to the **CountdownRing doctrine**
 * (§3.22), because the two components have the same failure mode: a graphic
 * that encodes a quantity where only sighted users can read it.
 *
 * 1. **The bar is decoration; the text is the information.** Every bar is
 *    `aria-hidden`, and every fact it depicts is real text on the same row. A
 *    screen reader gets "Missing official receipt, 12 returns", not a
 *    description of a rectangle.
 * 2. **It renders a server value and derives nothing but width.** The only
 *    arithmetic here is `count / max`, which decides how wide a div is and
 *    nothing else. No totals, no percentages, no ranking — the order arrives
 *    sorted, because a list that re-sorted client-side would disagree with the
 *    server the moment either changed.
 * 3. **A bar is a SHARE OF THE LARGEST ROW, never of a total.** Scaling to a
 *    sum would render each bar as a percentage of all returns, which is a RATE
 *    — a number this data cannot support (the denominator is submissions, not
 *    returns) and a claim nobody made.
 * 4. **Zero is a row, not a gap.** A row that has fallen to 0 keeps its place
 *    and renders no bar at all; a hairline "almost nothing" bar would be
 *    indistinguishable from a real small value.
 *
 * Semantic `<ol>`: the order IS the content, which is exactly what an ordered
 * list means, and it gives screen readers "3 of 7" for free.
 */

export interface RankedBarItem {
  /** Stable key — the row's own id, never the array index. */
  id: number | string;
  /** The primary label. Sentence case, no jargon (§5). */
  label: string;
  /** The quantity the bar depicts. */
  count: number;
  /**
   * The row's own words for its number — what a screen reader hears and a
   * sighted user reads. Required, because a bare integer beside a bar is
   * exactly the "meaning rides the graphic" failure this component prevents.
   */
  valueText: string;
  /** Optional secondary line (a trend phrase, a category). */
  meta?: string;
  /** Optional per-row control, right-aligned. */
  action?: ReactNode;
}

export interface RankedBarListProps {
  /** Pre-sorted, largest first. This component does not re-order. */
  items: RankedBarItem[];
  /** Accessible name for the list (`aria-label` on the `<ol>`). */
  label: string;
  className?: string;
}

export function RankedBarList({ items, label, className }: RankedBarListProps) {
  // The scale, from the data as given. `max` of an empty list is -Infinity, and
  // a zero max would divide by zero — both are guarded to 1, which renders
  // every bar empty and is the honest picture of "nothing to compare".
  const max = Math.max(1, ...items.map((item) => item.count));

  return (
    <ol aria-label={label} className={cx("flex flex-col gap-3", className)}>
      {items.map((item) => (
        <li key={item.id} className="flex flex-col gap-1">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <span className="text-base font-medium text-text">{item.label}</span>
            <span className="text-base tabular-nums text-text">
              {item.valueText}
            </span>
          </div>
          {/* Decoration only — everything it depicts is in the row above. */}
          <div
            aria-hidden="true"
            className="h-2 w-full overflow-hidden rounded-sm border border-border bg-surface"
          >
            {item.count > 0 ? (
              <div
                className="h-full rounded-sm bg-brand"
                style={{ width: `${Math.round((item.count / max) * 100)}%` }}
              />
            ) : null}
          </div>
          {item.meta || item.action ? (
            <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
              {item.meta ? (
                <span className="text-sm text-text-muted">{item.meta}</span>
              ) : (
                <span />
              )}
              {item.action}
            </div>
          ) : null}
        </li>
      ))}
    </ol>
  );
}
