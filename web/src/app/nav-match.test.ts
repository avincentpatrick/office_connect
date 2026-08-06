import { describe, expect, it } from "vitest";
import { matchNavItems, type Matchable } from "./nav-match";

const ITEMS: Matchable[] = [
  { label: "Reimbursement", intentKeywords: ["travel", "claim", "per diem"] },
  { label: "Cash advances", intentKeywords: ["cash advance", "liquidation", "COA"] },
  { label: "Claim queue", intentKeywords: ["queue", "FMS", "stuck"] },
  { label: "Insights", intentKeywords: ["returns", "why"] },
];

const found = (query: string) => matchNavItems(ITEMS, query).map((m) => m.item.label);
const tiers = (query: string) => matchNavItems(ITEMS, query).map((m) => m.tier);

describe("matchNavItems", () => {
  it("returns nothing for an empty query", () => {
    expect(matchNavItems(ITEMS, "")).toEqual([]);
  });

  it("returns nothing for a whitespace-only query", () => {
    expect(matchNavItems(ITEMS, "   ")).toEqual([]);
  });

  it("finds nothing in an empty item list — it cannot see NAV_GROUPS", () => {
    // The structural guarantee: the matcher has no import of the nav registry,
    // so an empty input can only ever produce an empty output. A future refactor
    // that "helpfully" reaches for NAV_GROUPS fails here.
    expect(matchNavItems([], "reimbursement")).toEqual([]);
  });

  it("matches an exact label", () => {
    expect(tiers("insights")[0]).toBe("label-exact");
  });

  it("matches an exact keyword", () => {
    expect(found("coa")).toEqual(["Cash advances"]);
    expect(tiers("coa")).toEqual(["keyword-exact"]);
  });

  it("matches a label prefix", () => {
    expect(found("cash")[0]).toBe("Cash advances");
    expect(tiers("cash")[0]).toBe("label-prefix");
  });

  it("matches a keyword prefix", () => {
    expect(found("liquid")).toEqual(["Cash advances"]);
    expect(tiers("liquid")).toEqual(["keyword-prefix"]);
  });

  it("matches a label substring", () => {
    expect(found("sight")).toEqual(["Insights"]);
    expect(tiers("sight")).toEqual(["label-substring"]);
  });

  it("matches a keyword substring", () => {
    expect(found("iem")).toEqual(["Reimbursement"]);
    expect(tiers("iem")).toEqual(["keyword-substring"]);
  });

  it("ranks an exact keyword above a label prefix", () => {
    // The ordering decision, documented as a test: "claim" is an exact keyword
    // on Reimbursement and a label prefix on Claim queue. Strength of match
    // beats which field it came from.
    expect(found("claim")).toEqual(["Reimbursement", "Claim queue"]);
    expect(tiers("claim")).toEqual(["keyword-exact", "label-prefix"]);
  });

  it("lists an item once, at its strongest tier", () => {
    // "queue" is both an exact keyword and a label substring on Claim queue.
    const matches = matchNavItems(ITEMS, "queue");
    expect(matches).toHaveLength(1);
    expect(matches[0].tier).toBe("keyword-exact");
  });

  it("preserves declaration order within a tier", () => {
    // Both are label-substring hits on "s"... except Insights is a prefix.
    const twoSubstrings = matchNavItems(
      [{ label: "Alpha one" }, { label: "Beta one" }],
      "one",
    );
    expect(twoSubstrings.map((m) => m.item.label)).toEqual(["Alpha one", "Beta one"]);
  });

  it("is case- and whitespace-insensitive", () => {
    expect(found("  CASH   ADVANCE ")).toEqual(["Cash advances"]);
    expect(tiers("  CASH   ADVANCE ")).toEqual(["keyword-exact"]);
  });

  it("matches a single character — there is no minimum query length", () => {
    expect(found("i").length).toBeGreaterThan(0);
  });

  it("never returns an item that was not in the input", () => {
    const labels = new Set(ITEMS.map((i) => i.label));
    for (const query of ["a", "e", "claim", "coa", "zzz"]) {
      for (const match of matchNavItems(ITEMS, query)) {
        expect(labels.has(match.item.label)).toBe(true);
      }
    }
  });

  it("tolerates an item with no keywords at all", () => {
    expect(matchNavItems([{ label: "Home" }], "home")).toHaveLength(1);
    expect(matchNavItems([{ label: "Home" }], "travel")).toEqual([]);
  });
});
