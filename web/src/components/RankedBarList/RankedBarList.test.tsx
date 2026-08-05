import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { expectNoA11yViolations } from "../../test/a11y";
import { RankedBarList, type RankedBarItem } from "./RankedBarList";

const ITEMS: RankedBarItem[] = [
  { id: 1, label: "Missing official receipt", count: 12, valueText: "12 returns", meta: "Up from 7" },
  { id: 2, label: "Per-diem miscomputed", count: 3, valueText: "3 returns", meta: "Down from 9" },
  { id: 3, label: "Obsolete form", count: 0, valueText: "None this period", meta: "Down from 4" },
];

function bars(container: HTMLElement) {
  return Array.from(container.querySelectorAll<HTMLElement>("li > div[aria-hidden] > div"));
}

describe("RankedBarList", () => {
  it("states every count in text, not only in the bar", () => {
    // The whole reason this component exists as an inventory row rather than
    // page markup: a bar encodes a quantity nobody can read without sight.
    render(<RankedBarList items={ITEMS} label="Return reasons" />);
    expect(screen.getByText("12 returns")).toBeInTheDocument();
    expect(screen.getByText("None this period")).toBeInTheDocument();
    expect(screen.getByText("Up from 7")).toBeInTheDocument();
  });

  it("hides the decorative bars from assistive technology", () => {
    const { container } = render(
      <RankedBarList items={ITEMS} label="Return reasons" />,
    );
    for (const track of container.querySelectorAll("li > div[aria-hidden]")) {
      expect(track).toHaveAttribute("aria-hidden", "true");
    }
  });

  it("scales bars against the LARGEST row, never against a total", () => {
    // Scaling to the sum would render each bar as a share of all returns —
    // a rate, which this data cannot support and nobody claimed.
    const { container } = render(
      <RankedBarList items={ITEMS} label="Return reasons" />,
    );
    const [first, second] = bars(container);
    expect(first.style.width).toBe("100%");
    expect(second.style.width).toBe("25%"); // 3/12, not 3/15
  });

  it("renders no bar at all for a zero row, rather than a hairline", () => {
    // A sliver is indistinguishable from a real small value, and "nothing
    // happened this period" is the most useful row on the whole surface.
    const { container } = render(
      <RankedBarList items={ITEMS} label="Return reasons" />,
    );
    expect(bars(container)).toHaveLength(2);
    expect(screen.getByText("Obsolete form")).toBeInTheDocument();
  });

  it("survives an empty list without dividing by zero", () => {
    const { container } = render(<RankedBarList items={[]} label="Return reasons" />);
    expect(container.querySelectorAll("li")).toHaveLength(0);
  });

  it("keeps the server's order and does not re-sort", () => {
    const unsorted: RankedBarItem[] = [
      { id: 1, label: "Small", count: 1, valueText: "1 return" },
      { id: 2, label: "Big", count: 9, valueText: "9 returns" },
    ];
    render(<RankedBarList items={unsorted} label="Return reasons" />);
    const labels = screen.getAllByRole("listitem").map((li) => li.textContent);
    expect(labels[0]).toContain("Small");
  });

  it("is an ordered list with an accessible name", () => {
    render(<RankedBarList items={ITEMS} label="Return reasons, most first" />);
    expect(
      screen.getByRole("list", { name: "Return reasons, most first" }),
    ).toBeInTheDocument();
  });

  it("has no a11y violations", async () => {
    const { container } = render(
      <RankedBarList items={ITEMS} label="Return reasons" />,
    );
    await expectNoA11yViolations(container);
  });
});
