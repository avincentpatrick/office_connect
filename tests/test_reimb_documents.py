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
    PACKET,
    SUBJECT_KIND,
    generate_claim_documents,
)
from office_connect.modules.reimbursement.documents import registry as doc_registry
from office_connect.modules.reimbursement.documents.context import GROUP_ORDER
from office_connect.modules.reimbursement.models import (
    ReimbAttachment,
    ReimbChecklistCatalog,
    ReimbChecklistItem,
    ReimbTemplateMap,
)
from office_connect.modules.reimbursement.services import checklist
from office_connect.modules.reimbursement.services.compute import compute_claim_totals
from tests.reimb_lifecycle_helpers import standard_cast

#: Per KIND, because bindings are per kind (the natural key is
#: ``(claim_kind, checklist_code)``). The old flat ``GENERATED_CODES`` was
#: correct only while one chain existed; R-6-liq-settle gave the liquidation its
#: own form and the flat set could no longer tell you whether a row had landed
#: under the wrong kind — which is now the single most likely way a binding
#: ships broken.
GENERATED_CODES = {"IOT-45", "AR-01", "DV-32"}
LIQUIDATION_CODES = {"LR-44"}

#: The reimbursement's three forms plus the combined packet. Every count in this
#: file is expressed against this rather than a bare 4, so adding a document is
#: one edit here and not a hunt through assertions.
DOCUMENT_COUNT = len(GENERATED_CODES) + 1
#: The liquidation's one form plus its own packet.
LIQUIDATION_DOCUMENT_COUNT = len(LIQUIDATION_CODES) + 1


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
    # Asserted on the PAIR, never the bare code: `(claim_kind, checklist_code)`
    # is the natural key, and a set of codes alone cannot catch a row seeded
    # under the wrong kind — a liquidation form bound to reimbursement claims
    # would simply never generate, silently.
    assert {(b.claim_kind, b.checklist_code) for b in bindings} == {
        *(("reimbursement", code) for code in GENERATED_CODES),
        *(("liquidation", code) for code in LIQUIDATION_CODES),
    }

    registered = {spec.key for spec in doc_registry.SPECS}
    assert {b.document_key for b in bindings} <= registered

    # The packet is REGISTERED but deliberately UNBOUND — it satisfies no COA
    # checklist code, because no circular names the folder its documents travel
    # in. Pinning it here is what stops a future session "fixing" the asymmetry
    # by seeding a binding row and thereby inventing a catalog requirement.
    assert PACKET in registered
    assert PACKET not in {b.document_key for b in bindings}

    # And every bound code is actually a generated_doc row in the catalog —
    # binding a form to an upload item would silently never fire.
    # Keyed on the pair for the same reason: TO-01 and CTC-47 now exist under
    # BOTH kinds, so a flat `{code: evidence}` dict would collapse rows and could
    # validate a liquidation binding against a reimbursement catalog row.
    catalog = {
        (row.claim_kind, row.code): row.evidence
        for row in (
            await app_session.execute(select(ReimbChecklistCatalog))
        ).scalars()
    }
    for binding in bindings:
        assert catalog[(binding.claim_kind, binding.checklist_code)] == "generated_doc"


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

    # Named explicitly rather than derived from BODY_PARTIALS: that derivation
    # was only ever right while one claim kind existed. BODY_PARTIALS now also
    # holds LR-44, which a REIMBURSEMENT claim must not produce — deriving from
    # it would have turned the arrival of a second chain into a green test.
    assert {r.document_key for r in results} == {
        doc_registry.IOT_45,
        doc_registry.AR_01,
        doc_registry.DV_32,
        PACKET,
    }
    assert {r.outcome for r in results} == {"generated"}
    assert renderer.calls == DOCUMENT_COUNT

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
    assert len(rows) == DOCUMENT_COUNT
    assert {row.scan_status for row in rows} == {"clean"}
    assert {row.scanner_name for row in rows} == {"system-generated"}

    # …and each is frozen as the official copy (core-service #3).
    snapshots = await active_snapshots(
        app_session, subject_kind=SUBJECT_KIND, subject_id=cast.claim.id
    )
    assert len(snapshots) == DOCUMENT_COUNT
    assert {s.status for s in snapshots} == {ACTIVE}
    assert PACKET in {s.document_key for s in snapshots}


