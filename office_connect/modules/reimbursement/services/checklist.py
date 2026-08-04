"""The claim's documentary packet — persistence around the core checklist engine.

Division of labour (Rule 10): ``core.checklist`` owns the grammar, the check
semantics, the reconciliation algorithm and the blocking rule — all pure. This
module owns the tables: it loads the catalog and the claim's items, hands them to
the engine as dataclasses, and applies the plan the engine returns.

**Reads do not write.** ``checklist_view`` computes the plan and merges persisted
rows with not-yet-persisted planned ones (``item_id: None``); a row is created
exactly when it needs to hold something. Every write endpoint is keyed on
``catalog_id``, so the client never needs a materialized row to act — which is
what lets the Documents screen be a pure GET rather than a GET that commits.

**The gate.** ``assert_packet_complete`` materializes first, then refuses: it is
the one place spec §2's *"a claim physically cannot be submitted with a missing
required item"* is enforced.  ``assert_persisted_packet_complete`` is the approve
side and deliberately does NOT re-materialize — see its docstring.

Everything flushes and never commits (the module-wide contract shared with
``lifecycle`` / ``drafts`` / ``compute``); the router owns the transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core import checklist as engine
from office_connect.core.documents import void_snapshots
from office_connect.core.session import set_audit_context
from office_connect.core.soft_delete import soft_delete
from office_connect.core.time import utc_now
from office_connect.modules.reimbursement.models import (
    ReimbAttachment,
    ReimbChecklistCatalog,
    ReimbChecklistItem,
    ReimbClaim,
)
from office_connect.modules.reimbursement.services import attachments as evidence
from office_connect.modules.reimbursement.services import errors
from office_connect.modules.reimbursement.services.checklist_facts import (
    build_claim_facts,
)


@dataclass(frozen=True)
class ChecklistRow:
    """One packet row, ready for the wire: the plan plus its stored evidence."""

    plan: engine.ItemPlan
    item_id: int | None
    files: tuple[dict[str, Any], ...] = ()
    waiver_reason: str | None = None


@dataclass(frozen=True)
class ChecklistView:
    """A claim's whole packet — the rows plus the gate's answer over them."""

    rows: tuple[ChecklistRow, ...]
    status: engine.PacketStatus


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


async def _catalog(
    session: AsyncSession, *, claim_kind: str
) -> tuple[list[engine.CatalogSpec], dict[int, ReimbChecklistCatalog]]:
    """The active catalog rows that apply to this claim kind (NULL = both)."""
    rows = (
        (
            await session.execute(
                select(ReimbChecklistCatalog).where(
                    ReimbChecklistCatalog.is_active.is_(True),
                    (ReimbChecklistCatalog.claim_kind.is_(None))
                    | (ReimbChecklistCatalog.claim_kind == claim_kind),
                )
            )
        )
        .scalars()
        .all()
    )
    specs = [
        engine.CatalogSpec(
            catalog_id=row.id,
            code=row.code,
            label=row.label,
            group=row.group,
            evidence=row.evidence,
            required_rule=row.required_rule,
            auto_checks=row.auto_checks,
            sort=row.sort or 0,
            circular_version=row.circular_version,
        )
        for row in rows
    ]
    return specs, {row.id: row for row in rows}


async def _items(
    session: AsyncSession, *, claim_id: int
) -> dict[int, ReimbChecklistItem]:
    """Every item for the claim INCLUDING dormant ones — restore needs them."""
    rows = (
        (
            await session.execute(
                select(ReimbChecklistItem)
                .where(ReimbChecklistItem.claim_id == claim_id)
                .execution_options(include_deleted=True)
            )
        )
        .scalars()
        .all()
    )
    return {row.catalog_id: row for row in rows}


async def _states(
    session: AsyncSession, *, claim_id: int, items: dict[int, ReimbChecklistItem]
) -> list[engine.ItemState]:
    counts = await evidence.evidence_counts(session, claim_id=claim_id)
    states = []
    for catalog_id, row in items.items():
        usable, pending, infected = counts.get(row.id, (0, 0, 0))
        states.append(
            engine.ItemState(
                item_id=row.id,
                catalog_id=catalog_id,
                status=row.status,
                evidence_count=usable,
                evidence_pending=pending,
                evidence_infected=infected,
                generated=row.status == "generated",
                waived=row.waiver_reason is not None,
                dormant=row.deleted_at is not None,
            )
        )
    return states


async def _build(
    session: AsyncSession, *, claim: ReimbClaim, now: datetime | None = None
) -> tuple[tuple[engine.ItemPlan, ...], dict[int, ReimbChecklistItem]]:
    specs, _ = await _catalog(session, claim_kind=claim.kind)
    items = await _items(session, claim_id=claim.id)
    facts = await build_claim_facts(session, claim=claim, now=now)
    states = await _states(session, claim_id=claim.id, items=items)
    return (
        engine.plan_checklist(catalog=specs, existing=states, facts=facts),
        items,
    )


def _rows(
    plan: Sequence[engine.ItemPlan],
    items: dict[int, ReimbChecklistItem],
    files: dict[int, list[dict[str, Any]]],
) -> tuple[ChecklistRow, ...]:
    out = []
    for item_plan in plan:
        row = items.get(item_plan.catalog.catalog_id)
        out.append(
            ChecklistRow(
                plan=item_plan,
                item_id=row.id if row is not None else None,
                files=tuple(files.get(row.id, ())) if row is not None else (),
                waiver_reason=row.waiver_reason if row is not None else None,
            )
        )
    return tuple(out)


# --------------------------------------------------------------------------
# Read
# --------------------------------------------------------------------------


async def checklist_view(
    session: AsyncSession, *, claim: ReimbClaim, now: datetime | None = None
) -> ChecklistView:
    """The claim's packet as it stands. Writes nothing."""
    plan, items = await _build(session, claim=claim, now=now)
    files = await evidence.claim_evidence(session, claim_id=claim.id)
    return ChecklistView(rows=_rows(plan, items, files), status=engine.packet_status(plan))


