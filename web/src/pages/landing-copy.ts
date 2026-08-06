/**
 * Landing copy that encodes a RULE, extracted so it can be asserted rather than
 * buried in JSX (the `reimbursement/insights-copy.ts` precedent — "the copy is
 * where a surface tells the truth or does not").
 *
 * Two of these sentences are load-bearing: the refusal has to name the surfaces
 * that DO answer the question (R-9's doctrine, api-standards §9f), and the
 * no-access state has to tell the user the right thing to do next — which is
 * reload, not sign out.
 */

import type { NavItem } from "../app/nav";

/**
 * The front door does not list itself.
 *
 * Lives here rather than in the matcher because this is a property of the
 * LANDING, not of navigation: when the query bar is eventually lifted into the
 * App shell, `/` becomes a legitimate destination again and this rule stops
 * applying, while the matcher's contract does not change at all.
 */
export function openableItems(items: NavItem[]): NavItem[] {
  return items.filter((item) => item.to !== "/");
}

/** Cap the echoed query so a pasted paragraph cannot own the layout. */
export function truncateQuery(query: string, max = 60): string {
  const trimmed = query.trim();
  return trimmed.length <= max ? trimmed : `${trimmed.slice(0, max)}…`;
}

/**
 * The one sentence in the polite live region.
 *
 * Idle announces nothing — a live region that fires on page load is noise. The
 * refusal names what the user CAN open in the same breath as the refusal, which
 * is the half of R-9's doctrine that is easy to drop.
 */
export function matchStatusText(query: string, count: number): string {
  const shown = truncateQuery(query);
  if (shown === "") return "";
  if (count === 0) return `Nothing matches “${shown}”. Here is everything you can open.`;
  const noun = count === 1 ? "match" : "matches";
  return `${count} ${noun} for “${shown}”. Choose one below.`;
}

export interface LandingEmptyState {
  title: string;
  description: string;
}

/**
 * Which no-access sentence is TRUE for this user.
 *
 * ui-standards §4's R-7-queue rule — an empty state must answer the question
 * that was asked. "You have nothing" and "nothing is switched on" are different
 * facts with different next actions, and getting them backwards sends someone to
 * an administrator who cannot help.
 *
 * ⚠ It says **reload this page**, never "sign out and back in": a grant lands on
 * the NEXT REQUEST through the version-keyed permission cache (api-standards
 * §7). Telling a user to re-login would be the same class of wrong-but-plausible
 * copy that §3.14 exists to prevent.
 */
export function emptyLandingState(permissions: string[], email?: string): LandingEmptyState {
  if (permissions.length === 0) {
    const quote = email ? ` Quote your sign-in name, ${email}.` : "";
    return {
      title: "You do not have access to any modules yet.",
      description:
        "Access is granted per person by an administrator." +
        `${quote}` +
        " Once it is granted, reload this page — you do not need to sign out.",
    };
  }
  return {
    title: "No modules are switched on right now.",
    description:
      "You have access, but no module is currently enabled for your organisation. " +
      "Try again shortly, or ask IT whether a module is being switched on.",
  };
}
