import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { expectNoA11yViolations } from "../../test/a11y";
import { Stepper } from "./Stepper";

const STEPS = ["Trip", "Legs", "Expenses", "Review"];

describe("Stepper", () => {
  it("announces the position and marks the active step", () => {
    render(<Stepper steps={STEPS} current={2} />);
    expect(screen.getByText(/Step 2 of 4/)).toBeInTheDocument();
    const items = screen.getAllByRole("listitem");
    expect(items[1]).toHaveAttribute("aria-current", "step");
    expect(items[0]).not.toHaveAttribute("aria-current");
  });

  it("has no axe violations", async () => {
    const { container } = render(<Stepper steps={STEPS} current={3} />);
    await expectNoA11yViolations(container);
  });
});
