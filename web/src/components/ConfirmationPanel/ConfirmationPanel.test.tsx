import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { expectNoA11yViolations } from "../../test/a11y";
import { ConfirmationPanel } from "./ConfirmationPanel";

describe("ConfirmationPanel", () => {
  it("renders the reference and focuses the heading on mount", () => {
    render(
      <ConfirmationPanel
        title="Claim submitted"
        referenceLabel="Your reference number"
        reference="RB-2026-0001"
      />,
    );
    expect(screen.getByText("RB-2026-0001")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Claim submitted" })).toHaveFocus();
  });

  it("has no axe violations", async () => {
    const { container } = render(
      <ConfirmationPanel
        title="Claim submitted"
        referenceLabel="Your reference number"
        reference="RB-2026-0001"
      >
        <p>We sent it to your division chief.</p>
      </ConfirmationPanel>,
    );
    await expectNoA11yViolations(container);
  });
});
