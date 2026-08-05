import type { LucideIcon } from "lucide-react";
import { Banknote, Home, Inbox, LayoutGrid, Palette, ReceiptText } from "lucide-react";
import { isFeatureOn } from "../lib/flags";

/**
 * NAV_GROUPS seed — the single source for navigation (master-plan §1.3). The
 * shape matches the Phase-3 landing concept (required_module + required_roles
 * + intent_keywords) so Stage D lifts it into the query bar unchanged. Items
 * render only when enabled AND permitted — no drift when a feature appears.
 *
 * UI gating uses feature flags + roles for now; a self-permissions endpoint is
 * a recorded deferral (ui-standards §7).
 */
export interface NavItem {
  label: string;
  to: string;
  icon: LucideIcon;
  /** Feature-flag key that must be ON (absent = OFF). */
  requiredModule?: string;
  /** Show only when the user has at least one of these role codes. */
  requiredRoles?: string[];
  /** Query-bar intent seeds (consumed in Stage D). */
  intentKeywords?: string[];
  /** Development builds only (statically eliminated from production). */
  devOnly?: boolean;
}

export interface NavGroup {
  label?: string;
  items: NavItem[];
}

export const NAV_GROUPS: NavGroup[] = [
  {
    items: [
      { label: "Home", to: "/", icon: Home, intentKeywords: ["home", "start"] },
      {
        label: "Reimbursement",
        to: "/reimbursement",
        icon: ReceiptText,
        requiredModule: "module.reimbursement",
        intentKeywords: ["travel", "claim", "reimbursement", "per diem"],
      },
      {
        // R-6-clock. Role-gated in the NAV only (discoverability, not
        // authorization — the server enforces reimb.cash_advance.manage).
        label: "Cash advances",
        to: "/reimbursement/cash-advances",
        icon: Banknote,
        requiredModule: "module.reimbursement",
        requiredRoles: ["admin_officer", "system_admin"],
        intentKeywords: ["cash advance", "liquidation", "deadline", "COA"],
      },
      {
        // R-7-queue. Role-gated in the NAV only, like Cash advances: the
        // server refuses anyone who oversees nobody, and hiding the link is
        // discoverability rather than a security boundary.
        label: "Claim queue",
        to: "/reimbursement/queue",
        icon: Inbox,
        requiredModule: "module.reimbursement",
        requiredRoles: ["admin_officer", "approver", "system_admin"],
        intentKeywords: ["queue", "FMS", "follow up", "stuck", "overdue"],
      },
      {
        // R-7-board. Spec §9.6 calls this the Director/Admin DEFAULT view, so
        // it sits beside the queue with the same role gating — which is
        // discoverability, not authorization: the server refuses anyone who
        // oversees nobody, and hiding a link is not a boundary.
        label: "Pipeline board",
        to: "/reimbursement/board",
        icon: LayoutGrid,
        requiredModule: "module.reimbursement",
        requiredRoles: ["admin_officer", "approver", "system_admin"],
        intentKeywords: [
          "board", "pipeline", "overview", "totals", "how much", "where",
        ],
      },
      { label: "UI foundation", to: "/ui-foundation", icon: Palette, devOnly: true },
    ],
  },
];

export function visibleNavItems(features: Record<string, boolean>, roles: string[]): NavItem[] {
  return NAV_GROUPS.flatMap((group) => group.items).filter((item) => {
    if (item.devOnly && !import.meta.env.DEV) return false;
    if (item.requiredModule && !isFeatureOn(features, item.requiredModule)) return false;
    if (item.requiredRoles && !item.requiredRoles.some((role) => roles.includes(role)))
      return false;
    return true;
  });
}
