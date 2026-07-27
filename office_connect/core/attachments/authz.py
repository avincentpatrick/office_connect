"""Download authorization for attachments (Stage B / Increment 4).

Two layers:
1. **Coarse RBAC** — the HTTP route declares ``require_permission('attachment.download')``.
2. **Holder scoping** — the per-row ``authorize`` hook ``download_attachment`` calls.
   ``core_attachments.(holder_kind, holder_id)`` is a sanctioned polymorphic ref;
   a module resolves authorization "through the entity named by holder_kind"
   (foundation §4). No holder modules exist in B4, so this is the extension point:
   a module registers how downloads of the attachments it owns are authorized
   (e.g. ``'reimb_claim'`` → can this actor see that claim), keyed by
   ``holder_kind`` — wiring reimb at Stage C needs zero router change.

With no authorizer registered the hook allows anything the RBAC gate let through.
The service converts any exception the hook raises into ``UnauthorizedDownload``
(fail-closed), so a Stage-C authorizer raising anything denies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.attachments.service import AuthorizeHook
from office_connect.core.auth.principal import Principal
from office_connect.core.models import Attachment


@dataclass(frozen=True)
class AuthzContext:
    """What a holder authorizer needs to decide a download: the acting principal
    and a live session to resolve the holder entity."""

    principal: Principal
    session: AsyncSession


HolderAuthorizer = Callable[[Attachment, AuthzContext], "Awaitable[None] | None"]
_holder_authorizers: dict[str, HolderAuthorizer] = {}


def register_holder_authorizer(holder_kind: str, fn: HolderAuthorizer) -> None:
    """Stage-C seam: register how downloads of a holder's attachments are gated."""
    _holder_authorizers[holder_kind] = fn


def make_download_authorizer(ctx: AuthzContext) -> AuthorizeHook:
    """Build the ``authorize`` hook for one request's principal + session."""

    def _authorize(row: Attachment):
        if not row.holder_kind:
            return None  # unowned → the coarse RBAC gate is authoritative → allow
        holder = _holder_authorizers.get(row.holder_kind)
        if holder is None:
            return None  # no module wired yet → RBAC gate authoritative → allow
        return holder(row, ctx)  # holder-scoped check (raise to deny)

    return _authorize