async def checklist_summary(
    session: AsyncSession, *, claim: ReimbClaim, now: datetime | None = None
) -> engine.PacketStatus:
    """Just the gate's answer — what ``ClaimDetail`` embeds. Writes nothing."""
    plan, _ = await _build(session, claim=claim, now=now)
    return engine.packet_status(plan)


# --------------------------------------------------------------------------
# Write
# --------------------------------------------------------------------------


async def refresh_checklist(
    session: AsyncSession,
    *,
    claim: ReimbClaim,
    actor_user_id: int,
    now: datetime | None = None,
) -> ChecklistView:
    """Materialize the plan onto ``reimb_checklist_items``. Flushes, never commits.

    Idempotent: an unchanged claim produces zero INSERTs, zero UPDATEs and
    therefore zero audit rows, because every write below is guarded by a
    compare-then-set.
    """
    set_audit_context(session, actor_id=actor_user_id)
    plan, items = await _build(session, claim=claim, now=now)

    for item_plan in plan:
        catalog_id = item_plan.catalog.catalog_id
        row = items.get(catalog_id)

        if item_plan.action == engine.CREATE:
            row = ReimbChecklistItem(
                claim_id=claim.id,
                catalog_id=catalog_id,
                status=item_plan.derived_status,
                # Pin what the requirement MEANT when this claim was checked:
                # `apply_dataset` upserts catalog rows in place, so without this
                # a later circular revision would retroactively rewrite history
                # (master-plan §1.1 #7 — "catalog versions pinned to the issuing
                # circular revision").
                circular_version=item_plan.catalog.circular_version,
            )
            session.add(row)
            items[catalog_id] = row
            continue

        if row is None:  # unparseable-rule plan with no row behind it
            continue

        if item_plan.action == engine.RESTORE:
            row.deleted_at = None
            row.deleted_by = None
        elif item_plan.action == engine.MAKE_DORMANT:
            soft_delete(row, actor_id=actor_user_id)
            continue

        if row.status != item_plan.derived_status:
            row.status = item_plan.derived_status

    await session.flush()
    return await checklist_view(session, claim=claim, now=now)


