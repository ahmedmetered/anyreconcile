"""Read each source's CSV export into Transaction rows.

Each source is one Spec, so fixing a header is a one-line change. How far each column
list could be checked (researched 2026-11-07):

- Stripe: OFFICIAL. The `payouts.itemized` report (Stripe Reporting API, and the Dashboard
  export with the same column names) has these columns, from Stripe's report schema and
  https://docs.stripe.com/reports/report-types/balance : payout_id, payout_expected_arrival_date,
  net, currency, description, payout_status. The export must include them. gross, fee and net
  are in major units (12.50 means 12.50). net is the effect on your Stripe balance, so a payout
  to your bank is NEGATIVE (https://docs.stripe.com/api/balance_transactions/object). We flip
  the sign so that, like the bank rows, positive means money arriving. Payouts whose
  payout_status is failed or canceled never reach the bank, so they are skipped. NOT CONFIRMED:
  the date text inside the CSV. Two third-party descriptions type the column as a datetime, so
  we accept YYYY-MM-DD with or without a time after it (after a space or a T).
- Wise: NOT OFFICIAL. Wise's help pages and API docs do not list CSV columns. The header comes
  from a user's mailing-list post (2023) and the ledger-autosync Wise plugin: "TransferWise ID",
  Date, Amount, Currency, Description, "Payment Reference" and others. A third-party page says
  newer exports add "Date Time" and more columns, which does not affect us. Date is day first
  (DD-MM-YYYY, from the plugin's parser). One CSV covers one currency balance.
- Revolut Business: NOT OFFICIAL. Revolut's help pages say CSV statements exist and can carry
  UTC and local times, and list no columns. Real header rows from two GitHub issues
  (revolut-to-mt940 #2 and #3) and a third-party format list show these variants, all with
  ID, Date completed (UTC), Description, Reference, Payment currency, Amount, Fee. Some
  variants also have a "State" column whose values we could not confirm, so it is ignored.
  The Fee column is ignored. Date text format NOT CONFIRMED (we accept YYYY-MM-DD with or
  without a time).
- Mercury: NOT OFFICIAL. Mercury's help pages say a CSV or XLSX export exists on the
  Transactions page and list no columns. The header comes from the beanhub-extract Mercury
  extractor, which accepts a file only if its header matches exactly: "Date (UTC)",
  Description, Amount, Status, "Source Account", "Bank Description", Reference, Note,
  "Last Four Digits", "Name On Card", Category, "GL Code", Timestamp, "Original Currency".
  Its parser reads dates as MM-DD-YYYY. There is no id column. We treat every Mercury row as
  USD (Mercury accounts are USD). The values of Status NOT CONFIRMED, so we skip rows whose
  status is pending, cancelled or failed.

Amounts may contain thousands commas ("1,234.50"). A comma as decimal mark is not supported.
The account name of every row is the file name without ".csv".
"""

import csv
import re
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
    negate: bool = False  # the file shows the other side of the money (Stripe net)

    def required(self) -> list[str]:
        """Headers that must exist. This is also how we recognise a file."""
        wanted = [self.date, self.amount, self.description, self.currency, self.id, self.status]
        return [h for h in wanted if h]


STRIPE = Spec(
    "stripe",
    id="payout_id",
    date="payout_expected_arrival_date",
    date_format="%Y-%m-%d",
    amount="net",
    currency="currency",
    description="description",
    status="payout_status",
    skip_status=("failed", "canceled"),
    negate=True,
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
    date="Date (UTC)",
    date_format="%m-%d-%Y",
    amount="Amount",
    description="Description",
    reference="Reference",
    fixed_currency="USD",
    status="Status",
    skip_status=("pending", "cancelled", "failed"),
)

BANK_SPECS = (WISE, REVOLUT, MERCURY)


def parse_amount(text: str) -> Decimal:
    return Decimal(text.replace(",", "").strip())


def parse_date(text: str, fmt: str) -> date:
    # Keep only the date part, so "2026-01-05 09:12:33" and "2026-01-05T09:12:33Z" both work.
    return datetime.strptime(re.split("[ T]", text.strip())[0], fmt).date()


def _row(spec: Spec, account: str, row: dict[str, str]) -> Transaction | None:
    if spec.status and row[spec.status].strip().lower() in spec.skip_status:
        return None
    amount = parse_amount(row[spec.amount])
    return Transaction(
        source=spec.source,
        account=account,
        id=row[spec.id].strip() if spec.id else "",
        date=parse_date(row[spec.date], spec.date_format),
        amount=-amount if spec.negate else amount,
        currency=(row[spec.currency] if spec.currency else spec.fixed_currency).strip().upper(),
        description=row[spec.description].strip(),
        reference=(row.get(spec.reference) or "").strip() if spec.reference else "",
        status=row[spec.status].strip() if spec.status else "",
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
