"""Settings. Defaults are used when no TOML file is given."""

import tomllib
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path


@dataclass(frozen=True)
class Config:
    fee_tolerance_eur: Decimal = Decimal("1.00")  # largest accepted payout vs deposit gap
    fx_spread_pct: Decimal = Decimal("1.5")  # allowed spread on internal transfers, in percent
    window_days: int = 3  # deposit may arrive 0..N business days after the arrival date
    internal_days: int = 2  # internal transfer legs must be within N calendar days
    my_accounts: tuple[str, ...] = ()  # account names that are mine; empty means all bank files
    hint_words: tuple[str, ...] = ("STRIPE",)  # words that point to a Stripe deposit
    max_rate_age_days: int = 7  # refuse an FX rate older than this many days
    early_days: int = 1  # a deposit may be dated up to N calendar days before the arrival date


INT_KEYS = ("window_days", "internal_days", "early_days", "max_rate_age_days")
DECIMAL_KEYS = ("fee_tolerance_eur", "fx_spread_pct")
LIST_KEYS = ("my_accounts", "hint_words")


def _decimal(value: object) -> Decimal | None:
    """The value as a finite Decimal of 0 or more, or None. TOML true/false are rejected."""
    if isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))  # str() first so 0.1 does not become a float error
    except InvalidOperation:
        return None
    return number if number.is_finite() and number >= 0 else None


def load_config(path: Path | None) -> Config:
    """Read a TOML file over the defaults.

    Unknown keys and wrong values are an error that names the key, so a typo cannot pass
    and a string cannot be split into single letters.
    """
    if path is None:
        return Config()
    with path.open("rb") as f:
        raw = tomllib.load(f)
    unknown = set(raw) - set(Config.__dataclass_fields__)
    if unknown:
        raise ValueError(f"unknown setting(s) in {path}: {', '.join(sorted(unknown))}")
    for key in INT_KEYS:
        if key in raw and (type(raw[key]) is not int or raw[key] < 0):
            raise ValueError(f"{path}: {key} must be a whole number, 0 or more")
    for key in DECIMAL_KEYS:
        if key in raw:
            number = _decimal(raw[key])
            if number is None:
                raise ValueError(f"{path}: {key} must be a number, 0 or more")
            raw[key] = number
    for key in LIST_KEYS:
        if key in raw:
            items = raw[key]
            if not isinstance(items, list) or not all(
                isinstance(i, str) and i.strip() for i in items
            ):
                raise ValueError(
                    f'{path}: {key} must be a list of text values, for example ["STRIPE"]'
                )
            raw[key] = tuple(items)
    return Config(**raw)