async def _item_for_catalog(
    session: AsyncSession,
    *,
    claim: ReimbClaim,
    catalog_id: int,
    actor_user_id: int,
) -> ReimbChecklistItem:
    """The live item row for ``catalog_id``, created on demand.

    Materialize-on-write is what lets the Documents GET stay read-only: the
    claimant addresses a catalog row, and the item springs into existence the
    moment it must hold something.
    """
    specs, catalog_rows = await _catalog(session, claim_kind=claim.kind)
    catalog_row = catalog_rows.get(catalog_id)
    if catalog_row is None:
        raise errors.unknown_catalog_item(catalog_id)
    if catalog_row.evidence not in ("upload", "external_wet_sign"):
        raise errors.evidence_not_uploadable(catalog_row.code, catalog_row.evidence)

    existing = (
        await session.execute(
            select(ReimbChecklistItem)
            .where(
                ReimbChecklistItem.claim_id == claim.id,
                ReimbChecklistItem.catalog_id == catalog_id,
            )
            .execution_options(include_deleted=True)
        )
    ).scalar_one_or_none()

    if existing is not None:
        # A dormant row means the rule stopped applying; attaching to it revives
        # it rather than creating a second row (the unique index forbids that,
        # and the history belongs to the original).
        existing.deleted_at = None
        existing.deleted_by = None
        return existing

    row = ReimbChecklistItem(
        claim_id=claim.id,
        catalog_id=catalog_id,
        status="missing",
        circular_version=catalog_row.circular_version,
    )
    session.add(row)
    await session.flush()
    return row


async def materialize_generated_item(
    session: AsyncSession,
    *,
    claim: ReimbClaim,
    code: str,
    actor_user_id: int | None,
) -> ReimbChecklistItem:
    """The ``generated_doc`` sibling of ``_item_for_catalog``.

    A separate entry point rather than a widened guard, because the two paths
    must stay asymmetric: a claimant may never upload against ``IOT-45`` (that
    is what ``reimb_evidence_not_uploadable`` protects), and the generator may
    never produce a ``TO-01``. Sharing one permissive materializer would erase
    both rules at once.

    Addressed by **code**, not catalog id: the caller is a template binding, and
    ``reimb_template_maps`` deliberately stores the stable code rather than a
    surrogate id a re-seed could change.
    """
    catalog_row = (
        await session.execute(
            select(ReimbChecklistCatalog).where(
                ReimbChecklistCatalog.is_active.is_(True),
                ReimbChecklistCatalog.code == code,
                (ReimbChecklistCatalog.claim_kind.is_(None))
                | (ReimbChecklistCatalog.claim_kind == claim.kind),
            )
        )
    ).scalar_one_or_none()
    if catalog_row is None:
        raise errors.unknown_catalog_code(code)
    if catalog_row.evidence != "generated_doc":
        raise errors.document_not_generatable(code, catalog_row.evidence)

    existing = (
        await session.execute(
            select(ReimbChecklistItem)
            .where(
                ReimbChecklistItem.claim_id == claim.id,
                ReimbChecklistItem.catalog_id == catalog_row.id,
            )
            .execution_options(include_deleted=True)
        )
    ).scalar_one_or_none()

    if existing is not None:
        # A dormant row is revived rather than duplicated — the partial unique
        # index forbids a second live row and the history belongs to the first.
        existing.deleted_at = None
        existing.deleted_by = None
        return existing

    row = ReimbChecklistItem(
        claim_id=claim.id,
        catalog_id=catalog_row.id,
        status="missing",
        circular_version=catalog_row.circular_version,
    )
    session.add(row)
    await session.flush()
    return row


