"""Print stylesheet for generated documents (core-service #8).

Standing rule 1 ("tokens only — no raw hex/px") does not stop at the screen. A
generated Disbursement Voucher is a surface of this platform, so it draws its
colours and type scale from the same ``core/ui/tokens.py`` contract the React
shell consumes: ``build_tokens(branding)`` → ``to_css_variables()`` → a ``:root``
block prepended to the print rules. Override a tenant's ``color.brand`` and the
PDFs change with the screens, with no second place to edit.

What is *not* token-driven, and why:

- **Page geometry** (A4, 15mm margins, the running footer) is print-only — there
  is no screen token for a paper size, and inventing one would be a token that
  means nothing to any component.
- **The font family** is pinned to DejaVu rather than the token's ``system-ui``
  stack. ``system-ui`` resolves to nothing inside the container: the slim image
  ships no fonts, and the Dockerfile installs exactly one family. Naming the
  font we actually installed is honest; inheriting a stack that silently falls
  back to a blank glyph box is not.

The footer carries the reference number and the Manila generation timestamp on
**every page**, because a page separated from its packet is still evidence and
must identify itself. Drafts additionally get a diagonal watermark — a document
without a reference number must never be mistakable for the filed original.
"""

from __future__ import annotations

from typing import Any

from office_connect.core.ui.tokens import build_tokens, to_css_variables

# The one font family the image installs (see Dockerfile). Kept as a constant so
# a future font change is one edit, and so tests can assert the two agree.
PRINT_FONT_FAMILY = "'DejaVu Sans', sans-serif"


def _root_block(tokens: dict[str, Any]) -> str:
    variables = to_css_variables(tokens)
    lines = "\n".join(f"    {name}: {value};" for name, value in variables.items())
    return ":root {\n" + lines + "\n}"


def build_stylesheet(branding: dict[str, Any] | None = None) -> str:
    """The complete print CSS for one tenant."""
    tokens = build_tokens(branding)
    return f"""{_root_block(tokens)}

@page {{
    size: A4 portrait;
    margin: 18mm 15mm 20mm 15mm;

    @bottom-left {{
        content: string(oc-docref);
        font-size: 8pt;
        color: var(--oc-color-text-muted);
    }}
    @bottom-center {{
        content: string(oc-docstamp);
        font-size: 8pt;
        color: var(--oc-color-text-muted);
    }}
    @bottom-right {{
        content: "Page " counter(page) " of " counter(pages);
        font-size: 8pt;
        color: var(--oc-color-text-muted);
    }}
}}

html {{
    font-family: {PRINT_FONT_FAMILY};
    font-size: 10pt;
    color: var(--oc-color-text);
}}

body {{ margin: 0; }}

/* The footer strings are declared once by hidden elements in the base template
   and repeated by @bottom-* on every page — WeasyPrint's string-set is what
   makes "identify itself on every page" cost one declaration, not one per page. */
.doc-meta {{ string-set: oc-docref attr(data-ref) " "; }}
.doc-stamp {{ string-set: oc-docstamp attr(data-stamp) " "; }}
.doc-meta, .doc-stamp {{ display: none; }}

.doc-header {{
    border-bottom: 2pt solid var(--oc-color-brand);
    padding-bottom: var(--oc-space-2);
    margin-bottom: var(--oc-space-4);
}}
.doc-agency {{
    font-size: var(--oc-font-size-sm);
    color: var(--oc-color-text-muted);
    margin: 0;
}}
.doc-title {{
    font-size: var(--oc-font-size-xl);
    font-weight: var(--oc-font-weight-bold);
    margin: var(--oc-space-1) 0 0 0;
}}
.doc-form-no {{
    font-size: var(--oc-font-size-xs);
    color: var(--oc-color-text-muted);
    margin: 0;
}}

h2 {{
    font-size: var(--oc-font-size-base);
    font-weight: var(--oc-font-weight-bold);
    margin: var(--oc-space-4) 0 var(--oc-space-2) 0;
    page-break-after: avoid;
}}

table {{
    width: 100%;
    border-collapse: collapse;
    font-size: var(--oc-font-size-xs);
}}
th, td {{
    border: 0.5pt solid var(--oc-color-border);
    padding: var(--oc-space-1) var(--oc-space-2);
    text-align: left;
    vertical-align: top;
}}
th {{
    background: var(--oc-color-surface);
    font-weight: var(--oc-font-weight-medium);
}}
/* Money reads right-aligned on every government form; a column of ragged
   figures is the classic way a transcription error hides in plain sight. */
td.amount, th.amount {{ text-align: right; white-space: nowrap; }}
tr.total td {{ font-weight: var(--oc-font-weight-bold); }}
thead {{ display: table-header-group; }}
tr {{ page-break-inside: avoid; }}

.field-grid {{
    display: grid;
    grid-template-columns: auto 1fr auto 1fr;
    gap: var(--oc-space-1) var(--oc-space-3);
    margin-bottom: var(--oc-space-3);
}}
.field-label {{
    color: var(--oc-color-text-muted);
    font-size: var(--oc-font-size-xs);
}}
.field-value {{ font-size: var(--oc-font-size-sm); }}

/* Signature blocks must never straddle a page break: a signature on a page that
   does not carry the thing it certifies is a COA finding waiting to happen. */
.signature-row {{
    display: flex;
    gap: var(--oc-space-6);
    margin-top: var(--oc-space-6);
    page-break-inside: avoid;
}}
.signature-block {{ flex: 1; page-break-inside: avoid; }}
.signature-line {{
    border-bottom: 0.5pt solid var(--oc-color-text);
    height: var(--oc-space-8);
}}
.signature-name {{
    font-size: var(--oc-font-size-sm);
    font-weight: var(--oc-font-weight-medium);
    margin-top: var(--oc-space-1);
}}
.signature-role {{
    font-size: var(--oc-font-size-xs);
    color: var(--oc-color-text-muted);
}}

.note {{
    font-size: var(--oc-font-size-xs);
    color: var(--oc-color-text-muted);
}}

/* Drafts carry a watermark AND a banner. Colour alone never carries meaning
   (ui-standards §6) — and a greyscale office printer is exactly where a
   colour-only draft marking disappears. */
.draft-banner {{
    border: 1pt solid var(--oc-status-warn);
    color: var(--oc-status-warn);
    padding: var(--oc-space-2);
    margin-bottom: var(--oc-space-3);
    font-weight: var(--oc-font-weight-bold);
    font-size: var(--oc-font-size-sm);
    text-align: center;
}}
.draft-watermark {{
    position: fixed;
    top: 40%;
    left: 0;
    right: 0;
    text-align: center;
    transform: rotate(-30deg);
    font-size: 72pt;
    font-weight: var(--oc-font-weight-bold);
    color: var(--oc-status-warn);
    opacity: 0.12;
}}
"""
