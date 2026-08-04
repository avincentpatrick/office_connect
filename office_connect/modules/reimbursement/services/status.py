"""Claim status vocabulary — the module's read-model of the workflow states.

``reimb_claims.status`` stores the engine state code VERBATIM (identity mapping —
one vocabulary, no translation table). Legality of every move is the engine's
closed transitions set (workflow-standards.md §1), not DDL: the column stays a
plain varchar by decision (delta register; db-standards §5 deviation recorded).
Display strings live here so the wizard/My-Work UI renders labels, never raw
codes, and spec §6.1's "one next action, always" auto-copy is a lookup.

**Two kinds, two vocabularies, one module (R-6-liq-chain).** A ``reimb_claims``
row is a reimbursement OR a liquidation, and the two run different chains: spec
§6.1 for the claim, §6.2 for the liquidation. That is GENERALIZED here rather
than forked — one ``Vocabulary`` per kind, looked up by ``claim.kind``, because
the alternative (a second ``liquidation_status.py``) would duplicate the four
shared codes and let the two copies drift on the day one of them gains a state.

Four codes are SHARED and mean the same thing in both chains — ``draft``,
``returned``, ``handed_to_fms``, ``cancelled`` — so a code is globally unique in
its meaning even though the vocabularies that contain it differ. What differs is
the SET a chain may occupy and the next-action copy the holder is shown.

The FMS journey sub-statuses (With Budget / With Accounting / Payment
Processing) are NOT states — they ride ``reimb_external_events`` at R-7; the
engine holds one ``handed_to_fms`` state for the whole external leg (delta
register).
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

# --- Engine state codes (the status vocabulary) ---------------------------
# Shared by both chains — same code, same meaning.
DRAFT = "draft"
RETURNED = "returned"
HANDED_TO_FMS = "handed_to_fms"
CANCELLED = "cancelled"

# Reimbursement only (spec §6.1).
DIVISION_APPROVAL = "division_approval"
ADMIN_REVIEW = "admin_review"
FMS_RETURNED = "fms_returned"
PAID_CLOSED = "paid_closed"

# Liquidation only (spec §6.2, R-6-liq-chain). Certification A is absent by
# design: the claimant is the MAKER and certifies by submitting, never as a
# checker slot — see ``workflow.ensure_liquidation_definition``.
CERTIFY_B = "certify_b"
CERTIFY_C = "certify_c"
SETTLED = "settled"

REIMBURSEMENT_KIND = "reimbursement"
LIQUIDATION_KIND = "liquidation"


@dataclass(frozen=True, slots=True)
class Vocabulary:
    """One claim kind's status vocabulary — the whole read-model contract.

    ``claimant`` and ``external`` drive ``lifecycle.resolve_holder``; ``terminal``
    clears the holder; ``all_states`` is what ``workflow._assert_graph_invariants``
    checks the authored graph against, so a state added to a definition without a
    label here fails at seed time rather than rendering as a raw code in the UI.
    """

    kind: str
    all_states: tuple[str, ...]
    terminal: frozenset[str]
    claimant: frozenset[str]
    external: frozenset[str]
    labels: Mapping[str, str]
    next_action: Mapping[str, str | None]


REIMBURSEMENT = Vocabulary(
    kind=REIMBURSEMENT_KIND,
    all_states=(
        DRAFT,
        DIVISION_APPROVAL,
        ADMIN_REVIEW,
        HANDED_TO_FMS,
        FMS_RETURNED,
        RETURNED,
        PAID_CLOSED,
        CANCELLED,
    ),
    terminal=frozenset({PAID_CLOSED, CANCELLED}),
    # States where the claimant holds the ball (owner-held; holder = their user).
    claimant=frozenset({DRAFT, RETURNED}),
    # The one state held by FMS — outside the platform (spec §6.1 row 6).
    external=frozenset({HANDED_TO_FMS}),
    # Display labels (spec §6.1 status names).
    labels=MappingProxyType(
        {
            DRAFT: "Draft",
            DIVISION_APPROVAL: "For Approval",
            ADMIN_REVIEW: "Admin Review",
            HANDED_TO_FMS: "Handed to FMS",
            FMS_RETURNED: "FMS Returned",
            RETURNED: "Returned",
            PAID_CLOSED: "Paid / Closed",
            CANCELLED: "Cancelled/Void",
        }
    ),
    # "One next action, always" (spec §7 rule 2; §6.1 auto-copy, verbatim).
    # Terminal states carry None — the journey is over (spec shows "—").
    next_action=MappingProxyType(
        {
            DRAFT: "Complete your packet",
            DIVISION_APPROVAL: "Approve or return",
            ADMIN_REVIEW: "Final check & print packet",
            HANDED_TO_FMS: "Waiting on FMS — update status",
            FMS_RETURNED: "Relay FMS comments",
            RETURNED: "Fix and resubmit",
            PAID_CLOSED: None,
            CANCELLED: None,
        }
    ),
)

LIQUIDATION = Vocabulary(
    kind=LIQUIDATION_KIND,
    all_states=(
        DRAFT,
        CERTIFY_B,
        CERTIFY_C,
        HANDED_TO_FMS,
        RETURNED,
        SETTLED,
        CANCELLED,
    ),
    terminal=frozenset({SETTLED, CANCELLED}),
    claimant=frozenset({DRAFT, RETURNED}),
    external=frozenset({HANDED_TO_FMS}),
    labels=MappingProxyType(
        {
            DRAFT: "Draft",
            CERTIFY_B: "For Certification B",
            CERTIFY_C: "For Certification C",
            HANDED_TO_FMS: "Handed to FMS",
            RETURNED: "Returned",
            SETTLED: "Settled",
            CANCELLED: "Cancelled/Void",
        }
    ),
    next_action=MappingProxyType(
        {
            DRAFT: "Complete your liquidation",
            CERTIFY_B: "Certify or return",
            CERTIFY_C: "Record the Accounting certification",
            HANDED_TO_FMS: "Waiting on FMS — update status",
            RETURNED: "Fix and resubmit",
            SETTLED: None,
            CANCELLED: None,
        }
    ),
)

VOCABULARIES: Mapping[str, Vocabulary] = MappingProxyType(
    {REIMBURSEMENT_KIND: REIMBURSEMENT, LIQUIDATION_KIND: LIQUIDATION}
)


def vocabulary(kind: str | None) -> Vocabulary:
    """The vocabulary for a claim kind.

    ``None`` resolves to reimbursement: ``reimb_claims.kind`` is NOT NULL, but
    the same coalesce-to-the-original-kind courtesy the status column already
    gets (delta row 48) costs nothing here. An unknown kind is a DEVELOPER error,
    so it raises like ``_assert_graph_invariants`` rather than guessing — a
    silent fallback would render a liquidation with claim labels.
    """
    if kind is None:
        return REIMBURSEMENT
    try:
        return VOCABULARIES[kind]
    except KeyError:
        raise RuntimeError(
            f"no status vocabulary for claim kind '{kind}' — "
            f"known kinds are {sorted(VOCABULARIES)}."
        ) from None


#: Every kind's terminal states, unioned.
#:
#: For CROSS-KIND SQL only — My-Work's "waiting on you"/"waiting on others"
#: queries span both kinds in one statement, so they cannot resolve a per-row
#: vocabulary. Anything holding a claim uses ``vocabulary(claim.kind).terminal``
#: instead. Derived, never hand-listed: a kind that gains a terminal state and is
#: forgotten here would leave settled work in someone's inbox forever.
ALL_TERMINAL_STATES: frozenset[str] = frozenset().union(
    *(voc.terminal for voc in VOCABULARIES.values())
)

#: Every kind's claimant-held states, unioned. Same cross-kind-SQL caveat.
ALL_CLAIMANT_STATES: frozenset[str] = frozenset().union(
    *(voc.claimant for voc in VOCABULARIES.values())
)
