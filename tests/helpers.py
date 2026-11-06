"""Small builders so tests read as a table of rows."""

from datetime import date
from decimal import Decimal

from anyreconcile.model import Transaction


def txn(
    amount: str,
    *,
    day: int = 5,
    account: str = "wise",
    currency: str = "EUR",
    eur: str | None = None,
    id: str = "",
    description: str = "",
    reference: str = "",
    source: str = "wise",
) -> Transaction:
    """A row in January 2026. eur defaults to the amount when the currency is EUR."""
    if eur is None and currency == "EUR":
        eur = amount
    return Transaction(
        source=source,
        account=account,
        id=id,
        date=date(2026, 1, day),
        amount=Decimal(amount),
        currency=currency,
        description=description,
        reference=reference,
        eur=Decimal(eur) if eur is not None else None,
    )
