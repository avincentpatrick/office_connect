import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { FormField } from "../FormField/FormField";
import { FormDialog } from "./FormDialog";

function Harness({
  onSubmit,
  busy = false,
}: {
  onSubmit: () => void;
  busy?: boolean;
}) {
  const [open, setOpen] = useState(true);
  return (
    <FormDialog
      open={open}
      onOpenChange={setOpen}
      title="Return this claim"
      description="The claim goes back to the claimant."
      submitLabel="Return claim"
      busy={busy}
      danger
      onSubmit={onSubmit}
    >
      <FormField id="why" label="What needs fixing?" />
    </FormDialog>
  );
}

describe("FormDialog", () => {
  it("renders its body inside a labelled dialog", () => {
    render(<Harness onSubmit={vi.fn()} />);

    expect(screen.getByRole("dialog", { name: "Return this claim" })).toBeInTheDocument();
    expect(screen.getByLabelText("What needs fixing?")).toBeInTheDocument();
    expect(screen.getByText("The claim goes back to the claimant.")).toBeInTheDocument();
  });

  it("STAYS OPEN after submit — the caller decides when to close", async () => {
    // This is the whole reason FormDialog exists next to ConfirmDialog: a
    // decision that can fail validation must not lose the user's work.
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<Harness onSubmit={onSubmit} />);

    await user.click(screen.getByRole("button", { name: "Return claim" }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("dialog", { name: "Return this claim" })).toBeInTheDocument();
  });

  it("submits on Enter from a field, like any form", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<Harness onSubmit={onSubmit} />);

    await user.type(screen.getByLabelText("What needs fixing?"), "Missing OR{Enter}");
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it("closes on Cancel without submitting", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<Harness onSubmit={onSubmit} />);

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("blocks re-submission while the request is in flight", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<Harness onSubmit={onSubmit} busy />);

    const submit = screen.getByRole("button", { name: "Return claim" });
    expect(submit).toBeDisabled();
    expect(submit).toHaveAttribute("aria-busy", "true");
    await user.click(submit);
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
