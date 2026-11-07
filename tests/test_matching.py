from datetime import date
from decimal import Decimal

from helpers import txn

from anyreconcile.config import Config
from anyreconcile.matching import add_business_days, match_payouts

CFG = Config()  # tolerance 1.00 EUR, spread 1.5 percent, window 3 business days


def payout(amount, day=5, currency="EUR", id="po_1"):
    return txn(amount, day=day, account="stripe", currency=currency, id=id, source="stripe")


def deposit(amount, day=5, currency="EUR", description="STRIPE PAYOUT", id="D1", account="wise"):
    return txn(amount, day=day, currency=currency, description=description, id=id, account=account)


def run(payouts, deposits, rates, cfg=CFG):
    return match_payouts(payouts, deposits, cfg, rates)


def test_business_days_skip_weekends():
    assert add_business_days(date(2026, 1, 9), 1) == date(2026, 1, 12)  # Friday to Monday
    assert add_business_days(date(2026, 1, 10), 1) == date(2026, 1, 12)  # Saturday to Monday
    assert add_business_days(date(2026, 1, 21), 3) == date(2026, 1, 26)  # Wed to next Mon
    assert add_business_days(date(2026, 1, 5), 0) == date(2026, 1, 5)


def test_exact_match(rates):
    matches, issues = run([payout("500")], [deposit("500")], rates)
    assert len(matches) == 1 and issues == [] and matches[0].diff_eur == 0


def test_fee_inside_tolerance_matches_and_records_the_fee(rates):
    matches, _ = run([payout("750", day=6)], [deposit("749.20", day=7)], rates)
    assert matches[0].diff_eur == Decimal("0.80")


def test_fee_outside_tolerance_is_an_exception_with_the_amount(rates):
    matches, issues = run([payout("300", day=7)], [deposit("295.80", day=8)], rates)
    assert matches == []
    assert issues[0].reason == "amount differs by 4.20 EUR, above tolerance"


def test_weekend_gap_is_inside_the_window(rates):
    # Friday arrival, Monday deposit is one business day.
    matches, _ = run([payout("420", day=9)], [deposit("420", day=12)], rates)
    assert len(matches) == 1


def test_window_edge_is_three_business_days_and_one_more_is_too_late(rates):
    on_edge, _ = run([payout("310", day=21)], [deposit("310", day=26)], rates)
    too_late, issues = run([payout("310", day=21)], [deposit("310", day=27)], rates)
    assert len(on_edge) == 1 and too_late == []
    assert issues[0].reason == "no deposit within 3 business days"


def test_deposit_more_than_early_days_before_arrival_is_not_a_candidate(rates):
    # One day early is allowed since AUD-4 (early_days = 1). Two days early is not.
    _, issues = run([payout("100", day=6)], [deposit("100", day=4)], rates)
    assert len(issues) == 1


def test_same_currency_usd_matches_even_when_the_rate_changes_between_days(rates):
    # Rate is 1.10 on the 15th and 1.25 from the 16th. Both sides use the payout date.
    p = payout("1100", day=15, currency="USD")
    d = deposit("1100", day=16, currency="USD")
    matches, _ = run([p], [d], rates)
    assert matches[0].diff_eur == 0


def test_cross_currency_uses_the_fx_spread_tolerance(rates):
    # 550 USD is 500 EUR on the 14th. 497 EUR is 3 off: over 1.00 but inside 1.00 + 7.50.
    matches, _ = run([payout("550", day=14, currency="USD")], [deposit("497", day=15)], rates)
    assert matches[0].diff_eur == Decimal("3")


def test_negative_payout_matches_a_bank_debit(rates):
    matches, _ = run([payout("-80", day=15)], [deposit("-80", day=16)], rates)
    assert len(matches) == 1


def test_negative_payout_does_not_match_a_credit(rates):
    matches, _ = run([payout("-80", day=15)], [deposit("80", day=16)], rates)
    assert matches == []


def test_gbp_gap_is_converted_and_not_rounded_in_the_calculation(rates):
    # 640.00 GBP is 800 EUR, 639.50 GBP is 799.375 EUR, gap 0.625 EUR.
    matches, _ = run(
        [payout("640", day=19, currency="GBP")], [deposit("639.50", day=20, currency="GBP")], rates
    )
    assert matches[0].diff_eur == Decimal("0.625")


