"""Document + template registry (core-service #8).

The inversion that lets core render a module's government form without ever
importing the module. A consumer registers, at import time:

- its **template directory**, appended to the Jinja search path, and
- one **DocumentSpec** per document key it can produce.

Core then knows a document key maps to a template and a title, and nothing else.
It never learns what a claim is. `lint-imports` is the proof: the contract
"core may not import modules" stays green precisely because this file inverts the
dependency, exactly as ``core/attachments/authz.py`` inverts holder authorization
and ``core/checklist/`` inverts checklist storage.

Keys are namespaced by their owning module (``reimb.iot45``) so two modules can
never collide on a bare form number — GAM App 45 means one thing to
reimbursement and could mean another to supply.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from office_connect.core.documents.errors import UnknownDocument


@dataclass(frozen=True)
class DocumentSpec:
    """What core needs to render one document kind.

    ``title`` is the human name that reaches the PDF's running header and the
    attachment filename; ``paper`` and ``orientation`` feed the ``@page`` rule.
    """

    key: str
    template: str
    title: str
    paper: str = "A4"
    orientation: str = "portrait"


_documents: dict[str, DocumentSpec] = {}
_template_dirs: list[Path] = []


def register_template_dir(path: Path | str) -> None:
    """Append a directory to the Jinja search path (idempotent)."""
    resolved = Path(path).resolve()
    if resolved not in _template_dirs:
        _template_dirs.append(resolved)


def template_dirs() -> tuple[Path, ...]:
    """Every registered template directory, in registration order."""
    return tuple(_template_dirs)


def register_document(spec: DocumentSpec) -> DocumentSpec:
    """Register one document kind. Re-registering the same key replaces it.

    Replacement rather than a raise: modules are imported once per process, but
    the test suite re-imports freely, and a registry that explodes on reload
    would make the seam hostile to exactly the tests that prove it works.
    """
    _documents[spec.key] = spec
    return spec


def get_document(key: str) -> DocumentSpec:
    """The spec for ``key``, or raise ``UnknownDocument``."""
    try:
        return _documents[key]
    except KeyError:
        raise UnknownDocument(f"no document registered for key {key!r}") from None


def registered_documents() -> tuple[DocumentSpec, ...]:
    """Every registered spec — used by the admin surface and by tests."""
    return tuple(_documents.values())
