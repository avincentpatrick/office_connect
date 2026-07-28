import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { expectNoA11yViolations } from "../../test/a11y";
import { StatusChip } from "./StatusChip";

describe("StatusChip", () => {
  it("always carries a text label (never color alone)", () => {
    render(<StatusChip status="done">Completed</StatusChip>);
    expect(screen.getByText("Completed")).toBeInTheDocument();
  });

  it("has no axe violations across all four semantic statuses", async () => {
    const { container } = render(
      <div>
        <StatusChip status="done">Completed</StatusChip>
        <StatusChip status="warn">Due soon</StatusChip>
        <StatusChip status="blocked">Overdue</StatusChip>
        <StatusChip status="waiting">Waiting on external</StatusChip>
      </div>,
    );
    await expectNoA11yViolations(container);
  });
});
