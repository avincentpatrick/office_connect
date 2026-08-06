import { describe, expect, it } from "vitest";
import { Home, ReceiptText } from "lucide-react";
import type { NavItem } from "../app/nav";
import {
  emptyLandingState,
  matchStatusText,
  openableItems,
  truncateQuery,
} from "./landing-copy";

const ITEMS: NavItem[] = [
  { label: "Home", to: "/", icon: Home },
  { label: "Reimbursement", to: "/reimbursement", icon: ReceiptText },
];

describe("openableItems", () => {
  it("drops Home — the front door does not list itself", () => {
    expect(openableItems(ITEMS).map((i) => i.to)).toEqual(["/reimbursement"]);
  });

  it("drops nothing else", () => {
    expect(openableItems([ITEMS[1]])).toHaveLength(1);
  });
});

describe("truncateQuery", () => {
  it("leaves a short query alone and trims it", () => {
    expect(truncateQuery("  travel  ")).toBe("travel");
  });

  it("caps a pasted paragraph so it cannot own the layout", () => {
    const long = "a".repeat(200);
    expect(truncateQuery(long)).toHaveLength(61); // 60 + the ellipsis
    expect(truncateQuery(long).endsWith("…")).toBe(true);
  });
});

describe("matchStatusText", () => {
  it("announces nothing while idle", () => {
    expect(matchStatusText("", 0)).toBe("");
    expect(matchStatusText("   ", 0)).toBe("");
  });

  it("uses the singular for one match", () => {
    expect(matchStatusText("queue", 1)).toBe("1 match for “queue”. Choose one below.");
  });

  it("uses the plural for several", () => {
    expect(matchStatusText("claim", 3)).toBe("3 matches for “claim”. Choose one below.");
  });

  it("refuses AND names what the user can open", () => {
    // R-9's doctrine: a refusal names the surface that DOES answer the
    // question. Dropping the second sentence is the easy mistake.
    expect(matchStatusText("zzz", 0)).toBe(
      "Nothing matches “zzz”. Here is everything you can open.",
    );
  });

  it("echoes an awkward query literally rather than mangling it", () => {
    expect(matchStatusText('<b>"x"</b>', 0)).toContain('<b>"x"</b>');
  });
});

describe("emptyLandingState", () => {
  it("blames nobody's grants when the user holds none", () => {
    const state = emptyLandingState([], "someone@doh.gov");
    expect(state.title).toBe("You do not have access to any modules yet.");
    expect(state.description).toContain("someone@doh.gov");
  });

  it("says the modules are switched off when the user DOES hold permissions", () => {
    // Different fact, different next action: this is the flags-OFF case, and
    // sending this person to an administrator would waste both their time.
    const state = emptyLandingState(["reimb.claim.read"]);
    expect(state.title).toBe("No modules are switched on right now.");
    expect(state.description).toContain("no module is currently enabled");
  });

  it("tells the user to reload, and never to sign in again", () => {
    // A grant lands on the NEXT REQUEST through the version-keyed cache
    // (api-standards §7). "Sign out and back in" would be plausible, wrong, and
    // exactly the class of copy defect ui-standards §3.14 exists to prevent —
    // so the copy goes further and says outright that it is unnecessary.
    const state = emptyLandingState([], "someone@doh.gov");
    expect(state.description).toContain("reload this page");
    expect(state.description).toMatch(/do not need to sign out/i);
    expect(state.description).not.toMatch(
      /sign out and|sign in again|log in again|log out and/i,
    );
  });

  it("omits the email when there is none to quote", () => {
    expect(emptyLandingState([]).description).not.toContain("Quote");
  });
});
