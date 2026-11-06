from datetime import date
from decimal import Decimal

import pytest

from anyreconcile.fx import rate, to_eur, with_eur
from anyreconcile.model import Transaction


def test_exact_day(rates):
    assert rate(rates, "USD", date(2026, 1, 5)) == Decimal("1.1000")


def test_weekend_uses_friday(rates):
    # 2026-01-17 is a Saturday. Friday the 16th is the first day of the 1.25 rate.
    assert rate(rates, "USD", date(2026, 1, 17)) == Decimal("1.2500")
    assert rate(rates, "USD", date(2026, 1, 11)) == Decimal("1.1000")  # Sunday after 1.10


def test_rate_change_between_days(rates):
    assert rate(rates, "USD", date(2026, 1, 15)) == Decimal("1.1000")
    assert rate(rates, "USD", date(2026, 1, 16)) == Decimal("1.2500")


def test_na_cell_falls_back_to_earlier_day(rates):
    # GBP is "N/A" on 2026-01-09, so the 8th is used. Both days are 0.80.
    assert rate(rates, "GBP", date(2026, 1, 9)) == Decimal("0.8000")


def test_date_before_first_rate_is_an_error(rates):
    # 2026-01-01 is a holiday and the file starts on the 2nd.
    with pytest.raises(ValueError, match="on or before"):
        rate(rates, "USD", date(2026, 1, 1))


def test_eur_is_one_and_unknown_currency_fails(rates):
    assert rate(rates, "EUR", date(2020, 1, 1)) == 1
    with pytest.raises(ValueError, match="CHF"):
        rate(rates, "CHF", date(2026, 1, 5))


def test_to_eur_is_exact_decimal(rates):
    assert to_eur(Decimal("110.00"), "USD", date(2026, 1, 5), rates) == Decimal("100")
    assert to_eur(Decimal("125.00"), "USD", date(2026, 1, 16), rates) == Decimal("100")
    assert to_eur(Decimal("80.00"), "GBP", date(2026, 1, 5), rates) == Decimal("100")


def test_with_eur_keeps_original_amount_and_currency(rates):
    t = Transaction("mercury", "mercury", "", date(2026, 1, 16), Decimal("625.00"), "USD")
    (out,) = with_eur([t], rates)
    assert (out.amount, out.currency, out.eur) == (Decimal("625.00"), "USD", Decimal("500"))
