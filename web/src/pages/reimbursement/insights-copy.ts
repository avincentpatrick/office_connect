import type { ReasonRank, ReturnInsights } from "../../api/reimbursement";
import { formatManilaDate } from "../../lib/format";

/**
 * Display rules for Insights (R-8, spec §11). Pure functions, unit-tested — the
 * `daysPhrase`/`boardMeta` precedent, and for the same reason: the copy is where
 * a surface tells the truth or does not, so it belongs somewhere it can be
 * asserted rather than inline in JSX.
 *
 * One rule runs through all of them: **a count of returns is never a rate.**
 * "12 returns" is a fact; "12% of claims" needs a denominator this surface does
 * not have (submissions, spec §13, Stage H). Nothing here divides anything.
 */

/** The row's own words for its number — never a bare integer beside a bar. */
export function countPhrase(item: ReasonRank): string {
  if (item.count === 0) return "None this period";
  return `${item.count} ${item.count === 1 ? "return" : "returns"}`;
}

/**
 * The trend, in words. Never an arrow glyph alone: a ▲ is unreadable to a
 * screen reader and ambiguous to everyone (is up good?), which is §6's
 * "meaning never rides a graphic" one step out from colour.
 *
 * `new` is deliberately distinct from `up` — "up from 0" describes a trend line
 * where a debut is a different event, and an Admin Officer reads them
 * differently: a spike in a familiar reason is a process problem, a brand-new
 * reason is usually a form or a circular that just changed.
 */
export function trendPhrase(item: ReasonRank): string {
  switch (item.trend) {
    case "new":
      return "New this period";
    case "up":
      return `Up from ${item.prior_count}`;
    case "down":
      return item.count === 0
        ? `Down from ${item.prior_count} — none this period`
        : `Down from ${item.prior_count}`;
    default:
      return item.prior_count === 0
        ? "None in either period"
        : `Unchanged from ${item.prior_count}`;
  }
}

/** The row's second line: the trend, and whether it is already a warning. */
export function rankMeta(item: ReasonRank): string {
  const parts = [trendPhrase(item)];
  if (item.promoted) parts.push("Shown as a warning at step 5");
  return parts.join(" · ");
}

/**
 * The page's one-line summary. Every number in it is the SERVER's — the window,
 * the date it opens on, and the count of returns inside it (api-standards §9g:
 * a bound the client cannot see is a bound the client will eventually
 * contradict).
 *
 * "returns" here counts PACKETS that came back, once each. The ranked rows
 * count returns CITING a reason, so they sum higher — two true numbers
 * answering different questions, and the header takes the one a person means.
 */
export function insightsSummary(data: ReturnInsights): string {
  const returns = `${data.total_returns} ${data.total_returns === 1 ? "return" : "returns"}`;
  return `${returns} in the last ${data.window_days} days, since ${formatManilaDate(data.period_start)}. Ranked by how often each reason was cited.`;
}
