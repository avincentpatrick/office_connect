"""Hash-chained audit trail — automatic, app-level (Day-1 #3; standing rule 5).

Every ORM flush through ``OCSession`` records insert / update / soft_delete
events into ``core_audit_logs``, hash-chained (SHA-256) so tampering with any
row breaks the chain from that point on. The write happens in ``after_flush``
on the same connection, so audit rows commit or roll back **atomically** with
the business change.

Design notes (docs/modules/foundation.md §7):
- Pure functions (``canonical_json``/``compute_row_hash``/``verify_chain``)
  survive any later re-wiring; reconcile with CSS-IS ``rechain_audit.py`` at
  Phase 1.
- A ``pg_advisory_xact_lock`` serializes chain writers. Fine at office scale;
  the documented escape valve is per-``table_name`` chains.
- App-level auditing does not capture raw-SQL writes — the chain proves log
  *integrity*, not *completeness*; DB grants close the delete/update paths.
"""

import base64
import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import event, insert, select, text
from sqlalchemy import inspect as sa_inspect

from office_connect.core.base import Base, SoftDeleteMixin
from office_connect.core.models.audit_log import AuditLog
from office_connect.core.models.login_attempt import LoginAttempt
from office_connect.core.models.notification import NotificationDelivery
from office_connect.core.models.query_log import QueryLog
from office_connect.core.models.report_lineage import ReportLineage
from office_connect.core.session import OCSession
from office_connect.core.time import UTC, utc_now

GENESIS_HASH = "0" * 64
_PENDING_KEY = "pending_audit"
# The append-only logs are never themselves audited (they ARE log mechanisms).
_UNAUDITED = (AuditLog, QueryLog, NotificationDelivery, ReportLineage, LoginAttempt)

# SPI / secret columns whose VALUES never enter the immutable hash chain (a chain
# row can never be redacted). The field NAME is still recorded (so "the field
# changed" stays auditable); only the value is replaced by this marker. A model
# opts a column in via ``__audit_exclude__`` (a frozenset of column keys). This is
# the Stage-B execution of the audit-payload SPI policy (database-standards §7,
# master-plan §4 #4) for credential secrets; broader person-field SPI lands in B4.
_REDACTED = "[redacted]"


def _audit_exclude(obj: Any) -> frozenset[str]:
    return getattr(type(obj), "__audit_exclude__", frozenset())


# --- pure hash core -------------------------------------------------------


def serialize_value(value: Any) -> Any:
    """Canonical JSON-native form of a column value (deterministic).

    Numbers that are not ints are stringified: Postgres jsonb normalizes
    numeric literals (1.2e16 -> 12000000000000000), so a raw float would hash
    one way at write time and re-serialize differently after the JSONB
    round-trip — permanently breaking verify_chain. Strings round-trip
    verbatim.
    """
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, datetime):
        return value.isoformat()  # aware-only by platform convention
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, dict):
        return {k: serialize_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize_value(v) for v in value]
    return str(value)


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_row_hash(prev_hash: str, payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        (prev_hash + "|" + canonical_json(payload)).encode("utf-8")
    ).hexdigest()


def build_payload(
    *,
    table: str,
    row_pk: int,
    action: str,
    actor_id: int | None,
    request_id: str | None,
    at: datetime,
    old: dict[str, Any] | None,
    new: dict[str, Any] | None,
) -> dict[str, Any]:
    """Exactly what gets hashed — the writer and ``verify_chain`` must agree."""
    return {
        "table": table,
        "row_pk": row_pk,
        "action": action,
        "actor_id": actor_id,
        "request_id": request_id,
        "at": at.astimezone(UTC).isoformat(),
        "old": old,
        "new": new,
    }


def verify_chain(rows: list[AuditLog]) -> int | None:
    """Recompute the chain from genesis over rows ordered by id.

    Returns the id of the first broken row, or None if the chain holds.
    QA gate: a tampered row MUST be reported (docs/modules/foundation.md §6).
    """
    prev = GENESIS_HASH
    for row in rows:
        payload = build_payload(
            table=row.table_name,
            row_pk=row.row_pk,
            action=row.action,
            actor_id=row.actor_id,
            request_id=row.request_id,
            at=row.created_at,
            old=row.old_data,
            new=row.new_data,
        )
        if row.prev_hash != prev or row.row_hash != compute_row_hash(prev, payload):
            return row.id
        prev = row.row_hash
    return None


# --- session listeners ----------------------------------------------------


@event.listens_for(OCSession, "persistent_to_deleted")
def _block_cascade_deletes(session, obj) -> None:
    """Catch deletions the before_flush guard cannot see (delete-orphan
    cascade victims are discovered by the unit-of-work AFTER before_flush).
    Convention (database-standards.md §8): relationships never use
    delete-orphan — this guard makes a violation fail loudly."""
    raise RuntimeError(
        "Hard deletes are forbidden (standing rule 6) - a relationship cascade "
        "attempted to delete a row. Do not configure delete-orphan cascades; "
        "use soft_delete() on the child instead."
    )


