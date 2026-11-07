"""Settings. Defaults are used when no TOML file is given."""

import tomllib
from dataclasses import dataclass
from decimal import Decimal
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


def load_config(path: Path | None) -> Config:
    """Read a TOML file over the defaults. Unknown keys are an error, so typos do not pass."""
    if path is None:
        return Config()
    with path.open("rb") as f:
        raw = tomllib.load(f)
    unknown = set(raw) - set(Config.__dataclass_fields__)
    if unknown:
        raise ValueError(f"unknown setting(s) in {path}: {', '.join(sorted(unknown))}")
    for key in ("fee_tolerance_eur", "fx_spread_pct"):
        if key in raw:
            raw[key] = Decimal(str(raw[key]))  # str() first so 0.1 does not become a float error
    for key in ("my_accounts", "hint_words"):
        if key in raw:
            raw[key] = tuple(raw[key])
    return Config(**raw)
