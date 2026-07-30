import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { expectNoA11yViolations } from "../../test/a11y";
import { RadioGroupField } from "./RadioGroupField";

const OPTIONS = [
  { value: "GF_ORS", label: "General Fund (ORS)" },
  { value: "TF_BUR", label: "Trust Fund (BUR)", hint: "Externally funded trips." },
];

describe("RadioGroupField", () => {
  it("renders a fieldset group with a legend and one radio per option", () => {
    render(
      <RadioGroupField id="fund" name="fund_source" legend="Fund source" options={OPTIONS} />,
    );
    expect(screen.getByRole("group", { name: /Fund source/ })).toBeInTheDocument();
    const radios = screen.getAllByRole("radio");
    expect(radios).toHaveLength(2);
    expect(radios[0]).toHaveAttribute("id", "fund-GF_ORS");
    expect(screen.getByLabelText(/General Fund/)).toHaveAttribute("value", "GF_ORS");
  });

  it("shows the error inside the fieldset with the group id", () => {
    render(
      <RadioGroupField
        id="fund"
        name="fund_source"
        legend="Fund source"
        options={OPTIONS}
        error="Select the fund source."
      />,
    );
    expect(screen.getByText("Select the fund source.")).toHaveAttribute("id", "fund-error");
    const group = screen.getByRole("group");
    expect(group).toHaveAttribute("aria-describedby", "fund-error");
    // The bare group id must exist in the DOM — ErrorSummary anchors to it.
    expect(group).toHaveAttribute("id", "fund");
  });

  it("has no axe violations", async () => {
    const { container } = render(
      <RadioGroupField
        id="f1"
        name="f1"
        legend="Question"
        options={OPTIONS}
        help="Pick one."
        error="Select an option."
        required
      />,
    );
    await expectNoA11yViolations(container);
  });
});
