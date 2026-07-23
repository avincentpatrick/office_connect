"""QA gate: design-token contract (Increment 3; ui-standards §2).

Covers the neutral default set, the branding override merge, CSS-variable
flattening (``--oc-*``), and a WCAG 2.1 AA contrast check on the default colour
pairs (§6 — checked once, inherited everywhere).
"""

from office_connect.core.ui.tokens import (
    NEUTRAL_TOKENS,
    build_tokens,
    to_css_variables,
)


def test_neutral_tokens_cover_all_categories():
    assert set(NEUTRAL_TOKENS["color"]) == {
        "brand", "brand-contrast", "bg", "surface", "border",
        "text", "text-muted", "link",
    }
    assert set(NEUTRAL_TOKENS["status"]) == {"done", "warn", "blocked", "waiting"}
    assert set(NEUTRAL_TOKENS["space"]) == {str(n) for n in range(1, 9)}
    assert NEUTRAL_TOKENS["space"]["1"] == "4px" and NEUTRAL_TOKENS["space"]["8"] == "32px"
    assert {"family", "size", "weight"} <= set(NEUTRAL_TOKENS["font"])
    assert set(NEUTRAL_TOKENS["radius"]) == {"sm", "md", "lg"}
    assert set(NEUTRAL_TOKENS["shadow"]) == {"sm", "md"}


def test_build_tokens_defaults_when_no_branding():
    assert build_tokens(None) == NEUTRAL_TOKENS
    assert build_tokens({}) == NEUTRAL_TOKENS
    assert build_tokens({"logo_url": "x"}) == NEUTRAL_TOKENS  # non-token branding


def test_branding_overrides_only_named_tokens():
    tokens = build_tokens({"tokens": {"color": {"brand": "#7a1f2b"}}})
    assert tokens["color"]["brand"] == "#7a1f2b"           # overridden
    assert tokens["color"]["bg"] == NEUTRAL_TOKENS["color"]["bg"]  # untouched
    assert tokens["status"] == NEUTRAL_TOKENS["status"]     # untouched


def test_unknown_override_keys_ignored():
    tokens = build_tokens({"tokens": {"color": {"evil": "#000"}, "bogus": {"x": 1}}})
    assert "evil" not in tokens["color"]
    assert "bogus" not in tokens


def test_to_css_variables_uses_oc_prefix():
    css = to_css_variables(NEUTRAL_TOKENS)
    assert css["--oc-color-brand"] == NEUTRAL_TOKENS["color"]["brand"]
    assert css["--oc-space-1"] == "4px"
    assert css["--oc-font-size-xs"] == NEUTRAL_TOKENS["font"]["size"]["xs"]
    assert css["--oc-font-weight-regular"] == "400"
    assert css["--oc-status-blocked"] == NEUTRAL_TOKENS["status"]["blocked"]


# --------------------------------------------------------- WCAG AA contrast (§6)
def _luminance(hex_color: str) -> float:
    hex_color = hex_color.lstrip("#")
    channels = [int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [
        c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(fg: str, bg: str) -> float:
    l1, l2 = _luminance(fg), _luminance(bg)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def test_default_palette_meets_wcag_aa():
    c = NEUTRAL_TOKENS["color"]
    bg = c["bg"]
    # Normal-text pairs must clear 4.5:1.
    assert _contrast(c["text"], bg) >= 4.5
    assert _contrast(c["text-muted"], bg) >= 4.5
    assert _contrast(c["link"], bg) >= 4.5
    assert _contrast(c["brand-contrast"], c["brand"]) >= 4.5
    for name, value in NEUTRAL_TOKENS["status"].items():
        assert _contrast(value, bg) >= 4.5, f"status {name} fails AA on bg"
