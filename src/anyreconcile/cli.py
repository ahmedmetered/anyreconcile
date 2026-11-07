"""Command line entry point: read files, run the stages in order, write results."""

import argparse
import sys
from pathlib import Path

from anyreconcile.adapters import read_bank, read_stripe
from anyreconcile.config import Config, load_config
from anyreconcile.duplicates import drop_duplicates
from anyreconcile.fx import Rates, download_rates, load_rates, with_eur
from anyreconcile.internal import find_internal
from anyreconcile.matching import match_payouts, stripe_leftovers
from anyreconcile.model import Result, Transaction
from anyreconcile.report import summary, write_results


def reconcile(
    payouts: list[Transaction], bank: list[Transaction], rates: Rates, cfg: Config
) -> Result:
    """The whole pipeline. The order matters, see docs/how-matching-works.md."""
    payouts = with_eur(payouts, rates, cfg.max_rate_age_days)
    bank = with_eur(bank, rates, cfg.max_rate_age_days)
    bank, dropped, duplicate_issues = drop_duplicates(bank)
    matches, payout_issues = match_payouts(payouts, bank, cfg, rates)
    used = {id(m.deposit) for m in matches}
    internal, internal_issues, pool = find_internal([t for t in bank if id(t) not in used], cfg)
    stripe_issues, pool = stripe_leftovers(pool, cfg)
    bank_issues = duplicate_issues + internal_issues + stripe_issues
    bank_issues.sort(key=lambda u: (u.txn.date, u.txn.account))
    internal.sort(key=lambda pair: (pair.out.date, pair.out.id))
    return Result(
        matched=matches,
        internal=internal,
        exceptions=sorted(
            payout_issues + bank_issues, key=lambda u: (u.txn.date, u.txn.source, u.txn.id)
        ),
        duplicates_dropped=dropped,
        unmatched_bank_rows=len(pool),
    )


def check_account_names(paths: list[Path]) -> None:
    """The account name is the file name without .csv, so two files must not share it."""
    seen: dict[str, Path] = {}
    for path in paths:
        if path.stem in seen:
            raise ValueError(
                f"the bank files {seen[path.stem]} and {path} both give the account name "
                f"'{path.stem}'. Rename one file so each account has its own name."
            )
        seen[path.stem] = path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="anyreconcile", description="Match Stripe payouts to bank deposits."
    )
    p.add_argument("--stripe", required=True, type=Path, help="Stripe payouts CSV export")
    p.add_argument(
        "--bank", required=True, action="append", type=Path, help="bank CSV export (repeat)"
    )
    p.add_argument("--out", type=Path, default=Path("results"), help="output folder")
    p.add_argument("--config", type=Path, help="TOML file with tolerances and accounts")
    p.add_argument(
        "--rates", type=Path, default=Path("eurofxref-hist.csv"), help="ECB rates csv file"
    )
    p.add_argument(
        "--download-rates", action="store_true", help="download the ECB rates to --rates first"
    )
    p.add_argument("--sheet", help="Google spreadsheet title to push exceptions to (optional)")
    p.add_argument("--sheet-credentials", type=Path, help="Google service account JSON key")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if bool(args.sheet) != bool(args.sheet_credentials):
        parser.error("--sheet and --sheet-credentials must be used together")
    try:
        if args.download_rates:
            download_rates(args.rates)
        if not args.rates.exists():
            raise ValueError(f"rates file {args.rates} not found. Use --download-rates to get it.")
        check_account_names(args.bank)
        cfg = load_config(args.config)
        rates = load_rates(args.rates)
        payouts = read_stripe(args.stripe)
        bank = [t for path in args.bank for t in read_bank(path)]
        result = reconcile(payouts, bank, rates, cfg)
        write_results(result, args.out)
    except (ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    for key, value in summary(result).items():
        print(f"{key.replace('_', ' '):>22}: {value}")
    print(f"results written to {args.out}")
    if args.sheet:
        try:
            from anyreconcile.sheets import push_exceptions  # optional, imported only here

            n = push_exceptions(args.out / "exceptions.csv", args.sheet_credentials, args.sheet)
        except Exception as e:  # gspread raises many types, all are reported the same way
            print(f"error: could not update the Google Sheet: {e}", file=sys.stderr)
            return 2
        print(f"{n} exception rows pushed to Google Sheet '{args.sheet}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
