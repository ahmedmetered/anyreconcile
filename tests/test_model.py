from datetime import date
from decimal import Decimal

import pytest

from anyreconcile.model import Transaction


def test_transaction_is_frozen_and_keeps_original_amount():
    t = Transaction("wise", "wise_usd", "W1", date(2026, 1, 5), Decimal("100.00"), "USD")
    assert t.eur is None
    with pytest.raises(AttributeError):
        t.amount = Decimal("1")  # type: ignore[misc]
