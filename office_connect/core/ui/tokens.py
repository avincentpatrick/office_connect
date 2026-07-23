"""Design-token contract — the single source of truth (ui-standards.md §2).

``NEUTRAL_TOKENS`` are the platform-wide **neutral defaults**: concrete values
for every §2 token category, all with the ``--oc-`` prefix when flattened to CSS
custom properties. Tenants override brand-specific tokens through their
``core_tenant_configs.branding.tokens`` map; ``build_tokens`` deep-merges those
over the neutral defaults so unspecified tokens always fall back to a valid,
accessible value. This is what ``GET /api/v1/config`` serves under ``tokens`` and
what the future React shell / Tailwind config (ui-standards §7, still deferred)
will consume — never raw hex/px in a component (§1 principle 5).

**Accessibility (§6):** the default colour pairs used as text on a surface meet
WCAG 2.1 AA (≥4.5:1 for normal text). Verified pairs (see test_tokens.py):
text/bg, text-muted/bg, link/bg, brand-contrast/brand, and each status colour on
bg. Changing a default colour re-runs that check.
"""

from __future__ import annotations

import copy
from typing import Any

# The neutral default token set. Structure is stable; tenant branding overrides
# a subset with the same shape. Colours are hex; spacing/type are CSS lengths.
NEUTRAL_TOKENS: dict[str, Any] = {
    "color": {
        # Brand — the one colour a tenant most often overrides.
        "brand": "#0b5cad",           # deep government blue
        "brand-contrast": "#ffffff",  # text/icon on a brand-filled surface
        # Surfaces
        "bg": "#ffffff",
        "surface": "#f6f8fa",
        "border": "#d0d7de",
        # Text
        "text": "#1a1a1a",
        "text-muted": "#5c6570",
        "link": "#0b5cad",
    },
    # Semantic, platform-wide status colours (§2: green/amber/red/grey). A given
    # colour means the same on every page of every module.
    "status": {
        "done": "#1a7f37",      # green — complete
        "warn": "#b45309",      # amber — due soon / flagged
        "blocked": "#b42318",   # red — overdue / blocked
        "waiting": "#5c6570",   # grey — waiting on external
    },
    # 4-px base spacing scale, space-1 … space-8.
    "space": {str(n): f"{4 * n}px" for n in range(1, 9)},
    "font": {
        "family": (
            "system-ui, -apple-system, 'Segoe UI', Roboto, "
            "'Helvetica Neue', Arial, sans-serif"
        ),
        "size": {
            "xs": "0.75rem",
            "sm": "0.875rem",
            "base": "1rem",
            "lg": "1.125rem",
            "xl": "1.25rem",
            "2xl": "1.5rem",
            "3xl": "1.875rem",
        },
        "weight": {"regular": 400, "medium": 500, "bold": 700},
    },
    "radius": {"sm": "2px", "md": "6px", "lg": "12px"},
    "shadow": {
        "sm": "0 1px 2px rgba(16, 24, 40, 0.06)",
        "md": "0 4px 8px rgba(16, 24, 40, 0.10)",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge ``override`` into a copy of ``base`` (override wins).

    Only dict branches are merged; scalar/list overrides replace outright.
    Ignores override keys that are not present in ``base`` so a malformed
    branding blob can never inject arbitrary token names.
    """
    out = copy.deepcopy(base)
    for key, value in override.items():
        if key not in out:
            continue  # unknown token name — ignore (fail-safe)
        if isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def build_tokens(branding: dict[str, Any] | None) -> dict[str, Any]:
    """Neutral defaults with tenant overrides from ``branding['tokens']`` applied.

    Always returns a complete token set — a missing/empty/None branding yields
    the neutral defaults unchanged, so a degraded config still serves usable
    tokens.
    """
    overrides = {}
    if isinstance(branding, dict):
        candidate = branding.get("tokens")
        if isinstance(candidate, dict):
            overrides = candidate
    if not overrides:
        return copy.deepcopy(NEUTRAL_TOKENS)
    return _deep_merge(NEUTRAL_TOKENS, overrides)


def to_css_variables(tokens: dict[str, Any]) -> dict[str, str]:
    """Flatten a token tree to ``{'--oc-<path>': value}`` CSS custom properties.

    e.g. ``color.brand`` → ``--oc-color-brand``, ``font.size.xs`` →
    ``--oc-font-size-xs``. The React/Tailwind layer (ui-standards §7) renders
    these into a ``:root`` block.
    """
    flat: dict[str, str] = {}

    def _walk(node: Any, path: list[str]) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                _walk(value, [*path, str(key)])
        else:
            flat["--oc-" + "-".join(path)] = str(node)

    _walk(tokens, [])
    return flat