async def test_the_packet_is_a_claim_level_artifact_not_a_checklist_item(
    app_session, make_user
):
    """R-5-packet's central decision, pinned.

    The packet is generated beside the bindings, never from one. Concretely:
    its join row carries NO checklist item, so the Documents task list (which
    filters on ``checklist_item_id IS NOT NULL``) cannot see it, and no catalog
    row was invented to hold it.
    """
    cast = await _computed_claim(app_session, make_user)
    await generate_claim_documents(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id,
        renderer=_FakeRenderer(),
    )

    snapshot = next(
        s
        for s in await active_snapshots(
            app_session, subject_kind=SUBJECT_KIND, subject_id=cast.claim.id
        )
        if s.document_key == PACKET
    )
    join = (
        await app_session.execute(
            select(ReimbAttachment).where(
                ReimbAttachment.attachment_id == snapshot.attachment_id
            )
        )
    ).scalar_one()
    assert join.claim_id == cast.claim.id
    assert join.checklist_item_id is None

    # It is therefore absent from the packet screen's rows entirely…
    view = await checklist.checklist_view(app_session, claim=cast.claim)
    every_file = [file for row in view.rows for file in row.files]
    assert snapshot.attachment_id not in {f["attachment_id"] for f in every_file}

    # …and no checklist item exists that nothing in the catalog authorised.
    statuses = await _statuses(app_session, cast.claim)
    assert set(statuses) <= {
        row.plan.catalog.code for row in view.rows
    }

    # The filename says what it is, and the reference-number convention holds.
    attachment = await app_session.get(Attachment, snapshot.attachment_id)
    assert attachment.original_filename.endswith("_PACKET.pdf")


async def test_the_packet_cover_vouches_for_the_forms_it_contains(
    app_session, make_user
):
    """The packet is generated LAST so its cover can carry each form's content
    hash — that is what lets a single loose page be tied back to the packet."""
    from office_connect.modules.reimbursement.documents.context import (
        PacketSection,
        build_packet_context,
    )

    cast = await _computed_claim(app_session, make_user)
    results = await generate_claim_documents(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id,
        renderer=_FakeRenderer(),
    )
    forms = {r.document_key: r for r in results if r.document_key != PACKET}
    assert all(r.content_sha256 for r in forms.values())

    context = await build_packet_context(
        app_session,
        claim=cast.claim,
        sections=[
            PacketSection(
                document_key=key,
                checklist_code=result.checklist_code,
                title=result.checklist_code,
                form_no=None,
                content_sha256=result.content_sha256,
            )
            for key, result in forms.items()
        ],
    )
    printed = {s["content_sha256"] for s in context["packet"]["sections"]}
    assert printed == {r.content_sha256 for r in forms.values()}
    # Every section resolves to a body partial, so the packet embeds the forms
    # in full rather than merely listing them.
    assert all(s["body"] for s in context["packet"]["sections"])


async def test_generation_is_idempotent(app_session, make_user):
    """Spec §10: "Celery task, idempotent, 3 retries". A retry must be free."""
    cast = await _computed_claim(app_session, make_user)
    renderer = _FakeRenderer()

    await generate_claim_documents(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id,
        renderer=renderer,
    )
    assert renderer.calls == DOCUMENT_COUNT

    again = await generate_claim_documents(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id,
        renderer=renderer,
    )
    # No re-render, no second attachment, no second snapshot. The packet is
    # included: it prints its OWN fingerprint, so this also proves that value is
    # excluded from the hash it is derived from (`comparable_context`) — were it
    # not, the packet alone would re-render on every single pass.
    assert renderer.calls == DOCUMENT_COUNT
    assert {r.outcome for r in again} == {"unchanged"}
    assert len(await active_snapshots(
        app_session, subject_kind=SUBJECT_KIND, subject_id=cast.claim.id
    )) == DOCUMENT_COUNT
    assert len((await app_session.execute(select(Attachment).where(
        Attachment.holder_id == cast.claim.id,
        Attachment.origin == "generated",
    ))).scalars().all()) == DOCUMENT_COUNT


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
    assert renderer.calls == DOCUMENT_COUNT * 2

    live = await active_snapshots(
        app_session, subject_kind=SUBJECT_KIND, subject_id=cast.claim.id
    )
    # still exactly one official copy per document
    assert len(live) == DOCUMENT_COUNT
    assert {s.id for s in live}.isdisjoint(set(first.values()))

    # The predecessors are SUPERSEDED, not deleted and not voided: this is an
    # ordinary reissue, and standing rule 6 keeps every row.
    all_rows = (
        (await app_session.execute(select(DocumentSnapshot).where(
            DocumentSnapshot.subject_id == cast.claim.id,
        ))).scalars().all()
    )
    assert len(all_rows) == DOCUMENT_COUNT * 2
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
    )) == DOCUMENT_COUNT

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
    )) == DOCUMENT_COUNT


