import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { expectNoA11yViolations } from "../../test/a11y";
import { TextareaField } from "./TextareaField";

describe("TextareaField", () => {
  it("associates the label with the textarea", () => {
    render(<TextareaField id="purpose" label="Purpose of travel" />);
    const textarea = screen.getByLabelText("Purpose of travel");
    expect(textarea.tagName).toBe("TEXTAREA");
    expect(textarea).toHaveAttribute("id", "purpose");
  });

  it("wires help and error via aria-describedby and flags aria-invalid", () => {
    render(
      <TextareaField
        id="purpose"
        label="Purpose"
        help="One or two sentences."
        error="Enter the purpose of the trip."
      />,
    );
    const textarea = screen.getByLabelText("Purpose");
    expect(textarea).toHaveAttribute("aria-invalid", "true");
    expect(textarea).toHaveAttribute("aria-describedby", "purpose-help purpose-error");
  });

  it("has no axe violations", async () => {
    const { container } = render(
      <TextareaField id="p1" label="Purpose" help="Help." error="Enter a purpose." required />,
    );
    await expectNoA11yViolations(container);
  });
});
