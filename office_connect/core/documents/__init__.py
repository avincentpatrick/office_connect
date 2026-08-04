"""Core document generation — core-services #8 (template → PDF) and #3 (frozen
snapshots), shipped together at Stage C R-5 because neither is useful alone.

Public API: the render entry point, the registry a consumer registers into, the
snapshot service, and the ops→core enqueue seam. Consumers call these; they never
touch Jinja, WeasyPrint or a storage driver directly.

The package is **pure core**: it imports only ``core.*`` and third-party
libraries, so `lint-imports` proves it can be consumed by every module without
either learning about the other. The Celery wrapper lives in ``ops/`` and injects
itself through ``register_enqueuer`` — the same inversion the notifications
outbox, the attachment scan queue and the workflow SLA sweeper already use.
"""

from office_connect.core.documents.errors import (
    DocumentError,
    RenderFailed,
    SnapshotNotFound,
    UnknownDocument,
)
from office_connect.core.documents.queue import (
    enqueue,
    generate_on_commit,
    is_wired,
    register_enqueuer,
)
from office_connect.core.documents.registry import (
    DocumentSpec,
    get_document,
    register_document,
    register_template_dir,
    registered_documents,
    template_dirs,
)
from office_connect.core.documents.render import (
    PdfRenderer,
    RenderedDocument,
    WeasyPrintRenderer,
    fingerprint_context,
    get_renderer,
    render_document,
    set_renderer,
)
from office_connect.core.documents.snapshots import (
    ACTIVE,
    SUPERSEDED,
    VOIDED,
    active_snapshots,
    find_active,
    freeze_snapshot,
    stale_snapshots,
    void_snapshots,
)
from office_connect.core.documents.stylesheet import build_stylesheet

__all__ = [
    "ACTIVE",
    "SUPERSEDED",
    "VOIDED",
    "DocumentError",
    "DocumentSpec",
    "PdfRenderer",
    "RenderFailed",
    "RenderedDocument",
    "SnapshotNotFound",
    "UnknownDocument",
    "WeasyPrintRenderer",
    "active_snapshots",
    "build_stylesheet",
    "enqueue",
    "find_active",
    "fingerprint_context",
    "freeze_snapshot",
    "generate_on_commit",
    "get_document",
    "get_renderer",
    "is_wired",
    "register_document",
    "register_enqueuer",
    "register_template_dir",
    "registered_documents",
    "render_document",
    "set_renderer",
    "stale_snapshots",
    "template_dirs",
    "void_snapshots",
]
