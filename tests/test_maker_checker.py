"""B3: maker-checker / segregation of duties (COA 92-389, NGICS)."""

import pytest

from office_connect.core.api.errors import APIError
from office_connect.core.maker_checker import assert_segregation


def test_distinct_maker_and_checkers_pass():
    # No exception = DV Boxes A/B/C all distinct, none is the preparer.
    assert_segregation(maker_id=1, checker_ids=[2, 3, 4])


def test_maker_cannot_be_a_checker():
    with pytest.raises(APIError) as exc:
        assert_segregation(maker_id=1, checker_ids=[2, 1])
    assert exc.value.status_code == 409
    assert exc.value.code == "segregation_of_duties"


def test_two_boxes_cannot_share_an_approver():
    with pytest.raises(APIError) as exc:
        assert_segregation(maker_id=1, checker_ids=[2, 2])
    assert exc.value.code == "segregation_of_duties"


def test_single_checker_distinct_from_maker_passes():
    assert_segregation(maker_id=5, checker_ids=[6])


def test_empty_checkers_is_vacuously_ok():
    assert_segregation(maker_id=5, checker_ids=[])
