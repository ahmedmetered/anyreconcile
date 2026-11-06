import csv

from conftest import FIXTURES

from anyreconcile.cli import main

STRIPE = (
    "id,Arrival Date,Amount,Currency,Description\n"
    "po_1,2026-01-05,500.00,EUR,STRIPE PAYOUT\n"
    "po_2,2026-01-06,900.00,EUR,STRIPE PAYOUT\n"
)
WISE = (
    "TransferWise ID,Date,Amount,Currency,Description,Payment Reference\n"
    "W-1,05-01-2026,500.00,EUR,STRIPE PAYOUT,\n"
)


def read(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run(tmp_path, *extra):
    (tmp_path / "payouts.csv").write_text(STRIPE)
    (tmp_path / "wise.csv").write_text(WISE)
    return main(
        [
            "--stripe", str(tmp_path / "payouts.csv"),
            "--bank", str(tmp_path / "wise.csv"),
            "--rates", str(FIXTURES / "ecb_rates.csv"),
            "--out", str(tmp_path / "out"),
            *extra,
        ]
    )  # fmt: skip


def test_writes_the_three_files_and_prints_a_summary(tmp_path, capsys):
    assert run(tmp_path) == 0
    out = tmp_path / "out"
    (match,) = read(out / "matched.csv")
    assert (match["payout_id"], match["deposit_id"], match["diff_eur"]) == ("po_1", "W-1", "0.00")
    assert read(out / "internal.csv") == []
    (exc,) = read(out / "exceptions.csv")
    assert (exc["row_id"], exc["reason"]) == ("po_2", "no deposit within 3 business days")
    text = capsys.readouterr().out
    assert "matched: 1" in text and "payout exceptions: 1" in text


def test_missing_rates_file_is_a_clear_error(tmp_path, capsys):
    (tmp_path / "payouts.csv").write_text(STRIPE)
    (tmp_path / "wise.csv").write_text(WISE)
    code = main(
        ["--stripe", str(tmp_path / "payouts.csv"), "--bank", str(tmp_path / "wise.csv")]
        + ["--rates", str(tmp_path / "nope.csv")]
    )
    assert code == 2 and "--download-rates" in capsys.readouterr().err


def test_unreadable_bank_file_is_a_clear_error(tmp_path, capsys):
    (tmp_path / "payouts.csv").write_text(STRIPE)
    (tmp_path / "bad.csv").write_text("a,b\n1,2\n")
    code = main(
        ["--stripe", str(tmp_path / "payouts.csv"), "--bank", str(tmp_path / "bad.csv")]
        + ["--rates", str(FIXTURES / "ecb_rates.csv")]
    )
    assert code == 2 and "bad.csv" in capsys.readouterr().err


def test_config_file_is_used(tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text("window_days = 0\n")
    assert run(tmp_path, "--config", str(cfg)) == 0
