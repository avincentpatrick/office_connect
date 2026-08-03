import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FileUpload } from "./FileUpload";

const file = (name = "receipt.jpg") =>
  new File(["bytes"], name, { type: "image/jpeg" });

function setup(props: Partial<Parameters<typeof FileUpload>[0]> = {}) {
  const onFiles = vi.fn();
  render(
    <FileUpload
      id="upload-1"
      label="Upload your travel order"
      onFiles={onFiles}
      {...props}
    />,
  );
  return { onFiles, input: screen.getByLabelText(/Upload your travel order/) };
}

describe("FileUpload", () => {
  it("is a real, label-associated file input", () => {
    const { input } = setup();
    expect(input).toHaveAttribute("type", "file");
  });

  it("emits the picked files", async () => {
    const { onFiles, input } = setup();
    await userEvent.upload(input, file());
    expect(onFiles).toHaveBeenCalledTimes(1);
    expect(onFiles.mock.calls[0][0][0].name).toBe("receipt.jpg");
  });

  it("clears its value so the SAME file can be re-picked", async () => {
    // Without the reset, a retry after a rejected upload fires no `change`
    // event and silently does nothing.
    const { onFiles, input } = setup();
    await userEvent.upload(input, file());
    expect((input as HTMLInputElement).value).toBe("");
    await userEvent.upload(input, file());
    expect(onFiles).toHaveBeenCalledTimes(2);
  });

  it("forwards accept and leaves capture unset unless asked", () => {
    const { input } = setup({ accept: "image/jpeg,application/pdf" });
    expect(input).toHaveAttribute("accept", "image/jpeg,application/pdf");
    // Spec §9.3 says camera capture is ALLOWED, not forced: on mobile the
    // `capture` attribute deletes the gallery option entirely.
    expect(input).not.toHaveAttribute("capture");
  });

  it("blocks a second pick while an upload is in flight", () => {
    const { input } = setup({ busy: true });
    expect(input).toBeDisabled();
    expect(input).toHaveAttribute("aria-busy", "true");
  });

  it("links help and error text to the input", () => {
    setup({ help: "Attach a scan or a photo.", error: "That file is too big." });
    const input = screen.getByLabelText(/Upload your travel order/);
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription(
      /Attach a scan or a photo\.\s+That file is too big\./,
    );
  });

  it("announces completion in a polite live region", () => {
    setup({ status: "receipt.jpg attached." });
    const region = screen.getByText("receipt.jpg attached.");
    expect(region).toHaveAttribute("aria-live", "polite");
  });
});
