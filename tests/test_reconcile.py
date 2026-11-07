"""Pipeline-level regression tests for reconcile(). One test per code review finding."""

from datetime import date
from decimal import Decimal

from helpers import txn

from anyreconcile.cli import reconcile
from anyreconcile.config import Config

# Only USD is needed. 1080 USD is exactly 1000 EUR on the day of these tests.
RATES = {"USD": [(date(2026, 2, 3), Decimal("1.08"))]}


def payout():
    """A payout of 1000.00 EUR due on Tuesday 2026-02-03."""
    return txn("1000.00", month=2, day=3, account="stripe", id="po_1", source="stripe")


def bank(amount, account, currency="EUR", description=""):
    return txn(
        amount,
        month=2,
        day=3,
        account=account,
        currency=currency,
        description=description,
        source=account,
    )


# AUD-1: internal transfers were found before payouts, and on amount and date alone.


def test_aud1_a_payout_deposit_is_not_taken_by_an_unrelated_payment_of_a_similar_amount():
    rows = [
        bank("1000.00", "revolut", description="ACME PAYMENTS LTD"),
        bank("-1005.00", "wise", description="Supplier invoice 77"),
    ]
    result = reconcile([payout()], rows, RATES, Config())
    assert [(m.payout.id, m.deposit.account) for m in result.matched] == [("po_1", "revolut")]
    assert result.internal == []
    assert result.exceptions == []


def test_aud1_b_payout_matches_first_then_the_rest_pairs_as_internal():
    rows = [
        bank("1000.00", "revolut", description="Incoming payment"),
        bank("1080.00", "mercury", currency="USD", description="Transfer from Wise"),
        bank("-1000.00", "wise", description="To Mercury"),
    ]
    result = reconcile([payout()], rows, RATES, Config())
    assert [(m.payout.id, m.deposit.account) for m in result.matched] == [("po_1", "revolut")]
    assert [(i.out.account, i.into.account) for i in result.internal] == [("wise", "mercury")]
    assert result.exceptions == []


# AUD-2: a leftover STRIPE deposit was only counted, never listed.


def test_aud2_leftover_stripe_deposit_goes_to_exceptions_and_is_not_counted_as_unmatched():
    rows = [bank("750.00", "revolut", description="STRIPE PAYOUT")]
    result = reconcile([], rows, {}, Config())
    assert [(u.txn.account, u.reason) for u in result.exceptions] == [
        ("revolut", "looks like a Stripe deposit, but no payout matches")
    ]
    assert result.unmatched_bank_rows == 0
