"""Currency conversion with ECB daily reference rates (eurofxref-hist.csv).

The ECB quotes units of currency per 1 EUR, so EUR = amount / rate. The ECB publishes no
rate on weekends or TARGET holidays, so we use the most recent earlier rate.
"""

import csv
import io
import urllib.request
import zipfile
from bisect import bisect_right
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

from anyreconcile.model import Transaction

ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip"

# currency -> [(day, rate), ...] sorted oldest first
Rates = dict[str, list[tuple[date, Decimal]]]


def load_rates(path: Path) -> Rates:
    """Read an eurofxref-hist.csv file. "N/A" cells (no rate that day) are skipped."""
    rates: Rates = {}
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            day = date.fromisoformat(row["Date"])
            for currency, text in row.items():
                # The real file ends every line with a comma, which makes an empty column name.
                if currency == "Date" or not currency or not text or text.strip() == "N/A":
                    continue
                rates.setdefault(currency, []).append((day, Decimal(text)))
    for series in rates.values():
        series.sort()
    return rates


def rate(rates: Rates, currency: str, day: date, max_age_days: int = 7) -> Decimal:
    """Units of currency per 1 EUR on day, or on the closest earlier day that has a rate.

    A rate more than max_age_days old is refused, so a stale rates file cannot pass silently.
    """
    if currency == "EUR":
        return Decimal(1)
    series = rates.get(currency)
    if not series:
        raise ValueError(f"no ECB rates for currency {currency}")
    i = bisect_right(series, day, key=lambda point: point[0])
    if i == 0:
        raise ValueError(f"no {currency} rate on or before {day}")
    rate_day, value = series[i - 1]
    if (day - rate_day).days > max_age_days:
        raise ValueError(
            f"no {currency} rate within {max_age_days} days before {day}. Run --download-rates"
        )
    return value


def to_eur(
    amount: Decimal, currency: str, day: date, rates: Rates, max_age_days: int = 7
) -> Decimal:
    """Convert without rounding. Rounding happens only when we write output."""
    return amount / rate(rates, currency, day, max_age_days)


def with_eur(txns: list[Transaction], rates: Rates, max_age_days: int = 7) -> list[Transaction]:
    """Fill in eur on each row, using the rate for the row's own date."""
    return [replace(t, eur=to_eur(t.amount, t.currency, t.date, rates, max_age_days)) for t in txns]


def download_rates(dest: Path) -> None:
    """Fetch the full ECB history (a zip with one csv inside) and save the csv at dest."""
    with urllib.request.urlopen(ECB_URL, timeout=30) as response:
        data = response.read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        dest.write_bytes(z.read("eurofxref-hist.csv"))