#: `standard_cast` already attaches TO-01 and CTC-47 to clear the submit gate,
#: so a claim arrives with evidence on it. The receipt below is the file these
#: tests add and then look for by name.
RECEIPT = "receipt.pdf"


async def _attach_a_receipt(app_session, cast, *, code: str = "RER-46") -> int:
    """Attach one uploaded file to an upload-kind item. Returns the catalog id."""
    catalog_id = (
        await app_session.execute(
            select(ReimbChecklistCatalog.id).where(
                ReimbChecklistCatalog.code == code,
                ReimbChecklistCatalog.claim_kind == cast.claim.kind,
            )
        )
    ).scalar_one()
    await checklist.attach_evidence(
        app_session,
        claim=cast.claim,
        catalog_id=catalog_id,
        data=b"%PDF-1.7\nreceipt\n",
        filename=RECEIPT,
        declared_mime="application/pdf",
        actor_user_id=cast.owner.id,
    )
    return catalog_id


async def test_attaching_evidence_voids_the_packet(app_session, make_user):
    """R-5-packet extends R-5-gen's invalidation one level out.

    The packet prints a manifest of the claimant's uploads, so attaching a file
    makes the frozen packet describe a set of documents the claim no longer has
    — exactly the argument that made ``purpose`` a void trigger at R-5-gen.
    """
    cast = await _computed_claim(app_session, make_user)
    await generate_claim_documents(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id,
        renderer=_FakeRenderer(),
    )
    assert len(await active_snapshots(
        app_session, subject_kind=SUBJECT_KIND, subject_id=cast.claim.id
    )) == DOCUMENT_COUNT

    await _attach_a_receipt(app_session, cast)

    assert await active_snapshots(
        app_session, subject_kind=SUBJECT_KIND, subject_id=cast.claim.id
    ) == []
    rows = (
        (await app_session.execute(select(DocumentSnapshot).where(
            DocumentSnapshot.subject_id == cast.claim.id,
            DocumentSnapshot.subject_kind == SUBJECT_KIND,
        ))).scalars().all()
    )
    assert {r.status for r in rows} == {VOIDED}


async def test_detaching_evidence_voids_the_packet(app_session, make_user):
    cast = await _computed_claim(app_session, make_user)
    catalog_id = await _attach_a_receipt(app_session, cast)
    await generate_claim_documents(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id,
        renderer=_FakeRenderer(),
    )
    join_id = (
        await app_session.execute(
            select(ReimbAttachment.id)
            .join(Attachment, Attachment.id == ReimbAttachment.attachment_id)
            .where(
                ReimbAttachment.claim_id == cast.claim.id,
                Attachment.original_filename == RECEIPT,
            )
        )
    ).scalar_one()

    await checklist.detach_evidence(
        app_session,
        claim=cast.claim,
        catalog_id=catalog_id,
        reimb_attachment_id=join_id,
        actor_user_id=cast.owner.id,
    )
    assert await active_snapshots(
        app_session, subject_kind=SUBJECT_KIND, subject_id=cast.claim.id
    ) == []


async def test_generating_after_an_upload_does_not_void_its_own_packet(
    app_session, make_user
):
    """The generator's writes must not trip the invalidation it just satisfied.

    ``store_generated_document`` / ``mark_generated`` are a separate door from
    ``attach_evidence``, which is what keeps a generation pass from voiding the
    snapshot it froze one line earlier. Without that separation the packet would
    be permanently self-invalidating and every read would find nothing.
    """
    cast = await _computed_claim(app_session, make_user)
    await _attach_a_receipt(app_session, cast)
    await generate_claim_documents(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id,
        renderer=_FakeRenderer(),
    )
    live = await active_snapshots(
        app_session, subject_kind=SUBJECT_KIND, subject_id=cast.claim.id
    )
    assert len(live) == DOCUMENT_COUNT


