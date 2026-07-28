import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { expectNoA11yViolations } from "../../test/a11y";
import { ErrorSummary } from "./ErrorSummary";

describe("ErrorSummary", () => {
  it("renders role=alert, takes focus on mount, and anchors to fields", () => {
    render(
      <ErrorSummary
        errors={[
          { message: "Enter your email address", fieldId: "email" },
          { message: "Something page-level went wrong" },
        ]}
      />,
    );
    const alert = screen.getByRole("alert");
    expect(alert).toHaveFocus();
    expect(screen.getByText("There is a problem")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Enter your email address" })).toHaveAttribute(
      "href",
      "#email",
    );
    expect(screen.getByText("Something page-level went wrong")).toBeInTheDocument();
  });

  it("renders nothing when there are no errors", () => {
    render(<ErrorSummary errors={[]} />);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("has no axe violations", async () => {
    const { container } = render(
      <ErrorSummary errors={[{ message: "Enter a code", fieldId: "code" }]} />,
    );
    await expectNoA11yViolations(container);
  });
});
