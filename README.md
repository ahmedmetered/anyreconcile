# anyreconcile

Match Stripe payouts to bank deposits from Wise, Revolut Business and Mercury, in several currencies.

**All data in this repository is synthetic.** The files in `tests/fixtures` hold invented payouts, bank rows and exchange rates. No real account, person or transaction appears anywhere.

## The problem

Stripe pays out in batches. Each payout reaches a bank account a few days later, sometimes in another currency, and sometimes minus a bank fee. Matching the Stripe list against bank statements by hand takes time and invites mistakes. Money you move between your own accounts adds noise, because it counts as neither income nor expense.

anyreconcile reads one Stripe payouts export and one or more bank exports. It matches each payout to a deposit, sets aside transfers between your own accounts, and lists every row it cannot match, with a reason in plain words.

## Quick start

You need Python 3.12 or newer. The core uses nothing outside the standard library.

```
pip install -e .
anyreconcile --stripe tests/fixtures/stripe_payouts.csv --bank tests/fixtures/wise.csv --bank tests/fixtures/revolut.csv --bank tests/fixtures/mercury.csv --rates tests/fixtures/ecb_rates.csv --out results/
```

The terminal shows this summary for the demo data:

```
               payouts: 15
               matched: 10
     payout exceptions: 5
       bank exceptions: 6
    internal transfers: 2
    duplicates dropped: 1
   unmatched bank rows: 19
    matched payout eur: 5700.00
         bank fees eur: 4.43
```

For your own files, replace `--rates ...` with `--download-rates`. That downloads the ECB history to `eurofxref-hist.csv` in the current folder and uses it. Add `--rates PATH` as well to choose another location.

## Output

`--out` receives three files.

- `matched.csv`: each payout with its deposit, the original amounts and currencies, the EUR values, and `diff_eur` (the fee, in EUR).
- `internal.csv`: transfers between your own accounts. Leave them out of income and expense.
- `exceptions.csv`: payouts and bank rows that need a person. A bank row that mentions `STRIPE` and matches no payout is listed here too. The `reason` column says what happened, for example `no deposit within 3 business days`, `2 candidates with the same amount`, `amount differs by 4.20 EUR, above tolerance` or `still in transit when the export was made` (a payout whose Stripe status is `in_transit` or `pending` and has no deposit yet).

Amounts keep the precision of the source file. EUR values round to cents (half up) when written, and nowhere before. Text cells (description, account, id, reason) that start with `=`, `+`, `-`, `@`, a tab or a carriage return get a leading quote, so a spreadsheet shows them as text and does not run them as formulas.

## Matching rules

The tool applies these rules in this order. [docs/how-matching-works.md](docs/how-matching-works.md) walks through one payout.

1. **Duplicates.** Rows with the same bank id in the same account count once. Identical rows without a bank id go to exceptions, since a duplicate and two real transactions look the same.
2. **Currency.** Every amount converts to EUR at the ECB rate for its own date. Weekends and holidays use the latest earlier rate. A rate more than 7 days old is refused with an error that points to `--download-rates`, so a stale rates file cannot pass unnoticed. Each output row keeps the original amount and currency.
3. **Date window.** A deposit can match a payout when it lands from 1 calendar day before to 3 business days after the payout's arrival date. The day before covers bank exports that use UTC dates. Business days skip Saturday and Sunday. The tool has no holiday calendar.
4. **Amount.** Payout and deposit may differ by up to 1.00 EUR, which leaves room for bank fees. When the two currencies differ, 1.5 percent of the payout adds to that limit.
5. **Direction.** A positive payout matches a bank credit. A negative payout matches a bank debit.
6. **Best candidate.** When several deposits fit, a deposit that mentions `STRIPE` wins first, then the smaller amount gap, then a deposit in the payout's own currency, then the date closest to the arrival date. Each deposit matches at most one payout.
7. **No guessing.** When two deposits fit one payout with the same rank, or two payouts want the same deposit, none of them match. All of them go to exceptions.
8. **Internal transfers.** Payouts match first. Among the bank rows no payout used, an outgoing row and an incoming row in two of your accounts form an internal transfer when they sit at most 2 days apart and agree in EUR. In one currency the two amounts are compared at one rate, so a rate move between the two days does not matter, and the gap may be at most 1.00 EUR. Across two currencies it may be 1.5 percent, which covers the conversion spread. Rows that mention `STRIPE` never count as internal. A row with two equally good partners, or two rows that want the same partner, go to exceptions.
9. **Leftover Stripe deposits.** A bank row that mentions `STRIPE` and that no payout and no internal transfer used goes to exceptions with the reason `looks like a Stripe deposit, but no payout matches`. Other leftover rows are only counted in the summary.

