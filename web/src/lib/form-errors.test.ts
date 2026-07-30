import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/http";
import { fieldIdFromPath, serverFieldErrors } from "./form-errors";

function validationError(details: unknown): ApiError {
  return new ApiError(422, "validation_error", "Validation failed.", details, null, null);
}

describe("serverFieldErrors", () => {
  it("maps body locs onto RHF paths and anchors the summary item", () => {
    const setError = vi.fn();
    const items = serverFieldErrors(
      validationError([{ loc: ["body", "dpo_date"], msg: "Enter the DPO date", type: "date" }]),
      setError,
      new Set(["dpo_date"]),
    );
    expect(setError).toHaveBeenCalledWith("dpo_date", {
      type: "server",
      message: "Enter the DPO date",
    });
    expect(items).toEqual([{ message: "Enter the DPO date", fieldId: "dpo_date" }]);
  });

  it("whitelists array paths by their root name", () => {
    const setError = vi.fn();
    const items = serverFieldErrors(
      validationError([
        { loc: ["body", "legs", 0, "fare"], msg: "Enter a valid fare", type: "decimal" },
      ]),
      setError,
      new Set(["legs"]),
    );
    expect(setError).toHaveBeenCalledWith("legs.0.fare", {
      type: "server",
      message: "Enter a valid fare",
    });
    expect(items).toEqual([{ message: "Enter a valid fare", fieldId: "legs-0-fare" }]);
  });

  it("keeps unknown locs page-level (no anchor, no setError)", () => {
    const setError = vi.fn();
    const items = serverFieldErrors(
      validationError([{ loc: ["body", "mystery"], msg: "Odd field", type: "x" }]),
      setError,
      new Set(["dpo_date"]),
    );
    expect(setError).not.toHaveBeenCalled();
    expect(items).toEqual([{ message: "Odd field" }]);
  });

  it("surfaces business errors (no details) as a single page-level message", () => {
    const setError = vi.fn();
    const items = serverFieldErrors(
      new ApiError(409, "reimb_claim_not_editable", "This claim can no longer be edited.", undefined, null, null),
      setError,
      new Set(["dpo_date"]),
    );
    expect(items).toEqual([{ message: "This claim can no longer be edited." }]);
  });

  it("degrades non-ApiError failures to the generic copy", () => {
    const items = serverFieldErrors(new Error("boom"), vi.fn(), new Set());
    expect(items).toEqual([{ message: "Something went wrong. Please try again." }]);
  });
});

describe("fieldIdFromPath", () => {
  it("dashes dots (the binding DOM-id convention)", () => {
    expect(fieldIdFromPath("legs.0.fare")).toBe("legs-0-fare");
  });
});
