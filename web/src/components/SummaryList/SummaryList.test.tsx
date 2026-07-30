import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { expectNoA11yViolations } from "../../test/a11y";
import { SummaryList } from "./SummaryList";

const ROWS = [
  {
    key: "Purpose",
    value: "Regional workshop",
    action: { label: "Change", to: "../trip", visuallyHidden: "purpose" },
  },
  { key: "DPO number", value: "" },
];

describe("SummaryList", () => {
  it("renders key/value rows with a Change link carrying sr-only context", () => {
    render(
      <MemoryRouter>
        <SummaryList rows={ROWS} />
      </MemoryRouter>,
    );
    expect(screen.getByText("Purpose")).toBeInTheDocument();
    expect(screen.getByText("Regional workshop")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "Change purpose" });
    expect(link).toHaveAttribute("href", "/trip");
  });

  it("renders empty values as 'Not provided', never blank", () => {
    render(
      <MemoryRouter>
        <SummaryList rows={ROWS} />
      </MemoryRouter>,
    );
    expect(screen.getByText("Not provided")).toBeInTheDocument();
  });

  it("has no axe violations", async () => {
    const { container } = render(
      <MemoryRouter>
        <SummaryList rows={ROWS} />
      </MemoryRouter>,
    );
    await expectNoA11yViolations(container);
  });
});
