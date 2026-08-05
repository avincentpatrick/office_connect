"""R-6-liq-chain: the kind-aware status vocabulary.

A pure-data module, so these are pure tests — no session, no fixtures. What they
pin is the *contract* between three things that must never disagree: the
vocabularies, the workflow definitions, and the SQL that spans both kinds.
"""

from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType

import pytest

from office_connect.modules.reimbursement.services import status as st
from office_connect.modules.reimbursement.workflow import DEFINITION_CODES


def test_every_kind_has_a_definition_and_vice_versa():
    """A kind with labels but no chain would create claims nobody can submit; a
    chain with no labels would render raw state codes at the user."""
    assert set(st.VOCABULARIES) == set(DEFINITION_CODES)


@pytest.mark.parametrize("vocab", list(st.VOCABULARIES.values()), ids=lambda v: v.kind)
def test_a_vocabulary_is_internally_complete(vocab):
    """Every authored state needs a label AND a next-action entry — the two
    lookups the read-model writes on every transition."""
    states = set(vocab.all_states)
    assert set(vocab.labels) == states
    assert set(vocab.next_action) == states
    # The sets that drive holder resolution must name states this kind has.
    assert vocab.terminal <= states
    assert vocab.claimant <= states
    assert vocab.external <= states
    # Spec §6.1/§6.2: terminal states show "—"; every live state names ONE
    # next action (spec §7 rule 2, "one next action, always").
    for code in states:
        if code in vocab.terminal:
            assert vocab.next_action[code] is None
        else:
            assert vocab.next_action[code]


@pytest.mark.parametrize("vocab", list(st.VOCABULARIES.values()), ids=lambda v: v.kind)
def test_a_state_is_never_both_terminal_and_held(vocab):
    """Terminal states clear the holder (``resolve_holder`` returns
    ``(None, None)``), so a code in both sets would be a contradiction the
    lifecycle sync resolves silently and wrongly."""
    assert not vocab.terminal & vocab.claimant
    assert not vocab.terminal & vocab.external
    assert not vocab.claimant & vocab.external


def test_shared_codes_mean_the_same_thing_in_both_chains():
    """``draft``/``returned``/``handed_to_fms``/``cancelled`` appear in both
    vocabularies. They may carry different next-action COPY, but they must not
    change category — a ``handed_to_fms`` that were claimant-held in one chain
    and external in the other would make ``resolve_holder`` kind-dependent in a
    way no reader would expect."""
    shared = set(st.REIMBURSEMENT.all_states) & set(st.LIQUIDATION.all_states)
    assert shared == {st.DRAFT, st.RETURNED, st.HANDED_TO_FMS, st.CANCELLED}
    for code in shared:
        assert (code in st.REIMBURSEMENT.claimant) == (code in st.LIQUIDATION.claimant)
        assert (code in st.REIMBURSEMENT.external) == (code in st.LIQUIDATION.external)
        assert (code in st.REIMBURSEMENT.terminal) == (code in st.LIQUIDATION.terminal)


def test_the_union_covers_every_kind():
    """THE trap this increment had to avoid. My-Work's two queries span both
    kinds in one statement, so they filter on the UNION; if ``settled`` were
    missing from it, every settled liquidation would sit in someone's inbox
    forever. Derived, so a future kind cannot be forgotten — this asserts the
    derivation, not a hand-written list."""
    for vocab in st.VOCABULARIES.values():
        assert vocab.terminal <= st.ALL_TERMINAL_STATES
        assert vocab.claimant <= st.ALL_CLAIMANT_STATES
    assert st.SETTLED in st.ALL_TERMINAL_STATES
    assert st.PAID_CLOSED in st.ALL_TERMINAL_STATES


def test_lookup_is_fail_loud_not_fail_quiet():
    """An unknown kind raises rather than falling back to reimbursement: a
    silent fallback would render a liquidation with claim labels and stamp claim
    next-actions on it, which reads as working software."""
    assert st.vocabulary("liquidation") is st.LIQUIDATION
    assert st.vocabulary("reimbursement") is st.REIMBURSEMENT
    # NULL is the one tolerated case — the legacy pre-stamp rows delta row 48
    # already coalesces elsewhere.
    assert st.vocabulary(None) is st.REIMBURSEMENT
    with pytest.raises(RuntimeError, match="no status vocabulary"):
        st.vocabulary("travel_order")


def test_certification_a_has_no_state():
    """Spec §6.2 reads "Certifications (A→B→C in order)", but A is the
    CLAIMANT's and the claimant is the maker — they certify by submitting.
    Authoring A as a gate would ask ``enforce_segregation`` to let the
    originator clear their own step. The absence is the decision."""
    assert st.CERTIFY_B in st.LIQUIDATION.all_states
    assert st.CERTIFY_C in st.LIQUIDATION.all_states
    assert "certify_a" not in st.LIQUIDATION.all_states


