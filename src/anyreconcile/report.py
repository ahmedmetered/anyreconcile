"""Write matched.csv, internal.csv and exceptions.csv, and build the terminal summary.

Rounding to cents happens here and nowhere else. Original amounts are written exactly as
read, next to the EUR value.
"""

import csv
from decimal import Decimal
from pathlib import Path

from anyreconcile.model import Result, Transaction, round2


def _safe(text: str) -> str:
    """Prefix a quote to text a spreadsheet would run as a formula (starts with = + - or @)."""
    return "'" + text if text.startswith(("=", "+", "-", "@")) else text


def _side(prefix: str, t: Transaction) -> dict[str, str]:
    assert t.eur is not None
    return {
        f"{prefix}_account": _safe(t.account),
        f"{prefix}_id": _safe(t.id),
        f"{prefix}_date": t.date.isoformat(),
        f"{prefix}_amount": format(t.amount, "f"),
        f"{prefix}_currency": t.currency,
        f"{prefix}_eur": str(round2(t.eur)),
    }


def _write(path: Path, rows: list[dict[str, str]], columns: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _columns(*prefixes: str) -> list[str]:
    parts = ("account", "id", "date", "amount", "currency", "eur")
    return [f"{p}_{part}" for p in prefixes for part in parts]


def write_results(result: Result, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    matched = [
        {
            **_side("payout", m.payout),
            **_side("deposit", m.deposit),
            "diff_eur": str(round2(m.diff_eur)),
        }
        for m in result.matched
    ]
    _write(out_dir / "matched.csv", matched, _columns("payout", "deposit") + ["diff_eur"])

    internal = [{**_side("out", i.out), **_side("in", i.into)} for i in result.internal]
    _write(out_dir / "internal.csv", internal, _columns("out", "in"))

    exceptions = []
    for u in result.exceptions:
        side = _side("row", u.txn)
        exceptions.append(
            {
                "source": u.txn.source,
                **side,
                "description": _safe(u.txn.description),
                "reason": _safe(u.reason),
            }
        )
    columns = ["source"] + _columns("row") + ["description", "reason"]
    _write(out_dir / "exceptions.csv", exceptions, columns)


def summary(result: Result) -> dict[str, str]:
    """Counts and totals for the terminal. Same numbers the tests check."""
    payout_exceptions = [u for u in result.exceptions if u.txn.source == "stripe"]
    payout_eur = sum((m.payout.eur or Decimal(0) for m in result.matched), Decimal(0))
    fees = sum((m.diff_eur for m in result.matched), Decimal(0))
    return {
        "payouts": str(len(result.matched) + len(payout_exceptions)),
        "matched": str(len(result.matched)),
        "payout_exceptions": str(len(payout_exceptions)),
        "bank_exceptions": str(len(result.exceptions) - len(payout_exceptions)),
        "internal_transfers": str(len(result.internal)),
        "duplicates_dropped": str(result.duplicates_dropped),
        "unmatched_bank_rows": str(result.unmatched_bank_rows),
        "matched_payout_eur": str(round2(payout_eur)),
        "bank_fees_eur": str(round2(fees)),
    }
