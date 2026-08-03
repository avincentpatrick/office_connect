"""R-3 — the checklist service against the shipped catalog and real tables.

What this pins, over and above the pure-core tests:

- the seeded COA 2023-004 catalog materializes into the set the rules imply;
- re-materializing an unchanged claim writes NOTHING (the idempotency contract);
- a rule that stops applying puts an EMPTY item away and RESTORES it by id, but
  never touches one holding the claimant's evidence;
- uploads ride core attachments (Rule 10) and land on the join table, with the
  JSONB list as a mirror;
- the ``(claim_id, catalog_id)`` unique index is real.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from office_connect.core.models import Attachment
from office_connect.modules.reimbursement.models import (
    ReimbAttachment,
    ReimbChecklistCatalog,
    ReimbChecklistItem,
)
from office_connect.modules.reimbursement.services import checklist
from office_connect.modules.reimbursement.services.attachments import (
    HOLDER_KIND,
    RETENTION_CLASS,
)
from tests.reimb_checklist_helpers import blocking_codes, satisfy_packet, tiny_jpeg
from tests.reimb_lifecycle_helpers import standard_cast


async def _codes(session, claim):
    view = await checklist.checklist_view(session, claim=claim)
    return {row.plan.catalog.code: row for row in view.rows}


async def _catalog_id(session, code):
    return (
        await session.execute(
            select(ReimbChecklistCatalog.id).where(ReimbChecklistCatalog.code == code)
        )
    ).scalar_one()


# --- materialization --------------------------------------------------------


async def test_the_seeded_catalog_materializes_the_rules_it_implies(
    make_user, seed_rbac, app_session
):
    cast = await standard_cast(app_session, make_user, packet=False)
    rows = await _codes(app_session, cast.claim)

    # Unconditional items apply; JO-01 does not (permanent staff); RER-46 does
    # not (bus legs only); LOD-01 does not (other_total is 0).
    assert {"TO-01", "IOT-45", "CTC-47", "AR-01", "DV-32"} <= set(rows)
    assert "JO-01" not in rows
    assert "RER-46" not in rows
    assert "LOD-01" not in rows


async def test_only_human_evidence_blocks_submit(make_user, seed_rbac, app_session):
    """The three always-on ``generated_doc`` rows are applicable but never
    blocking — a system-produced artifact cannot gate entry to the workflow
    that produces it."""
    cast = await standard_cast(app_session, make_user, packet=False)
    assert await blocking_codes(app_session, claim=cast.claim) == ["CTC-47", "TO-01"]


async def test_a_taxi_leg_spawns_the_conditional_receipt_item(
    make_user, seed_rbac, app_session
):
    from tests.reimbursement_helpers import make_leg

    cast = await standard_cast(app_session, make_user, packet=False)
    await make_leg(
        app_session,
        claim_id=cast.claim.id,
        seq=3,
        leg_date=cast.claim.date_depart,
        transport_mode="taxi",
        fare="120.00",
    )
    assert "RER-46" in await _codes(app_session, cast.claim)


async def test_other_expenses_spawn_the_lodging_item(
    make_user, seed_rbac, app_session
):
    """Spec §9.3 step 3 — "each spawns its conditional checklist items"."""
    from decimal import Decimal

    cast = await standard_cast(app_session, make_user, packet=False)
    cast.claim.other_total = Decimal("250.00")
    await app_session.flush()
    assert "LOD-01" in await _codes(app_session, cast.claim)


async def test_jo_cos_claimants_get_the_head_of_office_certification(
    make_user, seed_rbac, app_session
):
    cast = await standard_cast(app_session, make_user, packet=False)
    cast.claim.is_jo_cos = True
    await app_session.flush()
    assert "JO-01" in await _codes(app_session, cast.claim)


async def test_reading_the_checklist_writes_nothing(make_user, seed_rbac, app_session):
    """The Documents screen is a pure GET: rows are created when they must hold
    something, not when someone looks at them."""
    cast = await standard_cast(app_session, make_user, packet=False)
    before = (
        await app_session.execute(
            select(func.count()).select_from(ReimbChecklistItem)
        )
    ).scalar_one()
    view = await checklist.checklist_view(app_session, claim=cast.claim)
    after = (
        await app_session.execute(
            select(func.count()).select_from(ReimbChecklistItem)
        )
    ).scalar_one()
    assert before == after
    assert all(row.item_id is None for row in view.rows)


async def test_re_materializing_an_unchanged_claim_is_a_no_op(
    make_user, seed_rbac, app_session
):
    """The idempotency contract: no inserts, no updates, no audit rows."""
    from office_connect.core.models import AuditLog

    cast = await standard_cast(app_session, make_user, packet=False)
    await checklist.refresh_checklist(
        app_session, claim=cast.claim, actor_user_id=cast.owner.id
    )
    await app_session.commit()

    def counts():
        return app_session.execute(
            select(
                select(func.count())
                .select_from(ReimbChecklistItem)
                .scalar_subquery(),
                select(func.count()).select_from(AuditLog).scalar_subquery(),
            )
        )

    before = (await counts()).one()
    await checklist.refresh_checklist(
        app_session, claim=cast.claim, actor_user_id=cast.owner.id
    )
    await app_session.commit()
    assert (await counts()).one() == before


# --- the lifecycle of an item that stops applying ---------------------------


async def test_an_empty_item_goes_dormant_and_is_restored_by_id(
    make_user, seed_rbac, app_session
):
    cast = await standard_cast(app_session, make_user, packet=False)
    cast.claim.is_jo_cos = True
    await app_session.flush()
    await checklist.refresh_checklist(
        app_session, claim=cast.claim, actor_user_id=cast.owner.id
    )
    catalog_id = await _catalog_id(app_session, "JO-01")
    original = (
        await app_session.execute(
            select(ReimbChecklistItem).where(
                ReimbChecklistItem.claim_id == cast.claim.id,
                ReimbChecklistItem.catalog_id == catalog_id,
            )
        )
    ).scalar_one()

    cast.claim.is_jo_cos = False
    await app_session.flush()
    await checklist.refresh_checklist(
        app_session, claim=cast.claim, actor_user_id=cast.owner.id
    )
    await app_session.refresh(original)
    assert original.deleted_at is not None  # soft, never hard (standing rule 6)
    assert "JO-01" not in await _codes(app_session, cast.claim)

    cast.claim.is_jo_cos = True
    await app_session.flush()
    await checklist.refresh_checklist(
        app_session, claim=cast.claim, actor_user_id=cast.owner.id
    )
    await app_session.refresh(original)
    assert original.deleted_at is None  # same row, same id, same history


async def test_an_item_holding_evidence_survives_becoming_inapplicable(
    make_user, seed_rbac, app_session
):
    """Severing a claim-to-document link is a records-management act, not a
    projection refresh."""
    cast = await standard_cast(app_session, make_user, packet=False)
    cast.claim.is_jo_cos = True
    await app_session.flush()
    catalog_id = await _catalog_id(app_session, "JO-01")
    await checklist.attach_evidence(
        app_session,
        claim=cast.claim,
        catalog_id=catalog_id,
        data=tiny_jpeg(),
        filename="cert.jpg",
        declared_mime="image/jpeg",
        actor_user_id=cast.owner.id,
    )

    cast.claim.is_jo_cos = False
    await app_session.flush()
    await checklist.refresh_checklist(
        app_session, claim=cast.claim, actor_user_id=cast.owner.id
    )

    row = (await _codes(app_session, cast.claim))["JO-01"]
    assert row.plan.required is False  # no longer required…
    assert row.plan.evidence_state == "attached"  # …but the file is still there
    assert len(row.files) == 1


# --- uploads ----------------------------------------------------------------


async def test_an_upload_rides_core_attachments_and_lands_on_the_join_table(
    make_user, seed_rbac, app_session
):
    cast = await standard_cast(app_session, make_user, packet=False)
    catalog_id = await _catalog_id(app_session, "TO-01")
    view, attachment_id = await checklist.attach_evidence(
        app_session,
        claim=cast.claim,
        catalog_id=catalog_id,
        data=tiny_jpeg(),
        filename="travel-order.jpg",
        declared_mime="image/jpeg",
        actor_user_id=cast.owner.id,
    )

    core_row = (
        await app_session.execute(
            select(Attachment).where(Attachment.id == attachment_id)
        )
    ).scalar_one()
    assert core_row.holder_kind == HOLDER_KIND
    assert core_row.holder_id == cast.claim.id
    assert core_row.retention_class == RETENTION_CLASS
    assert core_row.sniffed_mime == "image/jpeg"  # magic bytes, not the header
    assert core_row.scan_status == "pending"

    join = (
        await app_session.execute(
            select(ReimbAttachment).where(
                ReimbAttachment.attachment_id == attachment_id
            )
        )
    ).scalar_one()
    assert join.claim_id == cast.claim.id
    assert join.retention_class == RETENTION_CLASS

    item = (await _codes(app_session, cast.claim))["TO-01"]
    assert item.plan.derived_status == "attached"
    # The JSONB list mirrors the join table (and was REASSIGNED, so it stuck).
    stored = (
        await app_session.execute(
            select(ReimbChecklistItem).where(ReimbChecklistItem.id == item.item_id)
        )
    ).scalar_one()
    assert stored.attachment_ids == [attachment_id]
    assert "TO-01" not in [b.code for b in view.status.blocking]


async def test_a_fake_image_is_rejected_by_the_core_allowlist(
    make_user, seed_rbac, app_session
):
    from office_connect.core.attachments.errors import RejectedUpload

    cast = await standard_cast(app_session, make_user, packet=False)
    catalog_id = await _catalog_id(app_session, "TO-01")
    with pytest.raises(RejectedUpload):
        await checklist.attach_evidence(
            app_session,
            claim=cast.claim,
            catalog_id=catalog_id,
            data=b"<svg>nope</svg>",
            filename="evil.svg",
            declared_mime="image/svg+xml",
            actor_user_id=cast.owner.id,
        )


async def test_detaching_soft_deletes_both_rows_and_reopens_the_item(
    make_user, seed_rbac, app_session
):
    cast = await standard_cast(app_session, make_user, packet=False)
    catalog_id = await _catalog_id(app_session, "TO-01")
    _, attachment_id = await checklist.attach_evidence(
        app_session,
        claim=cast.claim,
        catalog_id=catalog_id,
        data=tiny_jpeg(),
        filename="to.jpg",
        declared_mime="image/jpeg",
        actor_user_id=cast.owner.id,
    )
    join_id = (
        await app_session.execute(
            select(ReimbAttachment.id).where(
                ReimbAttachment.attachment_id == attachment_id
            )
        )
    ).scalar_one()

    view = await checklist.detach_evidence(
        app_session,
        claim=cast.claim,
        catalog_id=catalog_id,
        reimb_attachment_id=join_id,
        actor_user_id=cast.owner.id,
    )
    assert "TO-01" in [b.code for b in view.status.blocking]

    for model, pk in ((ReimbAttachment, join_id), (Attachment, attachment_id)):
        row = (
            await app_session.execute(
                select(model)
                .where(model.id == pk)
                .execution_options(include_deleted=True)
            )
        ).scalar_one()
        assert row.deleted_at is not None  # soft, both sides


async def test_uploading_to_a_generated_document_is_refused(
    make_user, seed_rbac, app_session
):
    from office_connect.core.api.errors import APIError

    cast = await standard_cast(app_session, make_user, packet=False)
    catalog_id = await _catalog_id(app_session, "IOT-45")  # generated_doc
    with pytest.raises(APIError) as exc:
        await checklist.attach_evidence(
            app_session,
            claim=cast.claim,
            catalog_id=catalog_id,
            data=tiny_jpeg(),
            filename="x.jpg",
            declared_mime="image/jpeg",
            actor_user_id=cast.owner.id,
        )
    assert exc.value.code == "reimb_evidence_not_uploadable"


async def test_an_unknown_catalog_id_is_refused(make_user, seed_rbac, app_session):
    from office_connect.core.api.errors import APIError

    cast = await standard_cast(app_session, make_user, packet=False)
    with pytest.raises(APIError) as exc:
        await checklist.attach_evidence(
            app_session,
            claim=cast.claim,
            catalog_id=10**9,
            data=tiny_jpeg(),
            filename="x.jpg",
            declared_mime="image/jpeg",
            actor_user_id=cast.owner.id,
        )
    assert exc.value.code == "reimb_unknown_catalog_item"


# --- the DB belt ------------------------------------------------------------


async def test_one_live_item_per_claim_and_catalog_row(
    make_user, seed_rbac, app_session
):
    """The unique index from 0017 — the belt behind the claim's FOR UPDATE lock."""
    from sqlalchemy.exc import IntegrityError

    cast = await standard_cast(app_session, make_user, packet=False)
    await satisfy_packet(app_session, claim=cast.claim, actor_user_id=cast.owner.id)
    catalog_id = await _catalog_id(app_session, "TO-01")

    app_session.add(
        ReimbChecklistItem(claim_id=cast.claim.id, catalog_id=catalog_id)
    )
    with pytest.raises(IntegrityError):
        await app_session.flush()
    await app_session.rollback()


# --- the seam contract ------------------------------------------------------


def test_the_module_status_enum_matches_the_core_vocabulary():
    """If either side grows a value the other does not know, the engine's
    derivation and the DB enum silently disagree — catch it here."""
    from office_connect.core.checklist import validate_status_vocabulary
    from office_connect.modules.reimbursement.models.enums import ChecklistItemStatus

    validate_status_vocabulary(ChecklistItemStatus.enums)


def test_every_seeded_catalog_rule_is_well_formed():
    """The seeds are the only writer of the catalog until the R-9 admin editor,
    so validating them here is what makes the evaluator's fail-open direction
    safe: an unparseable rule cannot reach data."""
    from office_connect.core.checklist import (
        validate_auto_checks,
        validate_required_rule,
    )
    from office_connect.modules.reimbursement.seeds import REIMB_CHECKLIST

    for row in REIMB_CHECKLIST.rows:
        validate_required_rule(row["required_rule"])
        validate_auto_checks(row["auto_checks"])
