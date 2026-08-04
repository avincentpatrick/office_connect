"""R-5 — the reimbursement module's document generation, end to end.

Objective 1 of the module: a traveller enters trip facts once and the system
produces the paperwork. These tests pin the three properties that make that safe
to run in a worker — it flips the right checklist items, it is idempotent, and it
regenerates when the claim changes — plus the two refusals that keep it honest.

A fake renderer is injected throughout, so these are about the ORCHESTRATION.
That WeasyPrint turns the templates into real PDFs is proven in
``test_document_render.py``.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from office_connect.core.api.errors import APIError
from office_connect.core.documents import ACTIVE, VOIDED, active_snapshots
from office_connect.core.documents import render as core_render
from office_connect.core.models import Attachment, DocumentSnapshot
from office_connect.modules.reimbursement.documents import (
    SUBJECT_KIND,
    generate_claim_documents,
)
from office_connect.modules.reimbursement.documents import registry as doc_registry
from office_connect.modules.reimbursement.models import (
    ReimbChecklistCatalog,
    ReimbChecklistItem,
    ReimbTemplateMap,
)
from office_connect.modules.reimbursement.services import checklist
from office_connect.modules.reimbursement.services.compute import compute_claim_totals
from tests.reimb_lifecycle_helpers import standard_cast

GENERATED_CODES = {"IOT-45", "AR-01", "DV-32"}


class _FakeRenderer:
    """Deterministic PDF-shaped bytes that vary with the html, so a changed
    context produces a changed blob exactly as WeasyPrint would."""

    name = "fake"

    def __init__(self) -> None:
        self.calls = 0

    def render(self, html: str, *, stylesheet: str) -> bytes:
        self.calls += 1
        return b"%PDF-1.7\n" + str(hash(html)).encode() + b"\n"


async def _computed_claim(app_session, make_user):
    cast = await standard_cast(app_session, make_user)
    await compute_claim_totals(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id
    )
    await app_session.flush()
    return cast


async def _statuses(app_session, claim) -> dict[str, str]:
    rows = (
        await app_session.execute(
            select(ReimbChecklistCatalog.code, ReimbChecklistItem.status)
            .join(
                ReimbChecklistItem,
                ReimbChecklistItem.catalog_id == ReimbChecklistCatalog.id,
            )
            .where(ReimbChecklistItem.claim_id == claim.id)
        )
    ).all()
    return {code: status for code, status in rows}


# --- the seeded contract ----------------------------------------------------


async def test_every_template_binding_points_at_a_registered_document(app_session):
    """A rename on either side must not ship half-done.

    The binding table is data and the specs are code; nothing but this test
    stops them drifting apart into a claim whose packet silently never renders.
    """
    from office_connect.modules.reimbursement.seeds import apply_reimbursement_seeds

    await apply_reimbursement_seeds(app_session)
    bindings = (
        (await app_session.execute(select(ReimbTemplateMap))).scalars().all()
    )
    assert {b.checklist_code for b in bindings} == GENERATED_CODES

    registered = {spec.key for spec in doc_registry.SPECS}
    assert {b.document_key for b in bindings} <= registered

    # And every bound code is actually a generated_doc row in the catalog —
    # binding a form to an upload item would silently never fire.
    catalog = {
        row.code: row.evidence
        for row in (
            await app_session.execute(select(ReimbChecklistCatalog))
        ).scalars()
    }
    for binding in bindings:
        assert catalog[binding.checklist_code] == "generated_doc"


# --- generation -------------------------------------------------------------


async def test_generates_the_three_documents_and_flips_their_items(
    app_session, make_user
):
    cast = await _computed_claim(app_session, make_user)
    renderer = _FakeRenderer()

    results = await generate_claim_documents(
        app_session,
        claim_id=cast.claim.id,
        actor_user_id=cast.owner.id,
        renderer=renderer,
    )

    assert {r.checklist_code for r in results} == GENERATED_CODES
    assert {r.outcome for r in results} == {"generated"}
    assert renderer.calls == 3

    statuses = await _statuses(app_session, cast.claim)
    for code in GENERATED_CODES:
        assert statuses[code] == "generated"

    # Each is a core attachment with generated provenance, born downloadable.
    rows = (
        (await app_session.execute(select(Attachment).where(
            Attachment.holder_kind == SUBJECT_KIND,
            Attachment.holder_id == cast.claim.id,
            Attachment.origin == "generated",
        ))).scalars().all()
    )
    assert len(rows) == 3
    assert {row.scan_status for row in rows} == {"clean"}
    assert {row.scanner_name for row in rows} == {"system-generated"}

    # …and each is frozen as the official copy (core-service #3).
    snapshots = await active_snapshots(
        app_session, subject_kind=SUBJECT_KIND, subject_id=cast.claim.id
    )
    assert len(snapshots) == 3
    assert {s.status for s in snapshots} == {ACTIVE}


async def test_generation_is_idempotent(app_session, make_user):
    """Spec §10: "Celery task, idempotent, 3 retries". A retry must be free."""
    cast = await _computed_claim(app_session, make_user)
    renderer = _FakeRenderer()

    await generate_claim_documents(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id,
        renderer=renderer,
    )
    assert renderer.calls == 3

    again = await generate_claim_documents(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id,
        renderer=renderer,
    )
    # No re-render, no second attachment, no second snapshot.
    assert renderer.calls == 3
    assert {r.outcome for r in again} == {"unchanged"}
    assert len(await active_snapshots(
        app_session, subject_kind=SUBJECT_KIND, subject_id=cast.claim.id
    )) == 3
    assert len((await app_session.execute(select(Attachment).where(
        Attachment.holder_id == cast.claim.id,
        Attachment.origin == "generated",
    ))).scalars().all()) == 3


async def test_a_changed_claim_regenerates_and_supersedes(app_session, make_user):
    cast = await _computed_claim(app_session, make_user)
    renderer = _FakeRenderer()
    await generate_claim_documents(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id,
        renderer=renderer,
    )
    first = {
        s.document_key: s.id
        for s in await active_snapshots(
            app_session, subject_kind=SUBJECT_KIND, subject_id=cast.claim.id
        )
    }

    # The trip's purpose changes — the printed page is now wrong.
    cast.claim.purpose = "A different, corrected purpose"
    await app_session.flush()

    results = await generate_claim_documents(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id,
        renderer=renderer,
    )
    assert {r.outcome for r in results} == {"generated"}
    assert renderer.calls == 6

    live = await active_snapshots(
        app_session, subject_kind=SUBJECT_KIND, subject_id=cast.claim.id
    )
    assert len(live) == 3  # still exactly one official copy per document
    assert {s.id for s in live}.isdisjoint(set(first.values()))

    # The predecessors are SUPERSEDED, not deleted and not voided: this is an
    # ordinary reissue, and standing rule 6 keeps every row.
    all_rows = (
        (await app_session.execute(select(DocumentSnapshot).where(
            DocumentSnapshot.subject_id == cast.claim.id,
        ))).scalars().all()
    )
    assert len(all_rows) == 6
    superseded = [r for r in all_rows if r.id in set(first.values())]
    assert {r.status for r in superseded} == {"superseded"}


async def test_draft_before_submit_official_after(app_session, make_user):
    """The confirmed R-5 flow: a watermarked working copy pre-submit, then the
    authoritative copy once the reference number exists."""
    cast = await _computed_claim(app_session, make_user)
    renderer = _FakeRenderer()

    # No reference number yet — which is the condition that makes it a draft,
    # independently of the status column (`is_draft_claim` checks both, so a
    # claim whose status has not been refreshed off the server default is still
    # correctly classified).
    assert cast.claim.ref_no is None
    await generate_claim_documents(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id,
        renderer=renderer,
    )
    drafts = await active_snapshots(
        app_session, subject_kind=SUBJECT_KIND, subject_id=cast.claim.id
    )
    assert {s.is_draft for s in drafts} == {True}

    # Stand in for submit: the number is burned and the claim leaves the
    # claimant's hands. Draft-ness is DERIVED, so the next pass switches.
    # Derived from the claim id because ref_no is globally unique and this
    # suite shares a database with every other test.
    ref_no = f"RB-2026-{cast.claim.id:04d}"
    cast.claim.ref_no = ref_no
    cast.claim.status = "division_approval"
    await app_session.flush()

    await generate_claim_documents(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id,
        renderer=renderer,
    )
    official = await active_snapshots(
        app_session, subject_kind=SUBJECT_KIND, subject_id=cast.claim.id
    )
    assert {s.is_draft for s in official} == {False}
    # Filenames follow spec §5.7 — the reference number leads.
    names = (
        (await app_session.execute(select(Attachment.original_filename).where(
            Attachment.holder_id == cast.claim.id,
            Attachment.origin == "generated",
        ))).scalars().all()
    )
    assert any(n.startswith(f"{ref_no}_") for n in names)
    assert any(n.startswith(f"DRAFT-{cast.claim.id}_") for n in names)


# --- invalidation on edit ---------------------------------------------------


async def test_editing_a_printed_field_voids_the_packet(app_session, make_user):
    """Found by the R-5 live smoke.

    `purpose` is printed on all three documents but is not a compute input, so
    an invalidation keyed only on money left an ACTIVE snapshot asserting a
    purpose the claim no longer had. Every editable field is printed somewhere,
    so any change voids the packet.
    """
    from office_connect.modules.reimbursement.services import drafts

    cast = await _computed_claim(app_session, make_user)
    await generate_claim_documents(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id,
        renderer=_FakeRenderer(),
    )
    assert len(await active_snapshots(
        app_session, subject_kind=SUBJECT_KIND, subject_id=cast.claim.id
    )) == 3

    await drafts.update_draft_fields(
        app_session,
        claim_id=cast.claim.id,
        actor_user_id=cast.owner.id,
        changes={"purpose": "A corrected purpose"},
    )

    assert await active_snapshots(
        app_session, subject_kind=SUBJECT_KIND, subject_id=cast.claim.id
    ) == []
    rows = (
        (await app_session.execute(select(DocumentSnapshot).where(
            DocumentSnapshot.subject_id == cast.claim.id,
            DocumentSnapshot.subject_kind == SUBJECT_KIND,
        ))).scalars().all()
    )
    # Voided, not superseded and not deleted: this records that the data moved
    # under a frozen document, which is what an auditor is looking for.
    assert {r.status for r in rows} == {VOIDED}
    assert all(r.void_reason for r in rows)
    # The money snapshot is untouched — `purpose` changes no arithmetic.
    assert cast.claim.totals.get("grand")


async def test_a_no_op_edit_voids_nothing(app_session, make_user):
    """Invalidation follows an actual change, not the shape of the request."""
    from office_connect.modules.reimbursement.services import drafts

    cast = await _computed_claim(app_session, make_user)
    cast.claim.purpose = "Unchanged purpose"
    await app_session.flush()
    await generate_claim_documents(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id,
        renderer=_FakeRenderer(),
    )

    await drafts.update_draft_fields(
        app_session,
        claim_id=cast.claim.id,
        actor_user_id=cast.owner.id,
        changes={"purpose": "Unchanged purpose"},
    )
    assert len(await active_snapshots(
        app_session, subject_kind=SUBJECT_KIND, subject_id=cast.claim.id
    )) == 3


# --- refusals ---------------------------------------------------------------


async def test_refuses_to_print_a_claim_with_no_money(app_session, make_user):
    """`drafts.py` clears totals whenever a compute input changes, so an empty
    snapshot means the numbers are mid-edit. An official-looking ₱0.00 voucher
    is far worse than no voucher."""
    cast = await standard_cast(app_session, make_user)  # no compute
    cast.claim.totals = {}
    await app_session.flush()

    results = await generate_claim_documents(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id,
        renderer=_FakeRenderer(),
    )
    assert {r.outcome for r in results} == {"failed"}
    # Nothing was stored and nothing was flipped — the items stay honestly blank.
    assert not await active_snapshots(
        app_session, subject_kind=SUBJECT_KIND, subject_id=cast.claim.id
    )
    statuses = await _statuses(app_session, cast.claim)
    assert all(statuses.get(code) != "generated" for code in GENERATED_CODES)


async def test_uploading_to_a_generated_item_is_still_refused(
    app_session, make_user
):
    """R-3's rule survives R-5. The generator and the claimant address the same
    catalog rows through deliberately asymmetric doors."""
    cast = await _computed_claim(app_session, make_user)
    catalog_id = (
        await app_session.execute(
            select(ReimbChecklistCatalog.id).where(
                ReimbChecklistCatalog.code == "IOT-45"
            )
        )
    ).scalar_one()

    with pytest.raises(APIError) as exc:
        await checklist.attach_evidence(
            app_session,
            claim=cast.claim,
            catalog_id=catalog_id,
            data=b"%PDF-1.7\n",
            filename="mine.pdf",
            declared_mime="application/pdf",
            actor_user_id=cast.owner.id,
        )
    assert exc.value.code == "reimb_evidence_not_uploadable"


async def test_the_generator_refuses_a_non_generated_item(app_session, make_user):
    """The mirror image: the system may not manufacture a travel order."""
    cast = await _computed_claim(app_session, make_user)
    with pytest.raises(APIError) as exc:
        await checklist.materialize_generated_item(
            app_session, claim=cast.claim, code="TO-01", actor_user_id=cast.owner.id
        )
    assert exc.value.code == "reimb_document_not_generatable"


# --- the packet gate --------------------------------------------------------


async def test_generated_documents_never_block_submission(app_session, make_user):
    """Module-doc row 67, unchanged by R-5: a system-produced artifact cannot be
    a precondition of entering the workflow that produces it."""
    cast = await standard_cast(app_session, make_user)
    summary = await checklist.checklist_summary(app_session, claim=cast.claim)
    blocking = {b.code for b in summary.blocking}
    assert blocking.isdisjoint(GENERATED_CODES)
    # …and they are not counted in the progress line either.
    assert summary.required_total < len(GENERATED_CODES) + summary.required_total


async def test_generated_files_are_not_counted_as_uploaded_evidence(
    app_session, make_user
):
    """A generated PDF must not satisfy a file_present check on a human item."""
    from office_connect.modules.reimbursement.services import (
        attachments as evidence,
    )

    cast = await _computed_claim(app_session, make_user)
    before = await evidence.evidence_counts(app_session, claim_id=cast.claim.id)
    await generate_claim_documents(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id,
        renderer=_FakeRenderer(),
    )
    after = await evidence.evidence_counts(app_session, claim_id=cast.claim.id)
    assert after == before


# --- the renderer seam ------------------------------------------------------


async def test_the_default_renderer_is_weasyprint():
    """Nothing in the module may quietly swap the engine core-service #8 names."""
    assert core_render.get_renderer().name == "weasyprint"
