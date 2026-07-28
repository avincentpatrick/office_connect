import type { TokenTree } from "../api/types";

/**
 * Flatten a token tree to `{'--oc-<path>': value}` CSS custom properties.
 * TS port of to_css_variables (office_connect/core/ui/tokens.py:108-125):
 * `color.brand` → `--oc-color-brand`, `font.size.xs` → `--oc-font-size-xs`.
 */
export function toCssVariables(tokens: TokenTree, prefix = "--oc"): Record<string, string> {
  const flat: Record<string, string> = {};
  const walk = (node: TokenTree[string], path: string[]): void => {
    if (node !== null && typeof node === "object" && !Array.isArray(node)) {
      for (const [key, value] of Object.entries(node)) walk(value, [...path, key]);
    } else {
      flat[[prefix, ...path].join("-")] = String(node);
    }
  };
  walk(tokens, []);
  return flat;
}

/**
 * Apply the served token tree as inline custom properties on <html>. Inline
 * style outranks the baked :root fallback in tokens.css, so tenant branding
 * re-themes every Tailwind utility (@theme inline) without a rebuild.
 */
export function injectTokens(tokens: TokenTree): void {
  const style = document.documentElement.style;
  for (const [name, value] of Object.entries(toCssVariables(tokens))) {
    style.setProperty(name, value);
  }
}
