from datetime import date
from decimal import Decimal

import pytest

from anyreconcile.fx import load_rates, rate, to_eur, with_eur
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


# AUD-3: a rate of any age used to be accepted.


def test_aud3_stale_rate_is_refused_with_a_hint(rates):
    with pytest.raises(
        ValueError, match=r"no USD rate within 7 days before 2026-09-15.*--download-rates"
    ):
        rate(rates, "USD", date(2026, 9, 15))


def test_aud3_the_limit_is_inclusive_and_can_be_changed(rates):
    # The last rate in the fixture is 2026-02-03, so the 10th is 7 days later and the 11th is 8.
    assert rate(rates, "USD", date(2026, 2, 10)) == Decimal("1.2500")
    with pytest.raises(ValueError, match="within 7 days"):
        rate(rates, "USD", date(2026, 2, 11))
    assert rate(rates, "USD", date(2026, 2, 11), max_age_days=8) == Decimal("1.2500")


def test_aud3_with_eur_and_to_eur_pass_the_limit_on(rates):
    t = Transaction("mercury", "mercury", "", date(2026, 2, 20), Decimal("125"), "USD")
    with pytest.raises(ValueError, match="within 7 days"):
        with_eur([t], rates)
    assert with_eur([t], rates, max_age_days=30)[0].eur == Decimal("100")
    with pytest.raises(ValueError, match="within 7 days"):
        to_eur(Decimal("1"), "USD", date(2026, 2, 20), rates)


# A malformed rates file must be an error that says where, not a traceback or a division by zero.


def rates_file(tmp_path, text):
    p = tmp_path / "r.csv"
    p.write_text(text)
    return p


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("Day,USD,\n2026-01-05,1.10,\n", "no Date column"),
        ("Date,USD,\nJan 5,1.10,\n", r"r\.csv line 2: bad date 'Jan 5'"),
        ("Date,USD,\n2026-01-05,1.10,\n2026-01-06,abc,\n", r"r\.csv line 3: bad USD rate 'abc'"),
        ("Date,USD,\n2026-01-05,0,\n", r"r\.csv line 2: bad USD rate '0'"),
        ("Date,USD,\n2026-01-05,-1.2,\n", r"r\.csv line 2: bad USD rate '-1\.2'"),
        ("Date,USD,\n2026-01-05,NaN,\n", r"r\.csv line 2: bad USD rate 'NaN'"),
    ],
)
def test_malformed_rates_file_is_a_clear_error(tmp_path, text, message):
    with pytest.raises(ValueError, match=message):
        load_rates(rates_file(tmp_path, text))


def test_na_cells_and_the_trailing_comma_are_still_fine(tmp_path):
    loaded = load_rates(rates_file(tmp_path, "Date,USD,GBP,\n2026-01-05,1.10,N/A,\n"))
    assert list(loaded) == ["USD"]
