"""R-6-liq-chain: the kind-aware status vocabulary.

A pure-data module, so these are pure tests — no session, no fixtures. What they
pin is the *contract* between three things that must never disagree: the
vocabularies, the workflow definitions, and the SQL that spans both kinds.
"""

from __future__ import annotations

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