def test_two_equal_deposits_for_one_payout_go_to_exceptions(rates):
    _, issues = run([payout("200")], [deposit("200", id="A"), deposit("200", id="B")], rates)
    assert issues[0].reason == "2 candidates with the same amount"


def test_two_equal_payouts_both_go_to_exceptions(rates):
    payouts = [payout("200", id="po_1"), payout("200", id="po_2")]
    matches, issues = run(payouts, [deposit("200", id="A"), deposit("200", id="B")], rates)
    assert matches == [] and [u.txn.id for u in issues] == ["po_1", "po_2"]


def test_two_payouts_for_one_deposit_both_go_to_exceptions(rates):
    payouts = [payout("200", id="po_1"), payout("200", id="po_2")]
    matches, issues = run(payouts, [deposit("200")], rates)
    assert matches == [] and issues[0].reason == "2 payouts fit the same deposit"


def test_stripe_hint_breaks_a_tie_between_equal_amounts(rates):
    d_hint = deposit("200", id="A")
    d_other = deposit("200", id="B", description="Client invoice")
    matches, _ = run([payout("200")], [d_other, d_hint], rates)
    assert matches[0].deposit.id == "A"


def test_no_deposit_at_all(rates):
    _, issues = run([payout("900", day=28)], [], rates)
    assert issues[0].reason == "no deposit within 3 business days"


def test_far_off_amount_in_window_is_not_reported_as_a_near_miss(rates):
    _, issues = run([payout("250", day=23)], [deposit("310", day=26)], rates)
    assert issues[0].reason == "no deposit within 3 business days"


def test_tolerance_comes_from_config(rates):
    cfg = Config(fee_tolerance_eur=Decimal("5"))
    matches, _ = run([payout("300", day=7)], [deposit("295.80", day=8)], rates, cfg)
    assert len(matches) == 1


def test_same_currency_deposit_beats_a_cross_currency_one_with_the_same_gap(rates):
    # 1100 USD is 1000 EUR on the 5th (rate 1.10), so both deposits fit equally on amount.
    # A EUR payout normally lands in a EUR account, so the EUR deposit wins instead of a tie.
    eur = deposit("1000", id="EUR1")
    usd = deposit("1100", currency="USD", id="USD1", account="mercury")
    matches, issues = run([payout("1000")], [usd, eur], rates)
    assert issues == [] and matches[0].deposit.id == "EUR1"


def test_aud4_closest_date_wins_when_hint_gap_and_currency_are_equal(rates):
    # A deposit on the arrival date beats one a day early. Hint and gap still come first.
    early = deposit("300", day=6, id="EARLY")
    on_time = deposit("300", day=7, id="ONTIME")
    matches, _ = run([payout("300", day=7)], [early, on_time], rates)
    assert matches[0].deposit.id == "ONTIME"


def test_aud4_hint_still_beats_a_closer_date(rates):
    early_hint = deposit("300", day=6, id="HINT")
    on_time = deposit("300", day=7, id="PLAIN", description="Client payment")
    matches, _ = run([payout("300", day=7)], [on_time, early_hint], rates)
    assert matches[0].deposit.id == "HINT"


def test_aud6_unpaid_payouts_say_so_and_other_statuses_keep_the_usual_reason(rates):
    def reason(status):
        p = txn("50", day=7, account="stripe", id="po_1", source="stripe", status=status)
        return run([p], [], rates)[1][0].reason

    assert reason("in_transit") == "still in transit when the export was made"
    assert reason("Pending") == "still in transit when the export was made"
    assert reason("paid") == "no deposit within 3 business days"
    assert reason("") == "no deposit within 3 business days"


def test_aud6_a_near_miss_deposit_is_still_reported_for_an_in_transit_payout(rates):
    p = txn("300", day=7, account="stripe", id="po_1", source="stripe", status="in_transit")
    _, issues = run([p], [deposit("295.80", day=8)], rates)
    assert issues[0].reason == "amount differs by 4.20 EUR, above tolerance"


def test_a_zero_amount_payout_matches_nothing(rates):
    # Zero is neither money in nor money out. It used to line up with any debit, such as a
    # 0.50 bank fee, and with zero rows.
    fee = deposit("-0.50", description="Bank fee")
    zero_row = deposit("0", id="Z")
    matches, issues = run([payout("0")], [fee, zero_row], rates)
    assert matches == []
    assert issues[0].reason == "no deposit within 3 business days"
