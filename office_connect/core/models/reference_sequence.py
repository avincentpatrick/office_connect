"""Reference-number sequences — core-service #5 (master-plan §1.1).

One allocator for every `XX-YYYY-NNNN` series platform-wide (reimbursement
`RB-`/`LQ-` first; DTWIS/QMS/supply later). A row per `(scope, year)` holds the last
allocated integer; `core/reference_numbers.py` locks + increments it. Numbers reset
yearly and are **never reused** — the counter only ever advances, so a soft-deleted or
voided record's number stays retired even though the partial-unique index on the owning
table (which excludes `deleted_at IS NOT NULL`) would technically permit reuse.

Business-class table (it is mutated as the counter advances); soft-delete columns are
present for convention but a sequence is never deleted.
"""

from sqlalchemy import BigInteger, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column

from office_connect.core.base import (
    AuditColsMixin,
    Base,
    PKMixin,
    SoftDeleteMixin,
)


class ReferenceSequence(PKMixin, AuditColsMixin, SoftDeleteMixin, Base):
    __tablename__ = "core_reference_sequences"
    __table_args__ = (
        # One counter per (scope, year), forever — a sequence row is never deleted,
        # so this is a full (not partial) unique index.
        Index(
            "uq_core_reference_sequences_scope_year", "scope", "year", unique=True
        ),
    )

    scope: Mapped[str]  # the series prefix, e.g. "RB", "LQ"
    year: Mapped[int] = mapped_column(Integer)
    last_value: Mapped[int] = mapped_column(BigInteger, default=0)