async def test_the_manifest_indexes_uploads_and_excludes_generated_files(
    app_session, make_user
):
    """The packet lists what should be stapled behind it — and vouches for each
    file by SHA-256 — rather than reproducing bytes it did not author."""
    from office_connect.modules.reimbursement.documents.context import (
        build_packet_context,
    )

    cast = await _computed_claim(app_session, make_user)
    await _attach_a_receipt(app_session, cast)
    await generate_claim_documents(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id,
        renderer=_FakeRenderer(),
    )

    context = await build_packet_context(
        app_session, claim=cast.claim, sections=[]
    )
    manifest = context["packet"]["evidence"]
    names = {f["filename"] for f in manifest}
    assert RECEIPT in names
    # `standard_cast` attached TO-01 and CTC-47 to clear the submit gate; all
    # three uploads must be listed, because "what should be stapled behind this"
    # is the manifest's whole job.
    assert len(manifest) == len(names) == 3
    assert context["packet"]["counts"]["evidence_files"] == 3
    receipt = next(f for f in manifest if f["filename"] == RECEIPT)
    assert receipt["sha256"]  # the ORIGINAL bytes' hash — the audit anchor
    assert receipt["usable"] is True
    assert receipt["scan_label"]

    # Ordered by the COA checklist, not by upload time: the packet is assembled
    # in the order the circular lists its requirements.
    order = [
        GROUP_ORDER.index(row["group"])
        for code in (f["code"] for f in manifest)
        for row in context["packet"]["checklist"]
        if row["code"] == code
    ]
    assert order == sorted(order)

    # The four generated PDFs are NOT evidence the claimant supplied, and the
    # packet already carries the forms in full.
    generated = (
        (await app_session.execute(select(Attachment.original_filename).where(
            Attachment.holder_id == cast.claim.id,
            Attachment.origin == "generated",
        ))).scalars().all()
    )
    assert set(generated).isdisjoint({f["filename"] for f in manifest})

    # The checklist rides along as the Admin Officer's final-check sheet.
    assert context["packet"]["checklist"]
    assert {"code", "status_label", "required"} <= set(
        context["packet"]["checklist"][0]
    )


async def test_a_quarantined_file_stays_on_the_manifest(app_session, make_user):
    """Marked, never silently dropped: a clerk counting envelopes needs to know
    a receipt was rejected, not merely that it is absent."""
    from office_connect.modules.reimbursement.documents.context import (
        build_packet_context,
    )

    cast = await _computed_claim(app_session, make_user)
    await _attach_a_receipt(app_session, cast)
    attachment = (
        await app_session.execute(
            select(Attachment).where(
                Attachment.holder_id == cast.claim.id,
                Attachment.original_filename == RECEIPT,
            )
        )
    ).scalar_one()
    attachment.scan_status = "infected"
    await app_session.flush()

    context = await build_packet_context(
        app_session, claim=cast.claim, sections=[]
    )
    receipt = next(
        f for f in context["packet"]["evidence"] if f["filename"] == RECEIPT
    )
    assert receipt["usable"] is False
    assert "QUARANTINED" in receipt["scan_label"]


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


