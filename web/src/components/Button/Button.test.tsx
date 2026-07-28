import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expectNoA11yViolations } from "../../test/a11y";
import { Button } from "./Button";

describe("Button", () => {
  it("renders its label and defaults to type=button", () => {
    render(<Button>Save claim</Button>);
    const button = screen.getByRole("button", { name: "Save claim" });
    expect(button).toHaveAttribute("type", "button");
  });

  it("blocks interaction and keeps the label while loading", async () => {
    const onClick = vi.fn();
    render(
      <Button loading onClick={onClick}>
        Submitting
      </Button>,
    );
    const button = screen.getByRole("button", { name: "Submitting" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
    await userEvent.click(button).catch(() => undefined);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("has no axe violations across variants", async () => {
    const { container } = render(
      <div>
        <Button>Primary</Button>
        <Button variant="secondary">Secondary</Button>
        <Button variant="danger">Danger</Button>
        <Button disabled>Disabled</Button>
      </div>,
    );
    await expectNoA11yViolations(container);
  });
});
