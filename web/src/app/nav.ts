import type { LucideIcon } from "lucide-react";
import {
  Banknote,
  CalendarDays,
  Home,
  Inbox,
  LayoutGrid,
  Lightbulb,
  Palette,
  ReceiptText,
} from "lucide-react";
import { isFeatureOn } from "../lib/flags";

/**
 * NAV_GROUPS — the single source for navigation (master-plan §1.3), consumed by
 * the App shell's top bar AND the Stage D-1 landing page. Items render only
 * when enabled AND permitted, so a new surface is discoverable, matchable and
 * listed the moment its row is added here.
 *
 * Gating is on **permission codes** from `/auth/me` (ui-standards §7, Stage
 * D-1). `requiredRoles` was deleted, not deprecated: authorization is on
 * permission strings everywhere else, the oversight items now carry the
 * server's own `OVERSIGHT_PERMS` verbatim, and `me.roles` is a login-time
 * snapshot that is never rewritten — so the old gate was not merely coarse, it
 * was out of date until the user signed in again.
 *
 * This is still **discoverability, not authorization**: every route stays
 * reachable and the server refuses. What changed is that the client's guess now
 * matches the server's rule instead of approximating it. The nav deliberately
 * does NOT narrow by org SCOPE — a scoped Admin Officer can genuinely open the
 * queue, they just see less inside it, and shipping scope to the client would
 * mean shipping the org tree to the client.
 *
 * Every item is accounted for by the census in `nav.test.ts`, which requires a
 * declared gate and the name of the server rule it mirrors. An item added
 * without a row FAILS the suite rather than being silently openable.
 */
export interface NavItem {
  label: string;
  to: string;
  icon: LucideIcon;
  /** Feature-flag key that must be ON (absent = OFF). */
  requiredModule?: string;
  /** Show only when the user holds AT LEAST ONE of these codes (OR semantics). */
  requiredPermissions?: string[];
  /** One plain-language line. Rendered on the landing, not in the top bar. */
  description?: string;
  /** Query-bar intent seeds (`app/nav-match.ts`). */
  intentKeywords?: string[];
  /** Development builds only (statically eliminated from production). */
  devOnly?: boolean;
}

export interface NavGroup {
  label?: string;
  items: NavItem[];
}

/**
 * The oversight permissions, mirroring
 * `modules/reimbursement/services/queue.py::OVERSIGHT_PERMS` verbatim. Holding
 * ANY one of them is exactly equivalent to `oversight_scope()` returning a
 * non-empty scope, which is what the queue / board / insights endpoints require
 * (api-standards §9f). Pinned server-side by
 * `tests/test_auth_me_permissions.py::test_the_oversight_triple_is_what_the_nav_mirrors`,
 * which names this file in its failure message.
 */
const OVERSIGHT_PERMISSIONS = [
  "reimb.claim.review",
  "reimb.claim.fms_update",
  "reimb.claim.approve",
];

export const NAV_GROUPS: NavGroup[] = [
  {
    items: [
      {
        label: "Home",
        to: "/",
        icon: Home,
        description: "Find a page, or see everything you can open.",
        intentKeywords: ["home", "start"],
      },
      {
        label: "Reimbursement",
        to: "/reimbursement",
        icon: ReceiptText,
        requiredModule: "module.reimbursement",
        // `staff` holds this globally so a traveller can read their own claim
        // from anywhere in the org tree — which is exactly why it can gate the
        // MODULE but never a list of other people's work (api-standards §9f).
        requiredPermissions: ["reimb.claim.read"],
        description: "File a local travel claim and track your own work.",
        intentKeywords: ["travel", "claim", "reimbursement", "per diem"],
      },
      {
        // R-6-clock.
        label: "Cash advances",
        to: "/reimbursement/cash-advances",
        icon: Banknote,
        requiredModule: "module.reimbursement",
        requiredPermissions: ["reimb.cash_advance.manage"],
        description: "Advances and their liquidation countdowns.",
        intentKeywords: ["cash advance", "liquidation", "deadline", "COA"],
      },
      {
        // R-7-queue.
        label: "Claim queue",
        to: "/reimbursement/queue",
        icon: Inbox,
        requiredModule: "module.reimbursement",
        requiredPermissions: OVERSIGHT_PERMISSIONS,
        description: "Claims you oversee, including anything stuck with FMS.",
        intentKeywords: ["queue", "FMS", "follow up", "stuck", "overdue"],
      },
      {
        // R-7-board. Spec §9.6 calls this the Director/Admin DEFAULT view.
        label: "Pipeline board",
        to: "/reimbursement/board",
        icon: LayoutGrid,
        requiredModule: "module.reimbursement",
        requiredPermissions: OVERSIGHT_PERMISSIONS,
        description: "Where the money is, by stage, with column totals.",
        intentKeywords: [
          "board", "pipeline", "overview", "totals", "how much", "where",
        ],
      },
      {
        // R-8. Spec §9.2 puts Insights on Desktop for the Admin/Director audience.
        label: "Insights",
        to: "/reimbursement/insights",
        icon: Lightbulb,
        requiredModule: "module.reimbursement",
        requiredPermissions: OVERSIGHT_PERMISSIONS,
        description: "Why claims come back, and what to pre-check.",
        intentKeywords: [
          "insights", "returns", "why", "reasons", "learning", "pre-check",
        ],
      },
      {
        // Stage D-2. NOT flag-gated: the Calendar is a CORE surface like
        // /directory and /audit, and there is no `module.calendar` to gate on —
        // inventing one would ship a flag for a module that does not exist. The
        // module CONTRIBUTIONS inside it are flag-gated per source instead
        // (api-standards §9k), which is why an OFF module leaves no trace here.
        label: "Calendar",
        to: "/calendar",
        icon: CalendarDays,
        requiredPermissions: ["activity.calendar.read"],
        description: "What is happening, and what is due.",
        intentKeywords: [
          "calendar", "activities", "schedule", "when", "upcoming", "agenda",
          "deadline", "due", "events",
        ],
      },
      {
        label: "UI foundation",
        to: "/ui-foundation",
        icon: Palette,
        description: "The component inventory, as built.",
        devOnly: true,
      },
    ],
  },
];

/**
 * Whether one item is visible to this user. Extracted so a grouped variant is
 * four lines the day a LABELLED group first exists (Stage H's Reports) —
 * today's single unlabeled group makes a grouped render byte-identical to a
 * flat one, so shipping `visibleNavGroups` now would ship a dead export.
 */
function isVisible(
  item: NavItem,
  features: Record<string, boolean>,
  permissions: string[],
): boolean {
  if (item.devOnly && !import.meta.env.DEV) return false;
  if (item.requiredModule && !isFeatureOn(features, item.requiredModule)) return false;
  if (item.requiredPermissions && !item.requiredPermissions.some((p) => permissions.includes(p)))
    return false;
  return true;
}

/** Everything this user can open, in declaration order. */
export function visibleNavItems(
  features: Record<string, boolean>,
  permissions: string[],
): NavItem[] {
  return NAV_GROUPS.flatMap((group) => group.items).filter((item) =>
    isVisible(item, features, permissions),
  );
}
