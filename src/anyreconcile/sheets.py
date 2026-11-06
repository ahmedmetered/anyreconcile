"""Optional: copy exceptions.csv into a Google Sheet.

Needs `pip install anyreconcile[sheets]` and a Google service account JSON key. Share the
spreadsheet with the service account's e-mail address first. The core tool never imports
this module unless the Sheets flags are used.
"""

import csv
from pathlib import Path

TAB = "exceptions"


def push_exceptions(csv_path: Path, credentials: Path, spreadsheet: str) -> int:
    """Replace the "exceptions" tab with the CSV contents. Returns the number of data rows."""
    try:
        import gspread
    except ImportError as e:
        raise RuntimeError("Google Sheets support needs: pip install anyreconcile[sheets]") from e

    with csv_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    book = gspread.service_account(filename=str(credentials)).open(spreadsheet)
    try:
        tab = book.worksheet(TAB)
    except gspread.WorksheetNotFound:
        tab = book.add_worksheet(TAB, rows=len(rows), cols=len(rows[0]))
    tab.clear()
    tab.update(values=rows, range_name="A1")
    return len(rows) - 1