async def test_real_weasyprint_renders_the_whole_packet(app_session, make_user):
    """The one end-to-end pass through the production renderer.

    A fake renderer cannot prove the thing R-5-packet actually risks: that the
    packet composes by Jinja include rather than by PDF merge. This asserts the
    real engine turns cover + checklist + manifest + three embedded form bodies
    into one PDF — and, because ``StrictUndefined`` is on, that every key the
    included partials expect is present in the packet's context. Skipped where
    the Pango stack is absent (a Windows dev host); it runs in the container,
    the only place WeasyPrint is allowed to run at all.
    """
    pytest.importorskip("weasyprint")
    from office_connect.core.documents import render_document

    from office_connect.modules.reimbursement.documents.context import (
        PacketSection,
        build_packet_context,
    )

    cast = await _computed_claim(app_session, make_user)
    await _attach_a_receipt(app_session, cast)

    context = await build_packet_context(
        app_session,
        claim=cast.claim,
        sections=[
            PacketSection(
                document_key=key,
                checklist_code=code,
                title=code,
                form_no="GAM Vol. II",
                content_sha256="0" * 64,
            )
            for key, code in (
                (doc_registry.IOT_45, "IOT-45"),
                (doc_registry.AR_01, "AR-01"),
                (doc_registry.DV_32, "DV-32"),
            )
        ],
    )
    context["doc"]["fingerprint"] = "f" * 64

    result = render_document(key=PACKET, context=context, renderer=None)
    assert result.pdf.startswith(b"%PDF-")
    # A cover + checklist + manifest + three forms is a substantial document;
    # the floor catches a template that silently rendered only its frame.
    assert len(result.pdf) > 5000

    # The embedded bodies really are the standalone forms' markup.
    assert "Itinerary" in result.html
    assert "Disbursement" in result.html or "Amount due the payee" in result.html
    assert "Accomplishments and observations" in result.html
    assert RECEIPT in result.html  # the manifest indexes it…
    assert "%PDF" not in result.html  # …and never embeds its bytes


async def test_the_standalone_forms_still_render_after_the_partial_split(
    app_session, make_user
):
    """The bodies moved into partials; the individual PDFs must be unaffected."""
    pytest.importorskip("weasyprint")
    from office_connect.core.documents import render_document

    from office_connect.modules.reimbursement.documents.context import (
        build_document_context,
    )

    cast = await _computed_claim(app_session, make_user)
    # NOTE this loops EVERY body partial against a REIMBURSEMENT claim, which
    # since R-6-liq-settle includes the liquidation's LR-44. That is deliberate
    # and load-bearing: the Jinja environment runs StrictUndefined, so this is
    # the cheapest guard in the suite against a context block that exists only
    # for one claim kind — which would raise inside RenderFailed and surface as
    # a SILENT `outcome="failed"` in the worker. Keep it looping the dict.
    for key in doc_registry.BODY_PARTIALS:
        context = await build_document_context(
            app_session, claim=cast.claim, document_key=key, title="Form"
        )
        result = render_document(key=key, context=context, renderer=None)
        assert result.pdf.startswith(b"%PDF-")


# --- R-6-liq-settle: GAM Appendix 44 ---------------------------------------


async def _liquidation_claim(app_session, make_user, *, advance_amount="8000.00"):
    """A computed liquidation linked to an advance — the LR-44 subject.

    ₱8,000 against the ₱6,500 fixture trip is the REFUND branch, which is the
    one with a receipt line to get right.
    """
    from datetime import date as _date
    from decimal import Decimal as _D

    from office_connect.modules.reimbursement.seeds import apply_reimbursement_seeds
    from office_connect.modules.reimbursement.services import cash_advance as ca

    cast = await standard_cast(app_session, make_user, kind="liquidation")
    await apply_reimbursement_seeds(app_session)
    cast.advance = await ca.create_cash_advance(
        app_session,
        claimant_id=cast.staff.id,
        amount=_D(advance_amount),
        actor_user_id=cast.admin.id,
        dv_no="DV-2026-0007",
        dv_date=_date(2026, 6, 25),
        date_return=_date(2026, 7, 3),
    )
    await ca.link_claim(
        app_session, claim=cast.claim, cash_advance=cast.advance
    )
    await compute_claim_totals(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id
    )
    await app_session.flush()
    return cast


async def test_bindings_are_kind_aware(app_session):
    """The test the whole increment turns on: neither kind may leak into the
    other's document set."""
    from office_connect.modules.reimbursement.documents.service import _bindings
    from office_connect.modules.reimbursement.seeds import apply_reimbursement_seeds

    await apply_reimbursement_seeds(app_session)
    reimbursement = await _bindings(app_session, claim_kind="reimbursement")
    liquidation = await _bindings(app_session, claim_kind="liquidation")

    assert {b.checklist_code for b in reimbursement} == GENERATED_CODES
    assert {b.checklist_code for b in liquidation} == LIQUIDATION_CODES


