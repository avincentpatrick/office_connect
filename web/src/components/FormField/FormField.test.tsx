import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { expectNoA11yViolations } from "../../test/a11y";
import { FormField } from "./FormField";

describe("FormField", () => {
  it("associates the label with the input", () => {
    render(<FormField id="email" label="Email address" />);
    expect(screen.getByLabelText("Email address")).toHaveAttribute("id", "email");
  });

  it("wires help and error text via aria-describedby and flags aria-invalid", () => {
    render(
      <FormField
        id="password"
        label="Password"
        help="At least 12 characters."
        error="Enter a password of at least 12 characters."
      />,
    );
    const input = screen.getByLabelText("Password");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAttribute("aria-describedby", "password-help password-error");
    expect(screen.getByText("At least 12 characters.")).toHaveAttribute("id", "password-help");
    expect(screen.getByText("Enter a password of at least 12 characters.")).toHaveAttribute(
      "id",
      "password-error",
    );
  });

  it("has no axe violations with help and error present", async () => {
    const { container } = render(
      <FormField id="f1" label="Field" help="Help text." error="Fix this field." required />,
    );
    await expectNoA11yViolations(container);
  });

  it("forwards a callback ref to the input (the react-hook-form register contract)", () => {
    let received: HTMLInputElement | null = null;
    render(
      <FormField
        id="dpo_no"
        label="DPO number"
        ref={(el) => {
          received = el;
        }}
      />,
    );
    expect(received).toBeInstanceOf(HTMLInputElement);
    expect((received as HTMLInputElement | null)?.id).toBe("dpo_no");
  });
});
