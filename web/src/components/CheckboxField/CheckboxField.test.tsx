import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { expectNoA11yViolations } from "../../test/a11y";
import { CheckboxField } from "./CheckboxField";

describe("CheckboxField", () => {
  it("associates the label with the checkbox", () => {
    render(<CheckboxField id="lodging" label="Lodging was provided by the host" />);
    const box = screen.getByLabelText("Lodging was provided by the host");
    expect(box).toHaveAttribute("type", "checkbox");
    expect(box).toHaveAttribute("id", "lodging");
  });

  it("wires hint and error via aria-describedby and flags aria-invalid", () => {
    render(
      <CheckboxField
        id="lodging"
        label="Lodging provided"
        hint="EO 77: strips 50% of the day's rate."
        error="Tick or clear the lodging attestation."
      />,
    );
    const box = screen.getByLabelText("Lodging provided");
    expect(box).toHaveAttribute("aria-invalid", "true");
    expect(box).toHaveAttribute("aria-describedby", "lodging-hint lodging-error");
  });

  it("has no axe violations", async () => {
    const { container } = render(
      <CheckboxField id="c1" label="Meals provided" hint="Hint." error="Fix this." />,
    );
    await expectNoA11yViolations(container);
  });
});