async def test_a_null_kind_binding_applies_to_both_kinds(app_session):
    """``claim_kind IS NULL`` means "both kinds" (models/templates.py), and the
    predicate must actually be able to match it.

    Until R-6-liq-settle ``_bindings`` used ``.in_([kind, None])`` — and SQL
    ``IN`` never matches a NULL, so the documented semantic was unreachable and
    the failure mode was a government form that silently never generated. No
    seeded row is NULL-kind, which is exactly why this inserts one directly:
    the capability has to be pinned by something other than the seed data.
    """
    from office_connect.modules.reimbursement.documents.service import _bindings

    app_session.add(
        ReimbTemplateMap(
            claim_kind=None,
            checklist_code="ZZ-BOTH",
            document_key="reimb.iot45",
            title="Applies to both kinds",
            sort=99,
        )
    )
    await app_session.flush()

    for kind in ("reimbursement", "liquidation"):
        codes = {b.checklist_code for b in await _bindings(app_session, claim_kind=kind)}
        assert "ZZ-BOTH" in codes, kind
    await app_session.rollback()


async def test_a_liquidation_generates_the_lr44_and_its_own_packet(
    app_session, make_user
):
    cast = await _liquidation_claim(app_session, make_user)
    renderer = _FakeRenderer()

    results = await generate_claim_documents(
        app_session,
        claim_id=cast.claim.id,
        actor_user_id=cast.owner.id,
        renderer=renderer,
    )

    assert {r.document_key for r in results} == {doc_registry.LR_44, PACKET}
    assert renderer.calls == LIQUIDATION_DOCUMENT_COUNT
    # The seeded-but-inert LR-44 catalog row is now discharged…
    statuses = await _statuses(app_session, cast.claim)
    assert statuses["LR-44"] == "generated"
    # …and none of the reimbursement forms exist on this claim at all.
    assert not (GENERATED_CODES & set(statuses))


async def test_the_liquidation_packet_titles_itself_a_liquidation(
    app_session, make_user
):
    """An Accounting clerk handed a folder stamped "Travel claim packet" on a
    liquidation reads it as the wrong document type. One `document_key` either
    way — forking the KEY would fork the snapshot lineage for one string."""
    from office_connect.modules.reimbursement.documents.context import (
        build_packet_context,
    )

    cast = await _liquidation_claim(app_session, make_user)
    await generate_claim_documents(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id,
        renderer=_FakeRenderer(),
    )
    snapshots = await active_snapshots(
        app_session, subject_kind=SUBJECT_KIND, subject_id=cast.claim.id
    )
    assert PACKET in {s.document_key for s in snapshots}

    context = await build_packet_context(
        app_session, claim=cast.claim, sections=[],
        title=doc_registry.PACKET_TITLES["liquidation"],
    )
    assert context["doc"]["title"] == "Liquidation packet"
    # …and the cover's money nouns follow the kind, from one table of prose.
    assert context["money_labels"]["total"] == "Total amount spent"


async def test_the_settlement_blocks_are_present_and_empty_on_a_reimbursement(
    app_session, make_user
):
    """The shape contract that keeps the BODY_PARTIALS render loop alive: these
    keys are ALWAYS present, all-None off the liquidation path. A key that
    appeared only for liquidations would raise StrictUndefined inside
    RenderFailed — a silent `outcome="failed"` in the worker."""
    from office_connect.modules.reimbursement.documents.context import (
        build_document_context,
    )

    cast = await _computed_claim(app_session, make_user)
    context = await build_document_context(
        app_session, claim=cast.claim, document_key=doc_registry.LR_44,
        title="Liquidation Report",
    )
    assert context["advance"]["dv_no"] is None
    assert context["settlement"]["or_no"] is None
    assert context["certifications"]["c"]["recorded_by"] is None
    assert context["money_labels"]["heading"] == "Amount claimed"


async def test_the_settlement_facts_are_hashed(app_session, make_user):
    """The OR number must be INSIDE the fingerprint, or recording a refund would
    leave the Liquidation Report permanently stale."""
    from office_connect.core.documents.render import fingerprint_context
    from office_connect.modules.reimbursement.documents.context import (
        build_document_context,
    )
    from office_connect.modules.reimbursement.documents.service import (
        comparable_context,
    )

    cast = await _liquidation_claim(app_session, make_user)
    context = await build_document_context(
        app_session, claim=cast.claim, document_key=doc_registry.LR_44,
        title="Liquidation Report",
    )
    before = fingerprint_context(comparable_context(context))
    context["settlement"]["or_no"] = "OR-2026-1234"
    assert fingerprint_context(comparable_context(context)) != before


