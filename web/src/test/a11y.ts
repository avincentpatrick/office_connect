import axe from "axe-core";
import { expect } from "vitest";

/**
 * Run axe-core against a rendered container and assert zero violations.
 * color-contrast is disabled: jsdom does no real rendering, and the token
 * palette's AA contrast is already pinned server-side (tests/test_tokens.py).
 * region is disabled: these are component fragments, not full pages with
 * landmarks.
 */
export async function expectNoA11yViolations(container: Element): Promise<void> {
  const results = await axe.run(container, {
    rules: {
      "color-contrast": { enabled: false },
      region: { enabled: false },
    },
  });
  expect(results.violations).toEqual([]);
}
