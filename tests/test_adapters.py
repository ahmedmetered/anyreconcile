from datetime import date
from decimal import Decimal

import pytest

from anyreconcile.adapters import read_bank, read_stripe

STRIPE_HEADER = "payout_id,payout_expected_arrival_date,net,currency,description,payout_status\n"


def write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_stripe_net_is_flipped_so_positive_means_money_to_the_bank(tmp_path):
    p = write(
        tmp_path,
        "payouts.csv",
        STRIPE_HEADER
        + "po_1,2026-01-05,-500.00,eur,STRIPE PAYOUT,paid\n"
        + "po_2,2026-01-06,80.00,eur,reversal,paid\n",
    )
    a, b = read_stripe(p)
    assert (a.source, a.account, a.id, a.date) == ("stripe", "stripe", "po_1", date(2026, 1, 5))
    assert (a.amount, a.currency) == (Decimal("500.00"), "EUR")  # sign flipped, upper-cased
    assert b.amount == Decimal("-80.00")  # a positive net (money back to Stripe) is a bank debit


def test_stripe_failed_and_canceled_payouts_are_skipped(tmp_path):
    p = write(
        tmp_path,
        "payouts.csv",
        STRIPE_HEADER
        + "po_1,2026-01-05,-1.00,eur,x,paid\n"
        + "po_2,2026-01-05,-2.00,eur,x,failed\n"
        + "po_3,2026-01-05,-3.00,eur,x,canceled\n"
        + "po_4,2026-01-05,-4.00,eur,x,in_transit\n",
    )
    assert [t.id for t in read_stripe(p)] == ["po_1", "po_4"]


@pytest.mark.parametrize("text", ["2026-01-05", "2026-01-05 00:00:00", "2026-01-05T00:00:00Z"])
def test_stripe_date_with_or_without_a_time_part_is_accepted(tmp_path, text):
    row = f"po_1,{text},-1.00,eur,x,paid" + chr(10)
    p = write(tmp_path, "payouts.csv", STRIPE_HEADER + row)
    assert read_stripe(p)[0].date == date(2026, 1, 5)


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
        "Date (UTC),Description,Amount,Status,Reference\n"
        "01-09-2026,STRIPE TRANSFER,1100.00,Sent,ref1\n"
        "01-10-2026,Not yet,5.00,Pending,\n",
    )
    (t,) = read_bank(p)
    assert (t.source, t.id, t.currency, t.date) == ("mercury", "", "USD", date(2026, 1, 9))
    assert t.reference == "ref1"


def test_utf8_bom_is_accepted(tmp_path):
    p = tmp_path / "mercury.csv"
    p.write_bytes(b"\xef\xbb\xbfDate (UTC),Description,Amount,Status\n01-09-2026,x,1.00,Sent\n")
    assert len(read_bank(p)) == 1


def test_unknown_header_is_rejected_with_the_header_shown(tmp_path):
    p = write(tmp_path, "other.csv", "when,what,how much\n1,2,3\n")
    with pytest.raises(ValueError, match="other.csv.*cannot tell"):
        read_bank(p)


def test_missing_stripe_column_names_it(tmp_path):
    p = write(
        tmp_path, "p.csv", "payout_id,net,currency,description,payout_status\npo_1,1,eur,x,paid\n"
    )
    with pytest.raises(ValueError, match="payout_expected_arrival_date"):
        read_stripe(p)


def test_bad_value_reports_the_line(tmp_path):
    p = write(
        tmp_path,
        "mercury.csv",
        "Date (UTC),Description,Amount,Status\n01-09-2026,ok,1.00,Sent\n01-10-2026,bad,abc,Sent\n",
    )
    with pytest.raises(ValueError, match=r"mercury.csv line 3"):
        read_bank(p)


def test_status_is_kept_on_the_transaction(tmp_path):
    p = write(tmp_path, "payouts.csv", STRIPE_HEADER + "po_1,2026-01-05,-1.00,eur,x,in_transit\n")
    assert read_stripe(p)[0].status == "in_transit"
    m = write(
        tmp_path, "mercury.csv", "Date (UTC),Description,Amount,Status\n01-09-2026,x,1.00,Sent\n"
    )
    assert read_bank(m)[0].status == "Sent"
    w = write(
        tmp_path,
        "wise.csv",
        "TransferWise ID,Date,Amount,Currency,Description\nW-1,05-01-2026,1.00,EUR,x\n",
    )
    assert read_bank(w)[0].status == ""


# Malformed rows and files must give an error that says where and what, never a traceback.

WISE_HEADER = "TransferWise ID,Date,Amount,Currency,Description\n"


def test_a_row_with_too_few_fields_names_the_missing_column(tmp_path):
    p = write(tmp_path, "wise.csv", WISE_HEADER + "W-1,05-01-2026,500.00\n")
    with pytest.raises(ValueError, match=r"wise\.csv line 2.*no value for Currency"):
        read_bank(p)


def test_a_stripe_row_with_too_few_fields_names_the_missing_column(tmp_path):
    p = write(tmp_path, "payouts.csv", STRIPE_HEADER + "po_1,2026-01-05,-5.00\n")
    with pytest.raises(ValueError, match=r"payouts\.csv line 2.*no value for"):
        read_stripe(p)


def test_an_empty_or_text_amount_says_what_is_wrong(tmp_path):
    for bad in ("", "abc", "12,5,3x"):
        p = write(tmp_path, "wise.csv", WISE_HEADER + f'W-1,05-01-2026,"{bad}",EUR,x\n')
        with pytest.raises(ValueError, match=r"wise\.csv line 2: bad amount"):
            read_bank(p)


def test_a_file_that_is_not_utf8_names_the_file_and_the_fix(tmp_path):
    p = tmp_path / "wise.csv"
    p.write_bytes(WISE_HEADER.encode() + b"W-1,05-01-2026,5.00,EUR,Caf\xe9\n")
    with pytest.raises(
        ValueError, match=r"wise\.csv: not a UTF-8 text file.*Save the export as UTF-8"
    ):
        read_bank(p)
    q = tmp_path / "payouts.csv"
    q.write_bytes(STRIPE_HEADER.encode() + b"po_1,2026-01-05,-1.00,eur,Caf\xe9,paid\n")
    with pytest.raises(ValueError, match=r"payouts\.csv: not a UTF-8 text file"):
        read_stripe(q)
