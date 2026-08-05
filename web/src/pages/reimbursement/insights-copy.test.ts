import { describe, expect, it } from "vitest";
import type { ReasonRank, ReturnInsights } from "../../api/reimbursement";
import { countPhrase, insightsSummary, rankMeta, trendPhrase } from "./insights-copy";

function rank(over: Partial<ReasonRank> = {}): ReasonRank {
  return {
    reason_id: 1,
    code: "MISSING_OR",
    label: "Missing official receipt",
    category: "missing_doc",
    count: 12,
    prior_count: 7,
    trend: "up",
    promoted: false,
    promotable: true,
    ...over,
  };
}

describe("countPhrase", () => {
  it("pluralises, and says zero in words", () => {
    expect(countPhrase(rank({ count: 12 }))).toBe("12 returns");
    expect(countPhrase(rank({ count: 1 }))).toBe("1 return");
    expect(countPhrase(rank({ count: 0 }))).toBe("None this period");
  });
});

describe("trendPhrase", () => {
  it("distinguishes a debut from a rise", () => {
    // An Admin Officer reads them differently: a spike in a familiar reason is
    // a process problem; a brand-new reason is usually a form that just changed.
    expect(trendPhrase(rank({ trend: "new", count: 3, prior_count: 0 }))).toBe(
      "New this period",
    );
    expect(trendPhrase(rank({ trend: "up", prior_count: 7 }))).toBe("Up from 7");
  });

  it("says out loud when a reason has stopped happening", () => {
    // The row that proves a promotion worked, on the surface built to show it.
    expect(
      trendPhrase(rank({ trend: "down", count: 0, prior_count: 4 })),
    ).toBe("Down from 4 — none this period");
    expect(trendPhrase(rank({ trend: "down", count: 2, prior_count: 4 }))).toBe(
      "Down from 4",
    );
  });

  it("never renders a bare arrow or a percentage", () => {
    for (const trend of ["up", "down", "flat", "new"] as const) {
      const phrase = trendPhrase(rank({ trend, count: 2, prior_count: 2 }));
      expect(phrase).not.toMatch(/[▲▼↑↓%]/);
    }
  });

  it("handles the flat case in both directions", () => {
    expect(trendPhrase(rank({ trend: "flat", count: 2, prior_count: 2 }))).toBe(
      "Unchanged from 2",
    );
    expect(trendPhrase(rank({ trend: "flat", count: 0, prior_count: 0 }))).toBe(
      "None in either period",
    );
  });
});

describe("rankMeta", () => {
  it("says when a reason is already a warning", () => {
    expect(rankMeta(rank({ promoted: true }))).toBe(
      "Up from 7 · Shown as a warning at step 5",
    );
    expect(rankMeta(rank({ promoted: false }))).toBe("Up from 7");
  });
});

describe("insightsSummary", () => {
  const data: ReturnInsights = {
    window_days: 90,
    period_start: "2026-05-08",
    total_returns: 37,
    can_promote: true,
    items: [],
  };

  it("quotes the server's window and its start date", () => {
    // api-standards §9g — a bound the client cannot see is a bound the client
    // will eventually contradict, so neither number is a literal here.
    const summary = insightsSummary(data);
    expect(summary).toContain("last 90 days");
    expect(summary).toContain("May 8, 2026");
    expect(summary).toContain("37 returns");
  });

  it("reflects a different server window rather than a hard-coded 90", () => {
    expect(insightsSummary({ ...data, window_days: 30 })).toContain(
      "last 30 days",
    );
  });

  it("counts packets, never a rate", () => {
    expect(insightsSummary(data)).not.toMatch(/%/);
    expect(insightsSummary({ ...data, total_returns: 1 })).toContain("1 return in");
  });
});
