import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Callout } from "./Callout";

describe("Callout", () => {
  it("names itself through its heading", () => {
    render(
      <Callout status="warn" title="1 automatic check flagged">
        <p>Body copy.</p>
      </Callout>,
    );
    const region = screen.getByRole("region", {
      name: /1 automatic check flagged/,
    });
    expect(region).toBeInTheDocument();
    expect(screen.getByText("Body copy.")).toBeInTheDocument();
  });

  it("carries the status as text, never colour alone (§6)", () => {
    const { rerender } = render(<Callout status="warn" title="Heads up" />);
    expect(screen.getByText("Warning:")).toBeInTheDocument();

    rerender(<Callout status="blocked" title="Stop" />);
    expect(screen.getByText("Problem:")).toBeInTheDocument();

    rerender(<Callout status="done" title="Fine" />);
    expect(screen.getByText("Success:")).toBeInTheDocument();

    rerender(<Callout status="waiting" title="Hold" />);
    expect(screen.getByText("Waiting:")).toBeInTheDocument();
  });

  it("honours the requested heading level", () => {
    render(<Callout status="warn" as="h2" title="Top level" />);
    expect(
      screen.getByRole("heading", { level: 2, name: /Top level/ }),
    ).toBeInTheDocument();
  });

  it("is only a live region when asked", () => {
    const { rerender } = render(<Callout status="warn" title="Quiet" />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();

    rerender(<Callout status="warn" title="Loud" live="polite" />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("does NOT take focus on mount", () => {
    // The whole reason this is not ErrorSummary: that component is role=alert
    // and focuses itself, which would rip focus off the approver's decision bar
    // on every render of the claim page.
    render(<Callout status="warn" title="Flagged" />);
    expect(document.activeElement).toBe(document.body);
  });
});