@event.listens_for(OCSession, "do_orm_execute")
def _block_unaudited_bulk_dml(state) -> None:
    """ORM-enabled bulk UPDATE/DELETE bypasses the unit of work, so no audit
    rows would be written. Forbid it; mutate loaded instances instead.
    ``execution_options(allow_unaudited=True)`` is the sanctioned escape hatch
    for maintenance scripts that log their own audit rows."""
    if (state.is_update or state.is_delete) and not state.execution_options.get(
        "allow_unaudited", False
    ):
        raise RuntimeError(
            "Bulk ORM UPDATE/DELETE bypasses the audit chain (standing rule 5) "
            "- load and mutate instances, or pass "
            "execution_options(allow_unaudited=True) and write audit rows "
            "yourself."
        )


@event.listens_for(OCSession, "before_flush")
def _capture_changes(session, flush_context, instances) -> None:
    """Capture change history before flush (values still loaded; no IO here)."""
    for obj in session.deleted:
        if isinstance(obj, Base):
            raise RuntimeError(
                "Hard deletes are forbidden (standing rule 6) - use "
                "office_connect.core.soft_delete.soft_delete() instead."
            )

    pending: list[tuple[Any, str, dict | None, dict | None]] = []

    for obj in session.new:
        if isinstance(obj, Base) and not isinstance(obj, _UNAUDITED):
            pending.append((obj, "insert", None, None))  # values read after INSERT

    for obj in session.dirty:
        if not isinstance(obj, Base) or isinstance(obj, _UNAUDITED):
            continue
        if not session.is_modified(obj, include_collections=False):
            continue
        state = sa_inspect(obj)
        excluded = _audit_exclude(obj)
        old_diff: dict[str, Any] = {}
        new_diff: dict[str, Any] = {}
        for attr in state.mapper.column_attrs:
            # No loader callables emitted (async-safe). Known limit: a column
            # assigned without ever being loaded records old=None.
            history = state.attrs[attr.key].history
            if not history.has_changes():
                continue
            old_value = history.deleted[0] if history.deleted else None
            new_value = history.added[0] if history.added else None
            if attr.key in excluded:
                # Record that an SPI/secret field changed, never its value.
                old_diff[attr.key] = _REDACTED if old_value is not None else None
                new_diff[attr.key] = _REDACTED if new_value is not None else None
                continue
            old_diff[attr.key] = serialize_value(old_value)
            new_diff[attr.key] = serialize_value(new_value)
        if not new_diff:
            continue
        action = "update"
        if isinstance(obj, SoftDeleteMixin):
            history = state.attrs["deleted_at"].history
            if history.has_changes() and history.added and history.added[0] is not None:
                action = "soft_delete"
        pending.append((obj, action, old_diff, new_diff))

    # Overwrite (not append): a failed+rolled-back flush must not leak stale
    # captures into the next flush.
    session.info[_PENDING_KEY] = pending


@event.listens_for(OCSession, "after_flush")
def _write_audit_rows(session, flush_context) -> None:
    """Write chained audit rows on the flush connection (same transaction)."""
    pending = session.info.pop(_PENDING_KEY, None)
    if not pending:
        return

    conn = session.connection()
    # Serialize chain writers for the transaction's duration. The lock is held
    # from the transaction's FIRST flush until COMMIT/ROLLBACK — keep audited
    # write transactions short (documented trade-off, foundation.md §7).
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('core_audit_logs'))"))
    prev = (
        conn.execute(
            select(AuditLog.row_hash).order_by(AuditLog.id.desc()).limit(1)
        ).scalar_one_or_none()
        or GENESIS_HASH
    )

    actor_id = session.info.get("actor_id")
    request_id = session.info.get("request_id")
    rows: list[dict[str, Any]] = []
    for obj, action, old_diff, new_diff in pending:
        state = sa_inspect(obj)
        table = state.mapper.local_table.name
        pk_col = state.mapper.primary_key[0]
        pk_key = state.mapper.get_property_by_column(pk_col).key
        row_pk = state.dict.get(pk_key)  # populated by the INSERT/UPDATE just run
        if action == "insert":
            # Full row image from values present post-INSERT (no lazy loads —
            # unfetched server defaults are simply omitted). SPI/secret columns
            # are redacted (field name kept, value withheld) so the immutable
            # chain never seals an un-removable secret (§7 payload policy).
            excluded = _audit_exclude(obj)
            new_diff = {}
            for attr in state.mapper.column_attrs:
                if attr.key not in state.dict:
                    continue
                value = state.dict[attr.key]
                if attr.key in excluded:
                    new_diff[attr.key] = _REDACTED if value is not None else None
                else:
                    new_diff[attr.key] = serialize_value(value)
            old_diff = None
        at = utc_now()
        payload = build_payload(
            table=table,
            row_pk=row_pk,
            action=action,
            actor_id=actor_id,
            request_id=request_id,
            at=at,
            old=old_diff,
            new=new_diff,
        )
        row_hash = compute_row_hash(prev, payload)
        rows.append(
            {
                "created_at": at,  # app-set: it is inside the hash
                "actor_id": actor_id,
                "request_id": request_id,
                "table_name": table,
                "row_pk": row_pk,
                "action": action,
                "old_data": old_diff,
                "new_data": new_diff,
                "prev_hash": prev,
                "row_hash": row_hash,
            }
        )
        prev = row_hash

    conn.execute(insert(AuditLog.__table__), rows)
