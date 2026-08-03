import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { expectNoA11yViolations } from "../../test/a11y";
import { ChipGroup, type ChipOption } from "./ChipGroup";

const OPTIONS: ChipOption[] = [
  { value: "1", label: "Missing official receipt" },
  { value: "2", label: "Per-diem miscomputed" },
];

function Harness({ initial = [] as string[], error }: { initial?: string[]; error?: string }) {
  const [value, setValue] = useState(initial);
  return (
    <ChipGroup
      id="reasons"
      legend="Why are you returning it?"
      help="Pick every reason that applies."
      error={error}
      options={OPTIONS}
      value={value}
      onChange={setValue}
    />
  );
}

describe("ChipGroup", () => {
  it("is a real checkbox group underneath the chip styling", async () => {
    const { container } = render(<Harness />);

    // The group name and the controls come from the platform, not from ARIA
    // we hand-roll — that is the whole reason chips wrap checkboxes.
    const group = screen.getByRole("group", { name: "Why are you returning it?" });
    expect(group).toBeInTheDocument();
    const boxes = screen.getAllByRole("checkbox");
    expect(boxes).toHaveLength(2);
    expect(boxes.every((box) => !(box as HTMLInputElement).checked)).toBe(true);

    await expectNoA11yViolations(container);
  });

  it("toggles selection on and back off", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    const chip = screen.getByRole("checkbox", { name: "Missing official receipt" });
    await user.click(chip);
    expect(chip).toBeChecked();
    expect(
      screen.getByRole("checkbox", { name: "Per-diem miscomputed" }),
    ).not.toBeChecked();

    await user.click(chip);
    expect(chip).not.toBeChecked();
  });

  it("selects more than one — the taxonomy is multi-select", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole("checkbox", { name: "Missing official receipt" }));
    await user.click(screen.getByRole("checkbox", { name: "Per-diem miscomputed" }));
    expect(screen.getAllByRole("checkbox").every((b) => (b as HTMLInputElement).checked)).toBe(
      true,
    );
  });

  it("renders a pre-selected value", () => {
    render(<Harness initial={["2"]} />);
    expect(screen.getByRole("checkbox", { name: "Per-diem miscomputed" })).toBeChecked();
  });

  it("links the error message to the group", async () => {
    const { container } = render(<Harness error="Select at least one reason." />);

    expect(screen.getByText("Select at least one reason.")).toBeInTheDocument();
    const group = screen.getByRole("group", { name: /Why are you returning it/ });
    expect(group.getAttribute("aria-describedby")).toContain("reasons-error");
    await expectNoA11yViolations(container);
  });
});