## Settings

Pass a TOML file with `--config settings.toml`. Every key is optional. A wrong type, a negative number or an unknown key stops the run with an error that names the key. These are the defaults:

```toml
fee_tolerance_eur = 1.00      # largest accepted gap between payout and deposit
fx_spread_pct = 1.5           # allowed spread, in percent, for FX
window_days = 3               # business days after the arrival date
early_days = 1                # calendar days before the arrival date
internal_days = 2             # days between the two halves of an internal transfer
my_accounts = []              # account names that are yours; empty means every bank file
hint_words = ["STRIPE"]       # words that mark a deposit as coming from Stripe
max_rate_age_days = 7         # refuse an FX rate older than this many days
```

An account name is the bank file's name without `.csv`. `wise_eur.csv` gives the account `wise_eur`. Two bank files must not share a name, even in different folders. The tool stops with an error and asks you to rename one.

## Google Sheets (optional)

```
pip install -e ".[sheets]"
anyreconcile ... --sheet "Reconciliation" --sheet-credentials service-account.json
```

This replaces the `exceptions` tab of the named spreadsheet with `exceptions.csv`. Share the spreadsheet with the service account's e-mail address first. The core never imports `gspread`.

## Preparing your exports

The tool reads these columns and ignores the rest. Files must be UTF-8 CSV. A missing column, a row with too few fields, a bad amount or a file in another encoding stops the run with an error that names the file and, for rows, the line.

| Source | Columns the tool reads | How well the format was checked |
|---|---|---|
| Stripe | `payout_id`, `payout_expected_arrival_date`, `net`, `currency`, `description`, `payout_status` | Stripe's own report schema (`payouts.itemized`) and documentation |
| Wise | `TransferWise ID`, `Date` (DD-MM-YYYY), `Amount`, `Currency`, `Description`, `Payment Reference` (optional) | A user's mailing-list post and an open-source plugin. No Wise page lists the columns. |
| Revolut Business | `ID`, `Date completed (UTC)`, `Description`, `Reference` (optional), `Amount`, `Payment currency` | Header rows posted in GitHub issues. No Revolut page lists the columns. |
| Mercury | `Date (UTC)` (MM-DD-YYYY), `Description`, `Amount`, `Status`, `Reference` (optional) | An open-source importer that rejects any other header. No Mercury page lists the columns. |

Stripe: export the `payouts.itemized` report with at least those columns. `net` is the change in your Stripe balance, so a payout to your bank is negative, and the tool flips the sign. Payouts with status `failed` or `canceled` never reach the bank, so the tool skips them. The Payouts page export offers a column choice too. Whether it uses these exact names is unconfirmed.

Wise exports one CSV per currency balance. Mercury accounts count as USD, and Mercury rows have no bank id.

Still unconfirmed, because no source shows real values:

- The date text inside Stripe and Revolut files. No source shows a real value. Two third-party descriptions call Stripe's column a datetime. The tool accepts `YYYY-MM-DD`, with or without a time after a space or a `T`.
- The values of Mercury's `Status` column. The tool skips `pending`, `cancelled` and `failed`.
- Revolut's `State` column, which some export variants have. The tool ignores it.

If an export differs, change the matching line in that source's `Spec` in `src/anyreconcile/adapters.py`. The docstring at the top of that file records the sources and dates of this research. The tests check the matching logic on synthetic files in these layouts. No test has run on a real export.

## Development

```
pip install -e ".[dev]"
ruff check .
ruff format --check .
pytest
```

`tests/fixtures/expected.json` holds the expected output for the demo data. Each row there carries a `_how` note that shows how the number was worked out by hand. CI runs ruff and pytest on every push and pull request.

## License

MIT, see `LICENSE`.
