import { describe, expect, it } from "vitest";
import { injectTokens, toCssVariables } from "./tokens";

const SAMPLE = {
  color: { brand: "#0b5cad", "text-muted": "#5c6570" },
  status: { done: "#1a7f37" },
  space: { "1": "4px", "8": "32px" },
  font: {
    family: "system-ui, sans-serif",
    size: { xs: "0.75rem", "3xl": "1.875rem" },
    weight: { regular: 400, bold: 700 },
  },
};

describe("toCssVariables", () => {
  // Parity with office_connect/core/ui/tokens.py::to_css_variables — same
  // walk, same joining, numbers stringified.
  it("flattens nested paths with the --oc- prefix", () => {
    const flat = toCssVariables(SAMPLE);
    expect(flat["--oc-color-brand"]).toBe("#0b5cad");
    expect(flat["--oc-color-text-muted"]).toBe("#5c6570");
    expect(flat["--oc-status-done"]).toBe("#1a7f37");
    expect(flat["--oc-space-8"]).toBe("32px");
    expect(flat["--oc-font-size-xs"]).toBe("0.75rem");
    expect(flat["--oc-font-size-3xl"]).toBe("1.875rem");
    expect(flat["--oc-font-family"]).toBe("system-ui, sans-serif");
  });

  it("stringifies numeric leaves (font weights)", () => {
    const flat = toCssVariables(SAMPLE);
    expect(flat["--oc-font-weight-regular"]).toBe("400");
    expect(flat["--oc-font-weight-bold"]).toBe("700");
  });

  it("produces only leaf entries", () => {
    const flat = toCssVariables(SAMPLE);
    expect(Object.keys(flat)).toHaveLength(10);
    expect(flat["--oc-color"]).toBeUndefined();
  });
});

describe("injectTokens", () => {
  it("sets custom properties inline on <html>", () => {
    injectTokens({ color: { brand: "#123456" } });
    expect(document.documentElement.style.getPropertyValue("--oc-color-brand")).toBe("#123456");
  });
});