async def mark_generated(
    session: AsyncSession,
    *,
    claim: ReimbClaim,
    item: ReimbChecklistItem,
    attachment_id: int,
    actor_user_id: int | None,
) -> ChecklistView:
    """Flip an item to ``generated`` and mirror the PDF onto it.

    **This is the only bootstrap of the ``generated`` status.** Everywhere else
    the value is read back off the column it was written to: ``_states`` derives
    ``ItemState.generated`` from ``row.status == "generated"``, and
    ``refresh_checklist`` writes back the ``derived_status`` the engine computed
    from that flag. Without an explicit first write the loop is closed and the
    three ``generated_doc`` items could never leave ``missing`` — which is
    exactly the state R-3 shipped and R-5 exists to end.

    Once written the value is self-sustaining: ``generated`` outranks every
    evidence-derived status in ``engine._derive``, and ``holds_something`` keeps
    the row alive even if its rule later stops applying.

    The mirror is REASSIGNED, never appended to — the column has no
    ``MutableList``, so an in-place mutation would leave the row un-dirty.
    """
    set_audit_context(session, actor_id=actor_user_id)

    if item.status != "generated":
        item.status = "generated"
    evidence.mirror_attachment_ids(item, [attachment_id])
    await session.flush()

    return await refresh_checklist(
        session, claim=claim, actor_user_id=actor_user_id
    )


async def _invalidate_packet(
    session: AsyncSession, *, claim: ReimbClaim, reason: str, actor_user_id: int
) -> None:
    """Void the claim's live snapshots because its EVIDENCE changed (R-5-packet).

    R-5-gen voided on any change to a printed *field* (``drafts.py``). That was
    complete while the generated documents only printed claim data. The combined
    packet also prints a manifest of the claimant's uploads — filename, size,
    SHA-256, scan state — so attaching or detaching a file makes the frozen
    packet describe a set of documents the claim no longer has. Exactly the same
    argument that made ``purpose`` a void trigger at R-5-gen, one level out.

    Calls ``void_snapshots`` directly rather than reusing
    ``drafts.invalidate_packet``: ``drafts`` imports ``lifecycle`` which imports
    this module, so importing ``drafts`` here would close the cycle. Core is
    always safe to import.

    Voids only; does **not** enqueue a regeneration. A render per upload would
    mean rendering the whole packet four or five times while a claimant works
    through the Documents step. Submit regenerates authoritatively, and the
    wizard already offers "Prepare my documents" for a claimant who wants the
    draft refreshed sooner.

    The generator's own writes are untouched: it stores through
    ``store_generated_document`` / ``mark_generated``, never through the two
    functions below, so a generation pass cannot void the snapshot it just
    froze.
    """
    await void_snapshots(
        session,
        subject_kind=evidence.HOLDER_KIND,
        subject_id=claim.id,
        reason=reason,
        actor_id=actor_user_id,
    )


async def attach_evidence(
    session: AsyncSession,
    *,
    claim: ReimbClaim,
    catalog_id: int,
    data: bytes,
    filename: str,
    declared_mime: str | None,
    actor_user_id: int,
) -> tuple[ChecklistView, int]:
    """Upload a file onto a checklist item. Returns ``(view, core_attachment_id)``.

    The caller enqueues the scan after commit and owns the transaction.
    """
    set_audit_context(session, actor_id=actor_user_id)
    item = await _item_for_catalog(
        session, claim=claim, catalog_id=catalog_id, actor_user_id=actor_user_id
    )
    join, attachment_id = await evidence.upload_claim_evidence(
        session,
        claim_id=claim.id,
        checklist_item_id=item.id,
        data=data,
        filename=filename,
        declared_mime=declared_mime,
        actor_user_id=actor_user_id,
    )
    evidence.mirror_attachment_ids(
        item, [*(item.attachment_ids or []), attachment_id]
    )
    await _invalidate_packet(
        session,
        claim=claim,
        reason="evidence attached",
        actor_user_id=actor_user_id,
    )
    await session.flush()
    return (
        await refresh_checklist(session, claim=claim, actor_user_id=actor_user_id),
        attachment_id,
    )


