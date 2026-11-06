from datetime import date
from decimal import Decimal

import pytest

from anyreconcile.adapters import read_bank, read_stripe


def write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_stripe(tmp_path):
    p = write(
        tmp_path,
        "payouts.csv",
        "id,Arrival Date,Amount,Currency,Description\n"
        "po_1,2026-01-05,500.00,eur,STRIPE PAYOUT\n"
        "po_2,2026-01-06,-80.00,eur,reversal\n",
    )
    a, b = read_stripe(p)
    assert (a.source, a.account, a.id, a.date) == ("stripe", "stripe", "po_1", date(2026, 1, 5))
    assert (a.amount, a.currency) == (Decimal("500.00"), "EUR")  # currency upper-cased
    assert b.amount == Decimal("-80.00")


def test_wise_is_detected_and_account_comes_from_file_name(tmp_path):
    p = write(
        tmp_path,
        "wise_eur.csv",
        "TransferWise ID,Date,Amount,Currency,Description,Payment Reference,Running Balance\n"
        'W-1,05-01-2026,"1,234.50",EUR,STRIPE PAYOUT,po_1,10.00\n',
    )
    (t,) = read_bank(p)
    assert (t.source, t.account, t.id) == ("wise", "wise_eur", "W-1")
    assert t.date == date(2026, 1, 5)  # DD-MM-YYYY
    assert t.amount == Decimal("1234.50")  # thousands comma removed
    assert t.reference == "po_1"


def test_revolut_timestamp_and_negative_amount(tmp_path):
    p = write(
        tmp_path,
        "revolut.csv",
        "ID,Date completed (UTC),Description,Reference,Amount,Fee,Payment currency\n"
        "R-1,2026-01-20 09:12:33,Coffee,,-62.30,0.00,GBP\n",
    )
    (t,) = read_bank(p)
    assert t.source == "revolut"
    assert (t.date, t.amount, t.currency) == (date(2026, 1, 20), Decimal("-62.30"), "GBP")
    assert t.reference == ""


def test_mercury_has_no_id_fixed_usd_and_skips_pending(tmp_path):
    p = write(
        tmp_path,
        "mercury.csv",
        "Date,Description,Amount,Status\n"
        "01-09-2026,STRIPE TRANSFER,1100.00,Sent\n"
        "01-10-2026,Not yet,5.00,Pending\n",
    )
    (t,) = read_bank(p)
    assert (t.source, t.id, t.currency, t.date) == ("mercury", "", "USD", date(2026, 1, 9))


def test_utf8_bom_is_accepted(tmp_path):
    p = tmp_path / "mercury.csv"
    p.write_bytes(b"\xef\xbb\xbfDate,Description,Amount,Status\n01-09-2026,x,1.00,Sent\n")
    assert len(read_bank(p)) == 1


def test_unknown_header_is_rejected_with_the_header_shown(tmp_path):
    p = write(tmp_path, "other.csv", "when,what,how much\n1,2,3\n")
    with pytest.raises(ValueError, match="other.csv.*cannot tell"):
        read_bank(p)


def test_missing_stripe_column_names_it(tmp_path):
    p = write(tmp_path, "p.csv", "id,Amount,Currency,Description\npo_1,1,EUR,x\n")
    with pytest.raises(ValueError, match="Arrival Date"):
        read_stripe(p)


def test_bad_value_reports_the_line(tmp_path):
    p = write(
        tmp_path,
        "mercury.csv",
        "Date,Description,Amount,Status\n01-09-2026,ok,1.00,Sent\n01-10-2026,bad,abc,Sent\n",
    )
    with pytest.raises(ValueError, match=r"mercury.csv line 3"):
        read_bank(p)
