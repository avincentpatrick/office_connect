"""Template map — which checklist item is satisfied by which generated document.

Spec §10 names ``reimb_template_map`` as the config that binds claim fields to
template placeholders. What ships here is deliberately **narrower**: a binding
table, not a placeholder-merge map.

The reason is that the merge half of §10 died with the Google-Docs flow. Under
WeasyPrint + Jinja2 (master-plan §1.1 #8, which outranks the reference spec) the
"mapping" from claim data to a rendered field is the Jinja template itself —
expressive, reviewable, diffable, and type-aware in a way a JSONB placeholder
dictionary never is. Re-encoding ``{{claimant_name}} → claim.claimant.full_name``
as data would buy nothing and cost a second grammar to validate, exactly the kind
of duplication rule 10 exists to prevent.

What genuinely *is* configuration is the binding: which catalog code
(``IOT-45``) is satisfied by which registered document (``reimb.iot45``), under
which COA circular revision, and whether it is currently issued at all. That
survives the engine change, and it is what the R-9 catalog editor will need in
order to retire a form when a circular is superseded — without a code change.

Rule 10 note: this is a candidate for core-service #13 (the shared document-type
/ signatory-config / template-map registry). It stays module-side for exactly the
reason core-service #7's storage did at R-3 — there is one consumer today, and a
second consumer is what tells you which columns are actually common. Promote at
Stage E when DTWIS arrives.
"""

from sqlalchemy import Index, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from office_connect.core.base import (
    AuditColsMixin,
    Base,
    LookupMixin,
    PKMixin,
    SoftDeleteMixin,
)


class ReimbTemplateMap(PKMixin, AuditColsMixin, SoftDeleteMixin, LookupMixin, Base):
    __tablename__ = "reimb_template_maps"
    __table_args__ = (
        Index(
            "uq_reimb_template_maps_kind_code",
            "claim_kind",
            "checklist_code",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    claim_kind: Mapped[str | None]  # "reimbursement" | "liquidation" | NULL (both)
    # The catalog code this document satisfies, e.g. "IOT-45". Deliberately a
    # code and not a catalog FK: the seed framework upserts catalog rows by
    # natural key, so the code is the stable identity and an FK would pin this
    # row to a surrogate id that a re-seed could legitimately change.
    checklist_code: Mapped[str]
    # Namespaced key registered with core.documents, e.g. "reimb.iot45".
    document_key: Mapped[str]
    title: Mapped[str] = mapped_column(Text)  # printed heading + filename stem
    form_no: Mapped[str | None] = mapped_column(Text)  # e.g. "GAM Vol. II, App. 45"
    circular_version: Mapped[str | None]
    sort: Mapped[int] = mapped_column(Integer, server_default=text("0"))
