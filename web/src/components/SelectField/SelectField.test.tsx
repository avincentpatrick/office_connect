import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { expectNoA11yViolations } from "../../test/a11y";
import { SelectField } from "./SelectField";

const OPTIONS = [
  { value: "13", label: "NCR" },
  { value: "01", label: "Region I" },
];

describe("SelectField", () => {
  it("associates the label and renders the placeholder + options", () => {
    render(
      <SelectField
        id="region"
        label="Destination region"
        options={OPTIONS}
        placeholder="Select a region"
      />,
    );
    const select = screen.getByLabelText("Destination region");
    expect(select).toHaveAttribute("id", "region");
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Select a region",
      "NCR",
      "Region I",
    ]);
  });

  it("wires help and error via aria-describedby and flags aria-invalid", () => {
    render(
      <SelectField
        id="region"
        label="Destination region"
        options={OPTIONS}
        help="Pick the trip's main destination."
        error="Select the destination region."
      />,
    );
    const select = screen.getByLabelText("Destination region");
    expect(select).toHaveAttribute("aria-invalid", "true");
    expect(select).toHaveAttribute("aria-describedby", "region-help region-error");
    expect(screen.getByText("Select the destination region.")).toHaveAttribute(
      "id",
      "region-error",
    );
  });

  it("has no axe violations", async () => {
    const { container } = render(
      <SelectField
        id="r1"
        label="Region"
        options={OPTIONS}
        placeholder="Select"
        help="Help."
        error="Select a region."
        required
      />,
    );
    await expectNoA11yViolations(container);
  });
});
