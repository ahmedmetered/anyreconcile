"""Randomized check of what must always hold, whatever the data looks like.

Every payout ends up in exactly one place, and every bank row ends up in exactly one place:
a dropped duplicate, a match, an internal pair, an exception, or the unmatched count.
The seeds are fixed, so a failure can be reproduced by its seed.
"""

import random
from datetime import date, timedelta
from decimal import Decimal

import pytest

from anyreconcile.cli import reconcile
from anyreconcile.config import Config
from anyreconcile.model import Transaction

AMOUNTS = [Decimal(x) for x in ("80", "100", "200", "250", "500", "625", "749.2", "1000", "1100")]
DESCRIPTIONS = ["STRIPE PAYOUT", "STRIPE TRANSFER", "Transfer", "To Mercury", "Client", "Supplier"]
CONFIGS = [Config(), Config(early_days=0), Config(window_days=1), Config(my_accounts=("wise",))]


def a_day() -> date:
    return date(2026, 1, 5) + timedelta(days=random.randint(0, 20))  # inside the fixture rates


def random_data() -> tuple[list[Transaction], list[Transaction]]:
    payouts = [
        Transaction(
            "stripe",
            "stripe",
            f"po_{i}",
            a_day(),
            random.choice(AMOUNTS) * random.choice([1, 1, 1, -1]),
            random.choice(["EUR", "USD", "GBP"]),
            status=random.choice(["paid", "in_transit", "pending"]),
        )
        for i in range(random.randint(0, 8))
    ]
    bank = []
    for _ in range(random.randint(0, 14)):
        account = random.choice(["wise", "revolut", "mercury"])
        bank_id = (
            "" if account == "mercury" or random.random() < 0.2 else f"B{random.randint(0, 14)}"
        )
        row = Transaction(
            account,
            account,
            bank_id,
            a_day(),
            random.choice(AMOUNTS) * random.choice([1, -1]),
            random.choice(["EUR", "USD", "GBP"]),
            random.choice(DESCRIPTIONS),
        )
        bank.append(row)
        if random.random() < 0.1:
            bank.append(row)  # an exact copy: same bank id, or an identical row without one
    return payouts, bank


@pytest.mark.parametrize("seed", range(300))
def test_every_payout_and_every_bank_row_is_accounted_for_once(seed, rates):
    random.seed(seed)
    payouts, bank = random_data()
    cfg = random.choice(CONFIGS)
    result = reconcile(payouts, bank, rates, cfg)

    seen = [m.payout.id for m in result.matched]
    seen += [u.txn.id for u in result.exceptions if u.txn.source == "stripe"]
    assert sorted(seen) == sorted(p.id for p in payouts)

    bank_exceptions = [u for u in result.exceptions if u.txn.source != "stripe"]
    accounted = result.duplicates_dropped + len(result.matched) + 2 * len(result.internal)
    accounted += len(bank_exceptions) + result.unmatched_bank_rows
    assert accounted == len(bank)

    for m in result.matched:
        assert (m.payout.amount > 0) == (m.deposit.amount > 0)
