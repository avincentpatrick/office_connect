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

# --- R-7-board: the pipeline board's three columns (spec §9.6) --------------
# Columns are GROUPS of states, not states — spec §9.2's screen inventory says
# so out loud ("Columns = status groups"). The grouping is per KIND for the same
# reason the labels are: `certify_b` exists only on a liquidation and
# `admin_review` only on a reimbursement, and a flat dict keyed by code would
# have to lean on "a code means the same thing in both chains", which is a
# docstring promise rather than an enforced one.
IN_BUREAU = "in_bureau"
WITH_FMS = "with_fms"
BOARD_DONE = "done"

#: Left-to-right board order, with the header label. Display strings live here
#: beside ``labels`` so the browser authors none of them — the same rule
#: ``external.label`` follows for the FMS sub-statuses.
BOARD_COLUMNS: tuple[tuple[str, str], ...] = (
    (IN_BUREAU, "In Bureau"),
    (WITH_FMS, "With FMS"),
    (BOARD_DONE, "Done"),
)


@dataclass(frozen=True, slots=True)
class Vocabulary:
    """One claim kind's status vocabulary — the whole read-model contract.

    ``claimant`` and ``external`` drive ``lifecycle.resolve_holder``; ``terminal``
    clears the holder; ``all_states`` is what ``workflow._assert_graph_invariants``
    checks the authored graph against, so a state added to a definition without a
    label here fails at seed time rather than rendering as a raw code in the UI.

    ``board_column`` (R-7-board) is mandatory per state for the same reason
    ``labels`` effectively is, but the stakes are different: an unlabelled state
    renders as a raw code at a user, who can SEE that it is wrong. A state with
    no column would vanish silently from a peso total — and "board totals match
    DB" is the one sentence spec §14 grades this surface on. So
    ``_assert_board_columns`` refuses a vocabulary that leaves one out, and
    ``None`` is the authored declaration that a state is deliberately off the
    board rather than the absence of a decision.
    """

    kind: str
    all_states: tuple[str, ...]
    terminal: frozenset[str]
    claimant: frozenset[str]
    external: frozenset[str]
    labels: Mapping[str, str]
    next_action: Mapping[str, str | None]
    board_column: Mapping[str, str | None]


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
    # Spec §9.6's three columns. `fms_returned` and `returned` are In Bureau
    # because the packet is physically back inside the bureau — bounced onto an
    # Admin Officer's desk, or back to the traveller who sits in it. The board
    # answers "how much is where", and both of those are here rather than with
    # FMS or finished.
    board_column=MappingProxyType(
        {
            # Nobody's oversight — an unsubmitted claim is the traveller's own
            # work and My Work already shows it. Same reason the queue's
            # `base_query` excludes it.
            DRAFT: None,
            DIVISION_APPROVAL: IN_BUREAU,
            ADMIN_REVIEW: IN_BUREAU,
            HANDED_TO_FMS: WITH_FMS,
            FMS_RETURNED: IN_BUREAU,
            RETURNED: IN_BUREAU,
            PAID_CLOSED: BOARD_DONE,
            # Spec §6.1 row 9: "terminal, excluded from KPIs". A voided claim
            # in Done would inflate a peso total with money that never moved.
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
    # A liquidation is work in the SAME pipeline, so it rides the same three
    # columns — forking the board by kind would ask a bureau chief to read two
    # boards to answer one question. The certifications are In Bureau (they sit
    # on a named person's desk) and `settled` is the liquidation's `paid_closed`.
    board_column=MappingProxyType(
        {
            DRAFT: None,
            CERTIFY_B: IN_BUREAU,
            CERTIFY_C: IN_BUREAU,
            HANDED_TO_FMS: WITH_FMS,
            RETURNED: IN_BUREAU,
            SETTLED: BOARD_DONE,
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


# --- R-7-board: the derived column sets -------------------------------------

#: ``{column_key: header label}`` in board order.
BOARD_COLUMN_LABELS: Mapping[str, str] = MappingProxyType(dict(BOARD_COLUMNS))

#: ``{column_key: the states in it, across every kind}``.
#:
#: For CROSS-KIND SQL only, the same caveat ``ALL_TERMINAL_STATES`` carries:
#: the board's card query spans both kinds in one statement, so it cannot
#: resolve a per-row vocabulary. Derived, never hand-listed — a kind that gains
#: a state and is forgotten here would leave money missing from a column total
#: with nothing on screen to say so.
BOARD_COLUMN_STATES: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        column: frozenset(
            state
            for voc in VOCABULARIES.values()
            for state, assigned in voc.board_column.items()
            if assigned == column
        )
        for column, _label in BOARD_COLUMNS
    }
)

#: Every state that appears on the board at all.
ALL_BOARD_STATES: frozenset[str] = frozenset().union(*BOARD_COLUMN_STATES.values())


def _assert_board_columns(
    vocabularies: Mapping[str, Vocabulary] = VOCABULARIES,
) -> None:
    """Every state declares a column, and no state declares two.

    Runs at import so a mis-authored vocabulary fails on the first request
    rather than on a quiet Tuesday when a director notices the totals are short.
    Parameterized so a test can build a deliberately broken vocabulary and prove
    the invariant actually bites — an unexercised assertion is a comment.

    The third check is the one nobody would think of. ``queue.column_totals``
    groups by status ACROSS kinds in one statement and buckets the rows through
    ``BOARD_COLUMN_STATES``, so a code that one kind called In Bureau and
    another called Done would be counted in BOTH columns: the board would total
    more than the database holds, which is the exact sentence spec §14 grades.
    """
    known = set(BOARD_COLUMN_LABELS)
    for kind, voc in vocabularies.items():
        missing = set(voc.all_states) - set(voc.board_column)
        if missing:
            raise RuntimeError(
                f"claim kind '{kind}' has states with no board column: "
                f"{sorted(missing)}. Every state must name one of "
                f"{sorted(known)} or None (deliberately off the board) — a "
                f"state with no column vanishes from the pipeline totals "
                f"silently."
            )
        stray = set(voc.board_column) - set(voc.all_states)
        if stray:
            raise RuntimeError(
                f"claim kind '{kind}' assigns board columns to states it does "
                f"not have: {sorted(stray)}."
            )
        unknown = {
            column for column in voc.board_column.values() if column not in known
        } - {None}
        if unknown:
            raise RuntimeError(
                f"claim kind '{kind}' names unknown board columns "
                f"{sorted(unknown)} — known columns are {sorted(known)}."
            )

    seen: dict[str, str] = {}
    for column, states in BOARD_COLUMN_STATES.items():
        for state in states:
            if state in seen and seen[state] != column:
                raise RuntimeError(
                    f"state '{state}' is in two board columns "
                    f"('{seen[state]}' and '{column}'). The board groups by "
                    f"status across kinds in one query, so a state in two "
                    f"columns is counted twice and the totals exceed the "
                    f"database."
                )
            seen[state] = column


_assert_board_columns()


def board_column(kind: str | None, status: str | None) -> str | None:
    """Which board column a claim falls in, or ``None`` if it is off the board.

    Per-row and kind-aware, the sibling of ``vocabulary(kind).labels``. The
    cross-kind SQL uses ``BOARD_COLUMN_STATES`` instead; this exists for the
    single-row question.
    """
    if status is None:
        return None
    return vocabulary(kind).board_column.get(status)
