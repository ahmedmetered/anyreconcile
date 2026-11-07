from helpers import txn

from anyreconcile.config import Config
from anyreconcile.internal import find_internal

CFG = Config()  # internal_days 2, spread 1.5 percent


def test_wise_to_mercury_with_fx_is_internal():
    # 1000 EUR out of Wise on the 7th. 1100 USD in on the 8th is 1000 EUR at 1.10.
    out = txn("-1000", day=7, account="wise")
    into = txn("1100", day=8, account="mercury", currency="USD", eur="1000", source="mercury")
    pairs, issues, rest = find_internal([out, into], CFG)
    assert [(p.out, p.into) for p in pairs] == [(out, into)] and issues == [] and rest == []


def test_conversion_spread_inside_tolerance_is_internal():
    # 496.36 against 500 is a 0.73 percent gap, inside 1.5 percent.
    out = txn("-500", account="wise")
    into = txn("546", account="mercury", currency="USD", eur="496.36", source="mercury")
    pairs, _, _ = find_internal([out, into], CFG)
    assert len(pairs) == 1


def test_spread_outside_tolerance_is_not_internal():
    # 470 against 500 is a 6 percent gap.
    out = txn("-500", account="revolut")
    into = txn("470", account="wise")
    pairs, issues, rest = find_internal([out, into], CFG)
    assert pairs == [] and issues == [] and rest == [out, into]


def test_too_many_days_apart_is_not_internal():
    pairs, _, _ = find_internal([txn("-100", day=5), txn("100", day=8, account="revolut")], CFG)
    assert pairs == []


def test_same_account_is_not_internal():
    pairs, _, _ = find_internal([txn("-100"), txn("100")], CFG)
    assert pairs == []


def test_only_my_accounts_are_considered():
    cfg = Config(my_accounts=("wise",))
    pairs, _, _ = find_internal([txn("-100"), txn("100", account="friend")], cfg)
    assert pairs == []


def test_stripe_hinted_deposit_is_never_an_internal_transfer():
    out = txn("-500", account="wise")
    deposit = txn("500", account="mercury", description="STRIPE TRANSFER")
    pairs, _, rest = find_internal([out, deposit], CFG)
    assert pairs == [] and rest == [out, deposit]


def test_two_equal_counterparts_go_to_exceptions():
    out = txn("-500", account="wise")
    a = txn("500", account="mercury", day=5)
    b = txn("500", account="revolut", day=5)
    pairs, issues, rest = find_internal([out, a, b], CFG)
    assert pairs == [] and rest == []
    assert sorted(u.txn.account for u in issues) == ["mercury", "revolut", "wise"]
    assert all("2 candidates" in u.reason for u in issues)


def test_two_debits_claiming_one_credit_go_to_exceptions():
    a = txn("-500", account="wise")
    b = txn("-500", account="revolut")
    credit = txn("500", account="mercury")
    pairs, issues, rest = find_internal([a, b, credit], CFG)
    assert pairs == [] and rest == [] and len(issues) == 3


def test_same_currency_pair_needs_the_fee_tolerance_not_the_fx_spread():
    # 1005 against 1000 EUR is a 0.5 percent gap, inside the 1.5 percent FX spread, but
    # both rows are EUR, so only the 1.00 EUR fee tolerance applies.
    out = txn("-1005", account="wise")
    into = txn("1000", account="revolut")
    pairs, issues, rest = find_internal([out, into], CFG)
    assert pairs == [] and issues == [] and rest == [out, into]


def test_same_currency_pair_inside_the_fee_tolerance_is_internal():
    pairs, _, _ = find_internal(
        [txn("-1000.80", account="wise"), txn("1000", account="revolut")], CFG
    )
    assert len(pairs) == 1


# Follow-up to AUD-1: in one currency the EUR values come from two different days' rates.


def test_same_currency_transfer_is_found_even_if_the_rate_moves_between_the_two_days():
    # 5000 USD out on the 5th (rate 1.10) and 5000 USD in on the 6th (rate 1.25). The amounts
    # are equal, so it is one transfer. Only the EUR values differ, because the rate moved.
    out = txn("-5000", day=5, account="wise", currency="USD", eur="-4545.4545")
    into = txn("5000", day=6, account="mercury", currency="USD", eur="4000", source="mercury")
    pairs, issues, rest = find_internal([out, into], CFG)
    assert len(pairs) == 1 and issues == [] and rest == []


def test_same_currency_amounts_that_really_differ_are_still_not_a_transfer():
    # 10 USD apart is about 9 EUR, above the 1.00 EUR fee tolerance.
    out = txn("-5000", day=5, account="wise", currency="USD", eur="-4545.4545")
    into = txn("5010", day=5, account="mercury", currency="USD", eur="4554.5455", source="mercury")
    pairs, _, rest = find_internal([out, into], CFG)
    assert pairs == [] and rest == [out, into]
