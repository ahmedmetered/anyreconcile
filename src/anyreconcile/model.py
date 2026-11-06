"""Shared data types. Every adapter produces Transaction; every stage returns the result types."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class Transaction:
    """One Stripe payout or one bank row.

    amount and currency are exactly what the source file said. eur is filled in by the
    fx step and never replaces them. id is the source's own id, or "" when it has none.
    Positive amount means money in, negative means money out.
    """

    source: str  # "stripe", "wise", "revolut" or "mercury"
    account: str  # name of the account, taken from the file name
    id: str
    date: date
    amount: Decimal
    currency: str
    description: str = ""
    reference: str = ""
    eur: Decimal | None = None


@dataclass(frozen=True)
class Match:
    payout: Transaction
    deposit: Transaction
    diff_eur: Decimal  # payout minus deposit, in EUR (the bank fee when positive)


@dataclass(frozen=True)
class Internal:
    out: Transaction
    into: Transaction


@dataclass(frozen=True)
class Unmatched:
    """A row that needs a human, with a plain-words reason."""

    txn: Transaction
    reason: str
