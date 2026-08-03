"""Shared builders for the R-3 documentary-packet tests.

``satisfy_packet`` attaches a real JPEG to every blocking item **through the
production service** (``services/checklist.attach_evidence``), never by writing
rows directly. That is deliberate: the helper every submitting test depends on
is then itself an end-to-end exercise of upload → join row → mirror → status
recompute, so a regression in the wiring turns 40 tests red rather than hiding
behind a hand-built fixture.
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image

from office_connect.modules.reimbursement.services import checklist


def tiny_jpeg(color=(120, 90, 60)) -> bytes:
    """A real 16×16 JPEG — the magic-byte allowlist in core attachments is
    genuine, so a fake ``b"not-an-image"`` would be rejected."""
    buf = BytesIO()
    Image.new("RGB", (16, 16), color).save(buf, "JPEG")
    return buf.getvalue()


async def satisfy_packet(session, *, claim, actor_user_id: int) -> list[int]:
    """Attach a file to every item currently blocking this claim's submit.

    Returns the catalog ids satisfied. Idempotent-ish: a second call finds
    nothing blocking and does nothing.
    """
    view = await checklist.checklist_view(session, claim=claim)
    satisfied = []
    for blocker in view.status.blocking:
        await checklist.attach_evidence(
            session,
            claim=claim,
            catalog_id=blocker.catalog_id,
            data=tiny_jpeg(),
            filename=f"{blocker.code}.jpg",
            declared_mime="image/jpeg",
            actor_user_id=actor_user_id,
        )
        satisfied.append(blocker.catalog_id)
    await session.flush()
    return satisfied


async def satisfy_packet_over_http(client, claim_id: int, *, base=None) -> list[str]:
    """The wizard's Documents step, driven over HTTP — multipart and all.

    Used by the end-to-end wizard walks so they exercise the real 5-step
    journey rather than reaching past the gate. Returns the codes satisfied.
    """
    from tests.conftest import CSRF

    base = base or "/api/v1/reimbursement"
    listed = await client.get(f"{base}/claims/{claim_id}/checklist")
    assert listed.status_code == 200, listed.text

    codes = []
    for blocker in listed.json()["summary"]["blocking"]:
        posted = await client.post(
            f"{base}/claims/{claim_id}/checklist/{blocker['catalog_id']}/attachments",
            files={"file": (f"{blocker['code']}.jpg", tiny_jpeg(), "image/jpeg")},
            headers=CSRF,
        )
        assert posted.status_code == 201, posted.text
        codes.append(blocker["code"])
    return codes


async def blocking_codes(session, *, claim) -> list[str]:
    """The catalog codes standing between this claim and submit."""
    view = await checklist.checklist_view(session, claim=claim)
    return sorted(item.code for item in view.status.blocking)
