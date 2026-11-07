"""Tests for the CSV writers."""

import csv
from datetime import date
from decimal import Decimal

from helpers import txn

from anyreconcile.model import Internal, Match, Result, Unmatched
from anyreconcile.report import write_results

FORMULA = '=HYPERLINK("http://x","y")'


def read(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def result(**kwargs):
    base = {"matched": [], "internal": [], "exceptions": [], "duplicates_dropped": 0}
    return Result(unmatched_bank_rows=0, **{**base, **kwargs})


# AUD-5: text from a bank file was written as it came, so a spreadsheet could run it.


def test_aud5_formula_like_text_gets_a_leading_quote(tmp_path):
    row = txn("-5.00", account="@acct", id="+id1", description=FORMULA, source="wise")
    write_results(result(exceptions=[Unmatched(row, "=reason")]), tmp_path)
    (out,) = read(tmp_path / "exceptions.csv")
    assert out["description"] == "'" + FORMULA
    assert (out["row_account"], out["row_id"], out["reason"]) == ("'@acct", "'+id1", "'=reason")


def test_aud5_amounts_and_dates_are_never_changed(tmp_path):
    row = txn("-5.00", description="-minus start", source="wise")
    write_results(result(exceptions=[Unmatched(row, "ok")]), tmp_path)
    (out,) = read(tmp_path / "exceptions.csv")
    assert (out["row_amount"], out["row_eur"], out["row_date"]) == ("-5.00", "-5.00", "2026-01-05")
    assert out["description"] == "'-minus start"  # text starting with a minus is quoted


def test_aud5_matched_and_internal_files_quote_account_and_id(tmp_path):
    a = txn("10.00", account="=a", id="@1", source="stripe")
    b = txn("-10.00", account="-b", id="+2")
    m = Match(a, b, Decimal("0"))
    write_results(result(matched=[m], internal=[Internal(b, a)]), tmp_path)
    (matched,) = read(tmp_path / "matched.csv")
    assert (matched["payout_account"], matched["payout_id"]) == ("'=a", "'@1")
    assert (matched["deposit_account"], matched["deposit_id"]) == ("'-b", "'+2")
    assert matched["deposit_amount"] == "-10.00"
    (internal,) = read(tmp_path / "internal.csv")
    assert (internal["out_account"], internal["in_id"]) == ("'-b", "'@1")


def test_aud5_plain_text_is_unchanged(tmp_path):
    row = txn("1.00", account="wise", id="W-1001", description="STRIPE PAYOUT", source="wise")
    write_results(
        result(exceptions=[Unmatched(row, "no deposit within 3 business days")]), tmp_path
    )
    (out,) = read(tmp_path / "exceptions.csv")
    assert (out["row_id"], out["description"]) == ("W-1001", "STRIPE PAYOUT")
    assert date.fromisoformat(out["row_date"]) == date(2026, 1, 5)


# Follow-up to AUD-5: a leading tab or carriage return can also hide a formula.


def test_aud5_followup_text_starting_with_a_tab_or_carriage_return_is_quoted(tmp_path):
    tab = txn("1.00", description="\t=cmd", source="wise")
    cr = txn("2.00", description="\r=cmd", source="wise")
    write_results(result(exceptions=[Unmatched(tab, "ok"), Unmatched(cr, "ok")]), tmp_path)
    first, second = read(tmp_path / "exceptions.csv")
    assert first["description"] == "'\t=cmd"
    assert second["description"] == "'\r=cmd"
