"""Read each source's CSV export into Transaction rows.

IMPORTANT: none of the column names below could be confirmed from official documentation,
and no real export was available when this was written. They are the best layouts found
in public sources. Each source is one Spec, so fixing a wrong header is a one-line change.

Assumptions per source:
- Stripe: Dashboard Payouts export with `id`, `Arrival Date`, `Amount`, `Currency`,
  `Description`. Amounts in major units (12.50 = 12.50). Dates as YYYY-MM-DD.
- Wise: legacy statement layout (`TransferWise ID`, `Date`, `Amount`, `Currency`,
  `Description`, `Payment Reference`). Dates as DD-MM-YYYY. Newer Wise exports may differ.
- Revolut Business: `ID`, `Date completed (UTC)`, `Description`, `Reference`, `Amount`,
  `Payment currency`. The Fee column is ignored. Timestamps like "2026-01-05 09:12:33".
- Mercury: `Date`, `Description`, `Amount`, `Status`. No id and no currency column (accounts
  are USD). Dates as MM-DD-YYYY, which is ambiguous with DD-MM-YYYY for days up to 12.
  Rows whose Status is pending, cancelled or failed are skipped.

Amounts may contain thousands commas ("1,234.50"). A comma as decimal mark is not supported.
The account name of every row is the file name without ".csv".
"""

import csv
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from anyreconcile.model import Transaction


@dataclass(frozen=True)
class Spec:
    """Which header holds which field. None means the file has no such column."""

    source: str
    date: str
    date_format: str
    amount: str
    description: str
    currency: str | None = None
    fixed_currency: str = ""  # used when the file has no currency column
    id: str | None = None
    reference: str | None = None  # optional: the file may lack it
    status: str | None = None
    skip_status: tuple[str, ...] = ()  # lowercase status values to skip

    def required(self) -> list[str]:
        """Headers that must exist. This is also how we recognise a file."""
        wanted = [self.date, self.amount, self.description, self.currency, self.id, self.status]
        return [h for h in wanted if h]


STRIPE = Spec(
    "stripe",
    id="id",
    date="Arrival Date",
    date_format="%Y-%m-%d",
    amount="Amount",
    currency="Currency",
    description="Description",
)
WISE = Spec(
    "wise",
    id="TransferWise ID",
    date="Date",
    date_format="%d-%m-%Y",
    amount="Amount",
    currency="Currency",
    description="Description",
    reference="Payment Reference",
)
REVOLUT = Spec(
    "revolut",
    id="ID",
    date="Date completed (UTC)",
    date_format="%Y-%m-%d",
    amount="Amount",
    currency="Payment currency",
    description="Description",
    reference="Reference",
)
MERCURY = Spec(
    "mercury",
    date="Date",
    date_format="%m-%d-%Y",
    amount="Amount",
    description="Description",
    fixed_currency="USD",
    status="Status",
    skip_status=("pending", "cancelled", "failed"),
)

BANK_SPECS = (WISE, REVOLUT, MERCURY)


def parse_amount(text: str) -> Decimal:
    return Decimal(text.replace(",", "").strip())


def parse_date(text: str, fmt: str) -> date:
    # Keep only the date part, so "2026-01-05 09:12:33" works with "%Y-%m-%d".
    return datetime.strptime(text.strip().split(" ")[0], fmt).date()


def _row(spec: Spec, account: str, row: dict[str, str]) -> Transaction | None:
    if spec.status and row[spec.status].strip().lower() in spec.skip_status:
        return None
    return Transaction(
        source=spec.source,
        account=account,
        id=row[spec.id].strip() if spec.id else "",
        date=parse_date(row[spec.date], spec.date_format),
        amount=parse_amount(row[spec.amount]),
        currency=(row[spec.currency] if spec.currency else spec.fixed_currency).strip().upper(),
        description=row[spec.description].strip(),
        reference=(row.get(spec.reference) or "").strip() if spec.reference else "",
    )


def read_file(path: Path, spec: Spec) -> list[Transaction]:
    """Read one file with a known spec. Errors name the file and the line."""
    account = "stripe" if spec.source == "stripe" else path.stem
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        missing = [h for h in spec.required() if h not in header]
        if missing:
            raise ValueError(
                f"{path.name}: expected {spec.source} column(s) {missing} but the header is "
                f"{header}. Change the column names in adapters.py if the export differs."
            )
        out = []
        for line, row in enumerate(reader, start=2):  # line 1 is the header
            try:
                txn = _row(spec, account, row)
            except (ValueError, InvalidOperation, KeyError) as e:
                raise ValueError(f"{path.name} line {line}: bad value ({e!r})") from e
            if txn:
                out.append(txn)
    return out


def detect(header: list[str]) -> Spec:
    """Pick the bank spec whose required headers are all present in header."""
    found = [s for s in BANK_SPECS if all(h in header for h in s.required())]
    if len(found) != 1:
        names = [s.source for s in found] or "none"
        raise ValueError(f"cannot tell which bank this file is from (matches: {names})")
    return found[0]


def read_bank(path: Path) -> list[Transaction]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        header = next(csv.reader(f), [])
    try:
        spec = detect(header)
    except ValueError as e:
        raise ValueError(f"{path.name}: {e}. Header was {header}") from e
    return read_file(path, spec)


def read_stripe(path: Path) -> list[Transaction]:
    return read_file(path, STRIPE)
