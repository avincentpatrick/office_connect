/**
 * Nav gating + the NAV_GROUPS census (Stage D-1).
 *
 * `visibleNavItems` had no test at all until this file — it shipped at
 * R-2-shell and was re-gated onto permission codes at D-1, which is the point
 * at which "nobody has ever asserted this" stopped being acceptable.
 *
 * ⚠ `import.meta.env.DEV` is TRUE under vitest (mode is `test`, not
 * `production`), so the `devOnly` "UI foundation" item IS visible in every
 * assertion below. That is deliberate and asserted rather than worked around:
 * hiding it here would make the test disagree with the dev build it describes.
 */

import { describe, expect, it } from "vitest";
import { NAV_GROUPS, visibleNavItems, type NavItem } from "./nav";

const ALL_FLAGS_ON = { "module.reimbursement": true };

const STAFF = ["reimb.claim.create", "reimb.claim.read", "reimb.claim.submit"];
const ADMIN_OFFICER = [
  "reimb.claim.read",
  "reimb.claim.review",
  "reimb.claim.fms_update",
  "reimb.cash_advance.manage",
];

function labels(features: Record<string, boolean>, permissions: string[]): string[] {
  return visibleNavItems(features, permissions).map((i) => i.label);
}

describe("visibleNavItems", () => {
  it("hides a flagged item when its feature key is absent (fail-safe OFF)", () => {
    expect(labels({}, ADMIN_OFFICER)).toEqual(["Home", "UI foundation"]);
  });

  it("hides a flagged item when its feature key is explicitly false", () => {
    expect(labels({ "module.reimbursement": false }, ADMIN_OFFICER)).toEqual([
      "Home",
      "UI foundation",
    ]);
  });

  it("shows Reimbursement only to a holder of reimb.claim.read", () => {
    expect(labels(ALL_FLAGS_ON, ["reimb.claim.read"])).toContain("Reimbursement");
    expect(labels(ALL_FLAGS_ON, ["reimb.claim.create"])).not.toContain("Reimbursement");
  });

  it("shows Cash advances only to a holder of reimb.cash_advance.manage", () => {
    expect(labels(ALL_FLAGS_ON, STAFF)).not.toContain("Cash advances");
    expect(labels(ALL_FLAGS_ON, ADMIN_OFFICER)).toContain("Cash advances");
  });

  // Holding ANY ONE of the triple is exactly what `oversight_scope()` needs, so
  // each is tested alone — an AND bug would pass a test that granted all three.
  it.each([
    ["reimb.claim.review"],
    ["reimb.claim.fms_update"],
    ["reimb.claim.approve"],
  ])("reveals the oversight surfaces to a holder of %s alone", (perm) => {
    const shown = labels(ALL_FLAGS_ON, [perm]);
    expect(shown).toContain("Claim queue");
    expect(shown).toContain("Pipeline board");
    expect(shown).toContain("Insights");
  });

  it("hides the oversight surfaces from a plain traveller", () => {
    const shown = labels(ALL_FLAGS_ON, STAFF);
    expect(shown).not.toContain("Claim queue");
    expect(shown).not.toContain("Pipeline board");
    expect(shown).not.toContain("Insights");
  });

  it("hides every module from a grant-less user, even with the flag ON", () => {
    // The common case after R-9: the flag says the module exists, the empty
    // grant list says it is not theirs. Before D-1 this user was shown a
    // Reimbursement link that 403s on all 32 module routes.
    expect(labels(ALL_FLAGS_ON, [])).toEqual(["Home", "UI foundation"]);
  });

  it("keeps NAV_GROUPS declaration order", () => {
    expect(
      labels(ALL_FLAGS_ON, [
        ...ADMIN_OFFICER,
        "reimb.claim.approve",
        "activity.calendar.read",
      ]),
    ).toEqual([
      "Home",
      "Reimbursement",
      "Cash advances",
      "Claim queue",
      "Pipeline board",
      "Insights",
      "Calendar",
      "UI foundation",
    ]);
  });

  it("shows the Calendar with NO module flag, but only to a permission holder", () => {
    // The first nav item gated on a permission and NOT on a feature flag. Both
    // halves matter: flags OFF must not hide it (it is a core surface), and a
    // grant-less user must not see it (it is still gated).
    expect(labels({}, ["activity.calendar.read"])).toContain("Calendar");
    expect(labels(ALL_FLAGS_ON, STAFF)).not.toContain("Calendar");
  });
});

