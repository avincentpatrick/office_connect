"""core/money — the platform rounding convention (ROUND_HALF_UP to the centavo)."""

from decimal import Decimal

from office_connect.core.money import CENT, money_str, to_money


def test_half_up_rounds_the_half_cent_up():
    assert to_money(Decimal("0.005")) == Decimal("0.01")
    assert to_money(Decimal("1.125")) == Decimal("1.13")  # banker's would give 1.12


def test_below_half_rounds_down():
    assert to_money(Decimal("0.014")) == Decimal("0.01")
    assert to_money(Decimal("2.994")) == Decimal("2.99")


def test_accepts_str_and_int_inputs():
    assert to_money("1234.5") == Decimal("1234.50")
    assert to_money(1500) == Decimal("1500.00")


def test_result_always_has_two_decimal_places():
    assert to_money(Decimal("2200")).as_tuple().exponent == CENT.as_tuple().exponent


def test_money_str_is_the_canonical_jsonb_form():
    assert money_str(Decimal("5500")) == "5500.00"
    assert money_str("0.005") == "0.01"
    assert money_str(0) == "0.00"
