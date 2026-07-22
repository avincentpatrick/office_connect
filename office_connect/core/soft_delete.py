"""Soft-delete enforcement (standing rule 6; database-standards.md §8).

Every ORM select of a ``SoftDeleteMixin`` entity is filtered to
``deleted_at IS NULL`` by default — including relationship and aliased loads.
Escape hatch: ``.execution_options(include_deleted=True)``.

Caveats (documented in database-standards.md §8):
- ``with_loader_criteria`` filters ORM entity selects only — raw ``text()`` /
  Core-table queries bypass it. Query via ORM entities.
- ``session.get()`` served from the identity map emits no SELECT, so an
  already-loaded soft-deleted object is still returned. Treat ``get()`` on
  possibly-deleted rows accordingly (check ``deleted_at``) or query via
  ``select()``.

The DB-level backstop is the grants: ``oc_app`` has no DELETE privilege
anywhere, and ``core/audit.py`` raises on ``session.delete()`` and on
cascade deletions.
"""

from sqlalchemy import event
from sqlalchemy.orm import ORMExecuteState, with_loader_criteria

from office_connect.core.base import SoftDeleteMixin
from office_connect.core.session import OCSession
from office_connect.core.time import utc_now


@event.listens_for(OCSession, "do_orm_execute")
def _filter_soft_deleted(state: ORMExecuteState) -> None:
    if (
        state.is_select
        and not state.is_column_load
        and not state.is_relationship_load
        and not state.execution_options.get("include_deleted", False)
    ):
        state.statement = state.statement.options(
            with_loader_criteria(
                SoftDeleteMixin,
                lambda cls: cls.deleted_at.is_(None),
                include_aliases=True,
            )
        )


def soft_delete(obj: SoftDeleteMixin, *, actor_id: int | None = None) -> None:
    """Mark a row deleted (idempotent). The audit listener records the
    transition as action ``soft_delete`` at the next flush."""
    if obj.deleted_at is not None:
        return
    obj.deleted_at = utc_now()
    obj.deleted_by = actor_id
