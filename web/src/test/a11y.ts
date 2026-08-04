import axe from "axe-core";
import { expect } from "vitest";

/**
 * Run axe-core against a rendered container and assert zero violations.
 * color-contrast is disabled: jsdom does no real rendering, and the token
 * palette's AA contrast is already pinned server-side (tests/test_tokens.py).
 * region is disabled: these are component fragments, not full pages with
 * landmarks.
 *
 * `iframes: false` keeps the run inside THIS document (R-5-packet). axe tries
 * to message every nested browsing context, and jsdom gives an <iframe> no real
 * window — so it throws "Respondable target must be a frame in the current
 * window" and the whole assertion dies. The rules that matter for a frame
 * ELEMENT (its `title`, its role) are attributes of the host document and are
 * still checked; only the frame's inner content is skipped, and that content is
 * a PDF the browser renders, not markup we author.
 */
export async function expectNoA11yViolations(container: Element): Promise<void> {
  const results = await axe.run(container, {
    iframes: false,
    rules: {
      "color-contrast": { enabled: false },
      region: { enabled: false },
    },
  });
  expect(results.violations).toEqual([]);
}
