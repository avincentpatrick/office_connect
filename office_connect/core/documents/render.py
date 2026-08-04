"""Template → PDF rendering (core-service #8).

The engine, and only the engine: give it a registered document key, a context
dict and a tenant's branding, and it returns PDF bytes plus the two hashes the
frozen-snapshot service needs. It knows nothing about claims, workflows or
checklists.

**The renderer is injected.** ``render_document(..., renderer=None)`` follows the
exact convention ``core/attachments/service.py`` set with ``scanner=`` and
``storage=``: every collaborator is a keyword argument with a ``None`` default
that resolves to the real implementation. That is what lets the test suite run on
the Windows dev host, where WeasyPrint's Pango stack does not exist — tests pass
a fake renderer and never import it. WeasyPrint itself is imported **lazily,
inside** ``WeasyPrintRenderer.render``, so merely importing ``core`` never
touches the native libraries.

**Two different hashes, deliberately.**

- ``content_sha256`` is the hash of the PDF bytes — the tamper-evidence value,
  written into the hash-chained audit log and used to prove the file an approver
  saw is the file on disk.
- ``source_fingerprint`` is the hash of the *canonical context* that produced it.
  This is what makes "modified after signature" cheap: re-derive the context and
  compare one string. PDF bytes are not reproducible (they embed a creation
  timestamp), so hashing output could never answer "did the underlying data
  change?" — only hashing input can.

Rendering never happens in the request path (master-plan §1.1 #8). Nothing here
enforces that — it is the caller's contract — but the Celery wrapper in
``ops/document_tasks.py`` is the only production caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from office_connect.core.audit import canonical_json
from office_connect.core.documents import registry, templates
from office_connect.core.documents.errors import RenderFailed
from office_connect.core.documents.stylesheet import build_stylesheet
from office_connect.core.storage.base import sha256_hex


@dataclass(frozen=True)
class RenderedDocument:
    """One rendered document plus everything needed to freeze it."""

    key: str
    title: str
    pdf: bytes
    content_sha256: str
    source_fingerprint: str
    html: str


class PdfRenderer(Protocol):
    """The HTML+CSS → PDF seam. One method, so a fake is three lines."""

    name: str

    def render(self, html: str, *, stylesheet: str) -> bytes: ...


class WeasyPrintRenderer:
    """The production renderer. Requires the Pango stack — container only."""

    name = "weasyprint"

    def render(self, html: str, *, stylesheet: str) -> bytes:
        # Lazy import: keeps `import office_connect.core` working on a host with
        # no GTK/Pango (the Windows dev machine, and every unit test).
        from weasyprint import CSS, HTML

        # base_url=None: templates are self-contained and must never resolve a
        # relative URL. A generated document that can fetch is an SSRF surface,
        # and on an air-gapped server it would simply hang.
        document = HTML(string=html, base_url=None)
        return document.write_pdf(stylesheets=[CSS(string=stylesheet)])


_renderer: PdfRenderer | None = None


def get_renderer(renderer: PdfRenderer | None = None) -> PdfRenderer:
    """Resolve the renderer: explicit argument → process default → WeasyPrint."""
    if renderer is not None:
        return renderer
    if _renderer is not None:
        return _renderer
    return WeasyPrintRenderer()


def set_renderer(renderer: PdfRenderer | None) -> None:
    """Override the process-wide renderer (tests, and a future ReportLab form)."""
    global _renderer
    _renderer = renderer


def fingerprint_context(context: dict[str, Any]) -> str:
    """SHA-256 of the canonical JSON of a render context.

    Reuses ``core.audit.canonical_json`` so the fingerprint is stable across
    processes and key insertion order — the same guarantee the audit chain
    already depends on.
    """
    return sha256_hex(canonical_json(context).encode("utf-8"))


def render_document(
    *,
    key: str,
    context: dict[str, Any],
    branding: dict[str, Any] | None = None,
    renderer: PdfRenderer | None = None,
) -> RenderedDocument:
    """Render a registered document to PDF bytes.

    Raises ``UnknownDocument`` for an unregistered key and ``RenderFailed`` if
    the template or the PDF engine produces nothing usable.
    """
    spec = registry.get_document(key)
    fingerprint = fingerprint_context(context)

    try:
        html = templates.render_html(spec.template, context)
        pdf = get_renderer(renderer).render(html, stylesheet=build_stylesheet(branding))
    except Exception as exc:  # template, font, or engine failure
        raise RenderFailed(f"rendering {key!r} failed: {exc}") from exc

    # A zero-byte or non-PDF result must never be stored: it would pass the
    # attachment allowlist only to flip a checklist item to Generated with
    # nothing behind it. Fail loudly so the task retries.
    if not pdf or not pdf.startswith(b"%PDF-"):
        raise RenderFailed(f"rendering {key!r} produced no PDF bytes")

    return RenderedDocument(
        key=key,
        title=spec.title,
        pdf=pdf,
        content_sha256=sha256_hex(pdf),
        source_fingerprint=fingerprint,
        html=html,
    )