/**
 * The census. Same posture as `tests/test_reimb_authz_census.py`: the risk is
 * not a wrong row, it is a MISSING one — an item added tomorrow with no
 * `requiredPermissions` is silently openable by everyone, and absence never
 * fails a test. Unlike the backend census this needs no app introspection,
 * because NAV_GROUPS is already an enumerable array.
 *
 * `rule` is a cross-reference, not an assertion: a browser test cannot check
 * the server. What it CAN do is make "which server rule does this mirror?" a
 * required field on every future nav item. This file proves the map is
 * complete; the backend suite proves the territory matches it.
 */
interface CensusRow {
  to: string;
  flag: string | null;
  permissions: string[] | null;
  /** The server rule this item's gate mirrors. Never empty. */
  rule: string;
}

const NAV_CENSUS: CensusRow[] = [
  {
    to: "/",
    flag: null,
    permissions: null,
    rule: "none — the landing is reachable by any authenticated session",
  },
  {
    to: "/reimbursement",
    flag: "module.reimbursement",
    permissions: ["reimb.claim.read"],
    rule: "api/my_work.py — require_permission('reimb.claim.read')",
  },
  {
    to: "/reimbursement/cash-advances",
    flag: "module.reimbursement",
    permissions: ["reimb.cash_advance.manage"],
    rule: "api/cash_advances.py — deps.can_read_cash_advance / CA_OWNER_OR_SCOPED",
  },
  {
    to: "/reimbursement/queue",
    flag: "module.reimbursement",
    permissions: ["reimb.claim.review", "reimb.claim.fms_update", "reimb.claim.approve"],
    rule: "services/queue.py — oversight_scope(); 403 queue_not_permitted when empty",
  },
  {
    to: "/reimbursement/board",
    flag: "module.reimbursement",
    permissions: ["reimb.claim.review", "reimb.claim.fms_update", "reimb.claim.approve"],
    rule: "services/queue.py — oversight_scope() (api-standards §9g)",
  },
  {
    to: "/reimbursement/insights",
    flag: "module.reimbursement",
    permissions: ["reimb.claim.review", "reimb.claim.fms_update", "reimb.claim.approve"],
    rule: "services/queue.py — oversight_scope(); the scope IS the privacy boundary (§9h)",
  },
  {
    to: "/calendar",
    flag: null,
    permissions: ["activity.calendar.read"],
    rule:
      "core/api/calendar.py — require_permission('activity.calendar.read'); " +
      "each source then applies its OWN scope rule, censused in " +
      "tests/test_calendar_sources.py (api-standards §9k)",
  },
  {
    to: "/ui-foundation",
    flag: null,
    permissions: null,
    rule: "none — devOnly, statically eliminated from production builds",
  },
];

describe("NAV_GROUPS census", () => {
  const items: NavItem[] = NAV_GROUPS.flatMap((g) => g.items);

  it("accounts for every NAV_GROUPS item", () => {
    // A nav item added without a census row fails HERE, with its path in the
    // message — the whole reason this block exists.
    expect(items.map((i) => i.to).sort()).toEqual(NAV_CENSUS.map((r) => r.to).sort());
  });

  it("matches each item's declared gates", () => {
    for (const row of NAV_CENSUS) {
      const item = items.find((i) => i.to === row.to);
      expect(item, `no nav item for ${row.to}`).toBeDefined();
      expect(item!.requiredModule ?? null, `flag for ${row.to}`).toEqual(row.flag);
      expect(item!.requiredPermissions ?? null, `permissions for ${row.to}`).toEqual(
        row.permissions,
      );
    }
  });

  it("names the server rule each nav item mirrors", () => {
    for (const row of NAV_CENSUS) {
      expect(row.rule.trim(), `census row ${row.to} has no server rule`).not.toBe("");
    }
  });

  it("hides every gated item from a grant-less user with all flags ON", () => {
    const shown = new Set(visibleNavItems(ALL_FLAGS_ON, []).map((i) => i.to));
    for (const row of NAV_CENSUS.filter((r) => r.permissions !== null)) {
      expect(shown.has(row.to), `${row.to} leaked to a grant-less user`).toBe(false);
    }
  });
});