async def detach_evidence(
    session: AsyncSession,
    *,
    claim: ReimbClaim,
    catalog_id: int,
    reimb_attachment_id: int,
    actor_user_id: int,
) -> ChecklistView:
    """Remove a file from a checklist item (soft, both rows)."""
    set_audit_context(session, actor_id=actor_user_id)
    item = (
        await session.execute(
            select(ReimbChecklistItem).where(
                ReimbChecklistItem.claim_id == claim.id,
                ReimbChecklistItem.catalog_id == catalog_id,
            )
        )
    ).scalar_one_or_none()
    if item is None:
        raise errors.unknown_catalog_item(catalog_id)

    join = (
        await session.execute(
            select(ReimbAttachment).where(
                ReimbAttachment.id == reimb_attachment_id,
                ReimbAttachment.claim_id == claim.id,
                ReimbAttachment.checklist_item_id == item.id,
            )
        )
    ).scalar_one_or_none()
    if join is None:
        raise errors.evidence_not_on_item(reimb_attachment_id)

    attachment_id = join.attachment_id
    await evidence.remove_claim_evidence(
        session, join=join, actor_user_id=actor_user_id
    )
    evidence.mirror_attachment_ids(
        item, [i for i in (item.attachment_ids or []) if i != attachment_id]
    )
    await _invalidate_packet(
        session,
        claim=claim,
        reason="evidence detached",
        actor_user_id=actor_user_id,
    )
    await session.flush()
    return await refresh_checklist(
        session, claim=claim, actor_user_id=actor_user_id
    )


# --------------------------------------------------------------------------
# The gate (spec §2 / §5.3 — "missing required items DO block submission")
# --------------------------------------------------------------------------


async def assert_packet_complete(
    session: AsyncSession,
    *,
    claim: ReimbClaim,
    actor_user_id: int,
    now: datetime | None = None,
) -> None:
    """Materialize the packet, then refuse the transition if anything is missing.

    Called from ``submit_claim`` (and the resubmit branch) AFTER totals are
    computed — the rules read fresh money — and BEFORE the workflow instance is
    started, so a refused submit creates no instance and burns no reference
    number.
    """
    view = await refresh_checklist(
        session, claim=claim, actor_user_id=actor_user_id, now=now or utc_now()
    )
    if not view.status.complete:
        raise errors.packet_incomplete(view.status.blocking, actor_is_owner=True)


async def assert_persisted_packet_complete(
    session: AsyncSession, *, claim: ReimbClaim
) -> None:
    """Approve-side gate: spec §9.4's *"never past a missing required item"*.

    Reads persisted rows ONLY — it deliberately does not re-materialize. Fresh
    evaluation mid-approval would let a catalog edit retroactively block a claim
    already in the chain, which workflow-standards §9 ("in-flight always
    finishes") forbids. The submit-time materialization IS the snapshot, and
    **row existence encodes what was required**: a rule that stopped applying
    leaves its row dormant unless it holds evidence, and a row holding evidence
    can never be blocking. That is why no ``required_snapshot`` column is needed.

    The remedy is always available — an approver who cannot approve can return.
    """
    rows = (
        (
            await session.execute(
                select(ReimbChecklistItem, ReimbChecklistCatalog)
                .join(
                    ReimbChecklistCatalog,
                    ReimbChecklistCatalog.id == ReimbChecklistItem.catalog_id,
                )
                .where(ReimbChecklistItem.claim_id == claim.id)
            )
        )
        .all()
    )
    counts = await evidence.evidence_counts(session, claim_id=claim.id)

    blocking = [
        engine.BlockingItem(
            catalog_id=catalog.id,
            item_id=item.id,
            code=catalog.code,
            label=catalog.label,
            group=catalog.group,
            evidence=catalog.evidence,
        )
        for item, catalog in rows
        if catalog.evidence in engine.BLOCKING_EVIDENCE
        and item.waiver_reason is None
        and item.status != "generated"
        and counts.get(item.id, (0, 0, 0))[0] == 0
    ]
    if blocking:
        raise errors.packet_incomplete(blocking, actor_is_owner=False)


async def persisted_packet_complete(
    session: AsyncSession, *, claim: ReimbClaim
) -> bool:
    """Boolean form of the approve-side gate — ``services/actions.py`` filters
    the offered verb set with it so the UI never shows a button certain to 422."""
    try:
        await assert_persisted_packet_complete(session, claim=claim)
    except Exception:  # the only raiser is packet_incomplete
        return False
    return True
