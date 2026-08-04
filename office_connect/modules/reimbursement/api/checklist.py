"""The documentary packet endpoints — read the checklist, attach/detach evidence.

**Why the module owns the upload rather than reusing ``POST /api/v1/attachments``
plus a link call** (recorded as api-standards §9b):

1. *Atomicity.* Attaching is upload + join row + mirror + status recompute in ONE
   transaction. Two HTTP calls leave a window where a stored, scanned,
   permission-gated file exists with no owner — and if the link call fails you
   have an orphan nobody can find.
2. *Authorization.* The real rule is "may this actor edit THIS claim's packet"
   (owner, and only while the claim is editable). A coarse ``attachment.upload``
   permission cannot express that — the same argument api-standards §9 makes for
   read scoping, applied to writes.

The module still never touches a storage driver: every byte goes through
``core.attachments`` (Rule 10). Downloads stay on the core route, now claim-scoped
by the holder authorizer ``services/attachments.py`` registers.

Transaction discipline as everywhere else: the services flush, this layer owns
exactly one ``session.commit()`` per handler.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.api.errors import APIError
from office_connect.core.attachments.errors import AttachmentError, RejectedUpload
from office_connect.core.attachments.scan_queue import scan_on_commit
from office_connect.core.auth.dependencies import require_permission
from office_connect.core.auth.principal import Principal
from office_connect.core.config import get_settings
from office_connect.core.db import get_session
from office_connect.core.documents import generate_on_commit
from office_connect.core.documents import queue as documents_queue
from office_connect.modules.reimbursement.api.deps import (
    can_read_claim,
    checklist_out,
    get_claim,
)
from office_connect.modules.reimbursement.api.schemas import (
    ChecklistOut,
    GenerateDocumentsOut,
)
from office_connect.modules.reimbursement.services import attachments as evidence
from office_connect.modules.reimbursement.services import checklist, drafts, errors

router = APIRouter()


async def _read_capped(file: UploadFile, max_bytes: int) -> bytes:
    """Read the upload into memory, aborting at the cap (deterministic 413).

    Mirrors ``core/api/attachments.py::_read_capped`` — same cap, same status,
    same message, so a claimant hitting the limit through the packet screen and
    through the generic route get identical answers.
    """
    if file.size is not None and file.size > max_bytes:
        raise APIError(413, "payload_too_large", "The file exceeds the maximum size.")
    buf = bytearray()
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > max_bytes:
            raise APIError(
                413, "payload_too_large", "The file exceeds the maximum size."
            )
    return bytes(buf)


@router.get("/claims/{claim_id}/checklist", response_model=ChecklistOut)
async def read_checklist(
    claim_id: int,
    principal: Principal = Depends(require_permission("reimb.claim.read")),
    session: AsyncSession = Depends(get_session),
):
    """The claim's packet. **Writes nothing** — planned-but-unmaterialized items
    come back with ``item_id: null``, and because every write below is keyed on
    ``catalog_id`` the client never needs a row to exist before it can act."""
    claim = await get_claim(session, claim_id)
    if not await can_read_claim(
        session, actor_user_id=principal.user_id, claim=claim
    ):
        raise errors.not_claim_owner()
    return checklist_out(await checklist.checklist_view(session, claim=claim))


@router.post(
    "/claims/{claim_id}/checklist/{catalog_id}/attachments",
    response_model=ChecklistOut,
    status_code=201,
)
async def attach_evidence(
    claim_id: int,
    catalog_id: int,
    file: UploadFile = File(...),
    principal: Principal = Depends(require_permission("reimb.claim.create")),
    session: AsyncSession = Depends(get_session),
):
    """Upload evidence against a checklist item.

    ``reimb.claim.create`` rather than a new permission: editing the packet IS
    editing the claim, exactly like ``PATCH /claims/{id}``. The real gate is
    ``drafts.owned_editable_claim`` — owner, and only while the claim is a draft
    or returned.
    """
    settings = get_settings()
    data = await _read_capped(file, settings.attachment_max_bytes)
    claim = await drafts.owned_editable_claim(
        session, claim_id=claim_id, actor_user_id=principal.user_id
    )
    try:
        view, attachment_id = await checklist.attach_evidence(
            session,
            claim=claim,
            catalog_id=catalog_id,
            data=data,
            filename=file.filename or "upload",
            declared_mime=file.content_type,
            actor_user_id=principal.user_id,
        )
    except RejectedUpload as exc:
        raise APIError(
            422, "attachment_rejected", "The file type is not allowed."
        ) from exc
    except AttachmentError as exc:  # pragma: no cover - defensive
        raise APIError(500, "internal_error", "An internal error occurred.") from exc

    payload = checklist_out(view)
    # Strictly after commit — the row must be visible before the worker looks
    # for it; a rolled-back upload must never enqueue.
    scan_on_commit(session, attachment_id)
    await session.commit()
    return payload


@router.post(
    "/claims/{claim_id}/documents/generate",
    response_model=GenerateDocumentsOut,
    status_code=202,
)
async def generate_documents(
    claim_id: int,
    principal: Principal = Depends(require_permission("reimb.claim.create")),
    session: AsyncSession = Depends(get_session),
):
    """Queue generation of the claim's packet (core-service #8).

    **202, never 200.** Rendering happens in the worker — master-plan §1.1 #8 is
    explicit that WeasyPrint never runs in a request path — so this handler
    cannot return the finished documents. It returns the packet as it stands plus
    whether the render was actually queued, and the client polls the checklist.

    On the **gated** router, not ``api/actions.py``: generating paperwork is not
    a decision on an in-flight workflow instance, so the §9a exemption does not
    apply and the module flag should hide it like every other module surface.

    Degrades non-blockingly (spec §19.12). No worker wired means ``queued:
    false`` and a notice in the UI — never a 500, never a refused save. The
    caller may ask again as often as it likes: generation is idempotent by
    fingerprint, so a duplicate request renders nothing new.
    """
    claim = await drafts.owned_editable_claim(
        session, claim_id=claim_id, actor_user_id=principal.user_id
    )
    # Refuse early, with the specific reason, rather than letting the worker
    # discover it and leave the user staring at a packet that never appears.
    if not (claim.totals or {}).get("grand"):
        raise errors.totals_missing()

    generate_on_commit(session, evidence.HOLDER_KIND, claim.id)
    payload = GenerateDocumentsOut(
        checklist=checklist_out(await checklist.checklist_view(session, claim=claim)),
        queued=documents_queue.is_wired(),
    )
    await session.commit()
    return payload


@router.delete(
    "/claims/{claim_id}/checklist/{catalog_id}/attachments/{attachment_id}",
    response_model=ChecklistOut,
)
async def detach_evidence(
    claim_id: int,
    catalog_id: int,
    attachment_id: int,
    principal: Principal = Depends(require_permission("reimb.claim.create")),
    session: AsyncSession = Depends(get_session),
):
    """Remove evidence from a checklist item.

    ``attachment_id`` is the ``reimb_attachments`` join row, not the core
    attachment — the join is what this module owns. Both rows are soft-deleted;
    the stored bytes are never touched (retention, standing rule 6).
    """
    claim = await drafts.owned_editable_claim(
        session, claim_id=claim_id, actor_user_id=principal.user_id
    )
    view = await checklist.detach_evidence(
        session,
        claim=claim,
        catalog_id=catalog_id,
        reimb_attachment_id=attachment_id,
        actor_user_id=principal.user_id,
    )
    payload = checklist_out(view)
    await session.commit()
    return payload
