"""Run the whole CLI on the synthetic dataset and compare with the hand-written expected.json."""

import csv
import json

from conftest import FIXTURES

from anyreconcile.cli import main

EXPECTED = json.loads((FIXTURES / "expected.json").read_text(encoding="utf-8"))


def read(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def without_comments(rows):
    return [{k: v for k, v in row.items() if not k.startswith("_")} for row in rows]


def run_cli(out):
    return main(
        [
            "--stripe", str(FIXTURES / "stripe_payouts.csv"),
            "--bank", str(FIXTURES / "wise.csv"),
            "--bank", str(FIXTURES / "revolut.csv"),
            "--bank", str(FIXTURES / "mercury.csv"),
            "--rates", str(FIXTURES / "ecb_rates.csv"),
            "--out", str(out),
        ]
    )  # fmt: skip


def check(actual_rows, expected_rows):
    """Same rows in the same order. Only the columns named in expected.json are compared."""
    assert len(actual_rows) == len(expected_rows)
    for actual, expected in zip(actual_rows, without_comments(expected_rows), strict=True):
        assert {k: actual[k] for k in expected} == expected


def test_matched(tmp_path):
    assert run_cli(tmp_path) == 0
    check(read(tmp_path / "matched.csv"), EXPECTED["matched"])


def test_internal(tmp_path):
    run_cli(tmp_path)
    check(read(tmp_path / "internal.csv"), EXPECTED["internal"])


def test_exceptions(tmp_path):
    run_cli(tmp_path)
    check(read(tmp_path / "exceptions.csv"), EXPECTED["exceptions"])


def test_summary_printed(tmp_path, capsys):
    run_cli(tmp_path)
    printed = capsys.readouterr().out
    for key, value in EXPECTED["summary"].items():
        if not key.startswith("_"):
            assert f"{key.replace('_', ' ')}: {value}\n" in printed


def test_every_payout_is_accounted_for_exactly_once(tmp_path):
    run_cli(tmp_path)
    ids = [r["payout_id"] for r in read(tmp_path / "matched.csv")]
    ids += [r["row_id"] for r in read(tmp_path / "exceptions.csv") if r["source"] == "stripe"]
    assert sorted(ids) == [f"po_{n:03d}" for n in range(1, 16)]