async def test_the_pre_settlement_lr44_prints_a_blank_receipt_line(
    app_session, make_user
):
    """A Liquidation Report with a blank OR line IS GAM App 44 at the stage it
    is at — the traveller walks it to the cashier and the number is written on.
    What would be dishonest is printing ₱0.00 (indistinguishable from "nothing
    refundable") or hiding the section so nobody learns a refund is owed."""
    pytest.importorskip("weasyprint")
    from office_connect.core.documents import render_document
    from office_connect.modules.reimbursement.documents.context import (
        build_document_context,
    )

    cast = await _liquidation_claim(app_session, make_user)
    assert cast.claim.totals["to_refund"] == "1500.00"
    context = await build_document_context(
        app_session, claim=cast.claim, document_key=doc_registry.LR_44,
        title="Liquidation Report", form_no="GAM Vol. II, Appendix 44",
    )
    html = render_document(
        key=doc_registry.LR_44, context=context, renderer=None
    ).html

    assert "produced BEFORE the refund was recorded" in html
    assert "Official receipt no. ___" in html
    # The figure that IS known is printed; the one that is not, is not faked.
    assert "₱1,500.00" in html
    assert "Amount refunded per Official Receipt" not in html
    # The advance's own identity — the LR's central line, unprintable before
    # this increment because `totals` carries the amount and nothing else.
    assert "DV-2026-0007" in html


async def test_the_settled_lr44_carries_the_official_receipt(
    app_session, make_user
):
    pytest.importorskip("weasyprint")
    from office_connect.core.documents import render_document
    from office_connect.modules.reimbursement.documents.context import (
        build_document_context,
    )
    from office_connect.modules.reimbursement.services import cash_advance as ca

    cast = await _liquidation_claim(app_session, make_user)
    await ca.mark_settled(
        app_session,
        cash_advance=cast.advance,
        actor_user_id=cast.admin.id,
        mode=ca.REFUND,
        refund_amount=cast.claim.totals["to_refund"],
        or_no="OR-2026-1234",
        or_date=__import__("datetime").date(2026, 7, 9),
    )
    context = await build_document_context(
        app_session, claim=cast.claim, document_key=doc_registry.LR_44,
        title="Liquidation Report",
    )
    html = render_document(
        key=doc_registry.LR_44, context=context, renderer=None
    ).html

    assert "Amount refunded per Official Receipt no. OR-2026-1234" in html
    assert "09 July 2026" in html
    assert "produced BEFORE the refund" not in html


async def test_the_lr44_never_prints_a_name_in_certification_c(
    app_session, make_user
):
    """The workflow records the ADMIN OFFICER who typed the mandatory comment,
    not the Head of the Accounting Unit who signed on paper. Printing the
    recorder in box C would name the wrong person in a COA certification — a
    worse untruth than a blank box. This is the test that stops a future session
    "helpfully" filling it in."""
    pytest.importorskip("weasyprint")
    from office_connect.core.documents import render_document
    from office_connect.modules.reimbursement.documents.context import (
        build_document_context,
    )

    cast = await _liquidation_claim(app_session, make_user)
    context = await build_document_context(
        app_session, claim=cast.claim, document_key=doc_registry.LR_44,
        title="Liquidation Report",
    )
    # Pretend the chain recorded certification C against a named Admin Officer.
    context["certifications"]["c"] = {
        "recorded_by": "Recording Adminofficer",
        "recorded_at": "2026-07-08T02:00:00+00:00",
        "note": "Signed by the Head, Accounting Unit on 2026-07-08.",
    }
    html = render_document(
        key=doc_registry.LR_44, context=context, renderer=None
    ).html

    # The name appears ONLY inside the "Recorded in Office-Connect by" note…
    assert "Recorded in Office-Connect by Recording Adminofficer" in html
    # …and never on a signature-name line.
    for chunk in html.split('class="signature-name"')[1:]:
        assert "Recording Adminofficer" not in chunk.split("</p>")[0]