# --- R-7-board: the three columns (spec §9.6) ------------------------------


@pytest.mark.parametrize("vocab", list(st.VOCABULARIES.values()), ids=lambda v: v.kind)
def test_every_state_declares_a_board_column(vocab):
    """Mandatory per state, like a label — but the stakes differ. An unlabelled
    state renders as a raw code at a user, who can SEE that it is wrong. A state
    with no column disappears from a peso total, and "board totals match DB" is
    the one sentence spec §14 grades this surface on."""
    assert set(vocab.board_column) == set(vocab.all_states)
    for state, column in vocab.board_column.items():
        assert column is None or column in st.BOARD_COLUMN_LABELS, state


def test_the_states_off_the_board_are_off_it_deliberately():
    """``None`` is an authored declaration, not a gap. ``draft`` is nobody's
    oversight — it is the traveller's own work and My Work has it, the same
    reason the queue's ``base_query`` excludes it. ``cancelled`` is spec §6.1
    row 9's "terminal, excluded from KPIs": a voided claim produced no
    disbursement, so counting it would inflate a total with money that never
    moved."""
    for vocab in st.VOCABULARIES.values():
        assert vocab.board_column[st.DRAFT] is None
        assert vocab.board_column[st.CANCELLED] is None
    assert st.DRAFT not in st.ALL_BOARD_STATES
    assert st.CANCELLED not in st.ALL_BOARD_STATES


def test_the_column_sets_are_derived_not_hand_listed():
    """Same rule ``ALL_TERMINAL_STATES`` follows. A kind that gains a state and
    is forgotten in a hand-written list would leave money missing from a column
    with nothing on screen to say so."""
    for vocab in st.VOCABULARIES.values():
        for state, column in vocab.board_column.items():
            if column is None:
                continue
            assert state in st.BOARD_COLUMN_STATES[column]
    # Both chains end in the same column: a liquidation is work in the same
    # pipeline, and forking the board by kind would ask a chief to read two.
    assert st.PAID_CLOSED in st.BOARD_COLUMN_STATES[st.BOARD_DONE]
    assert st.SETTLED in st.BOARD_COLUMN_STATES[st.BOARD_DONE]
    assert st.BOARD_COLUMN_STATES[st.WITH_FMS] == {st.HANDED_TO_FMS}


def test_the_columns_are_pairwise_disjoint():
    """THE trap this increment had to avoid. ``column_totals`` groups by status
    ACROSS kinds in ONE statement and buckets the rows through
    ``BOARD_COLUMN_STATES`` — so a code one kind called In Bureau and another
    called Done would be counted in BOTH columns, and the board would total more
    than the database holds."""
    for column, states in st.BOARD_COLUMN_STATES.items():
        for other, other_states in st.BOARD_COLUMN_STATES.items():
            if column != other:
                assert not states & other_states, (column, other)


def test_a_vocabulary_missing_a_column_fails_loudly():
    """What makes the invariant a promise rather than a comment. Build a
    deliberately broken vocabulary and prove ``_assert_board_columns`` bites —
    an assertion nothing ever exercises is a comment with a runtime cost."""
    broken = replace(
        st.REIMBURSEMENT,
        board_column=MappingProxyType(
            {
                state: column
                for state, column in st.REIMBURSEMENT.board_column.items()
                if state != st.ADMIN_REVIEW
            }
        ),
    )
    with pytest.raises(RuntimeError, match="no board column"):
        st._assert_board_columns({"reimbursement": broken})


def test_a_vocabulary_naming_an_unknown_column_fails_loudly():
    """A typo in a column key would otherwise put a whole status in a column
    that renders nowhere."""
    broken = replace(
        st.REIMBURSEMENT,
        board_column=MappingProxyType(
            {**st.REIMBURSEMENT.board_column, st.ADMIN_REVIEW: "in-bureau"}
        ),
    )
    with pytest.raises(RuntimeError, match="unknown board columns"):
        st._assert_board_columns({"reimbursement": broken})


def test_board_column_lookup_is_kind_aware():
    """The per-row sibling of the cross-kind sets."""
    assert st.board_column("reimbursement", st.ADMIN_REVIEW) == st.IN_BUREAU
    assert st.board_column("liquidation", st.CERTIFY_C) == st.IN_BUREAU
    assert st.board_column("liquidation", st.SETTLED) == st.BOARD_DONE
    assert st.board_column("reimbursement", st.CANCELLED) is None
    # A liquidation never reaches `admin_review`, so asking is answering "not on
    # this chain" rather than guessing a column from a code alone.
    assert st.board_column("liquidation", st.ADMIN_REVIEW) is None
    assert st.board_column("reimbursement", None) is None
