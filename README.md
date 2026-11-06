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
       bank exceptions: 2
    internal transfers: 2
    duplicates dropped: 1
   unmatched bank rows: 23
    matched payout eur: 5700.00
         bank fees eur: 4.43
```

For your own files, replace `--rates ...` with `--download-rates`. That downloads the ECB history to `eurofxref-hist.csv` in the current folder and uses it. Add `--rates PATH` as well to choose another location.

## Output

`--out` receives three files.

- `matched.csv`: each payout with its deposit, the original amounts and currencies, the EUR values, and `diff_eur` (the fee, in EUR).
- `internal.csv`: transfers between your own accounts. Leave them out of income and expense.
- `exceptions.csv`: payouts and bank rows that need a person. The `reason` column says what happened, for example `no deposit within 3 business days`, `2 candidates with the same amount` or `amount differs by 4.20 EUR, above tolerance`.

Amounts keep the precision of the source file. EUR values round to cents (half up) when written, and nowhere before.

## Matching rules

The tool applies these rules in this order. [docs/how-matching-works.md](docs/how-matching-works.md) walks through one payout.

1. **Duplicates.** Rows with the same bank id in the same account count once. Identical rows without a bank id go to exceptions, since a duplicate and two real transactions look the same.
2. **Currency.** Every amount converts to EUR at the ECB rate for its own date. Weekends and holidays use the latest earlier rate. Each output row keeps the original amount and currency.
3. **Internal transfers.** An outgoing row and an incoming row in two of your accounts form an internal transfer when they sit at most 2 days apart and agree in EUR within 1.5 percent. The 1.5 percent covers the conversion spread. Rows that mention `STRIPE` never count as internal.
4. **Date window.** A deposit can match a payout when it lands 0 to 3 business days after the payout's arrival date. Business days skip Saturday and Sunday. The tool has no holiday calendar.
5. **Amount.** Payout and deposit may differ by up to 1.00 EUR, which leaves room for bank fees. When the two currencies differ, 1.5 percent of the payout adds to that limit.
6. **Direction.** A positive payout matches a bank credit. A negative payout matches a bank debit.
7. **Best candidate.** When several deposits fit, a deposit that mentions `STRIPE` wins first, then the smaller amount gap, then the earlier date. Each deposit matches at most one payout.
8. **No guessing.** When two deposits fit one payout with the same rank, or two payouts want the same deposit, none of them match. All of them go to exceptions.

## Settings

Pass a TOML file with `--config settings.toml`. Every key is optional. These are the defaults:

```toml
fee_tolerance_eur = 1.00      # largest accepted gap between payout and deposit
fx_spread_pct = 1.5           # allowed spread, in percent, for FX
window_days = 3               # business days after the arrival date
internal_days = 2             # days between the two halves of an internal transfer
my_accounts = []              # account names that are yours; empty means every bank file
hint_words = ["STRIPE"]       # words that mark a deposit as coming from Stripe
```

An account name is the bank file's name without `.csv`. `wise_eur.csv` gives the account `wise_eur`.

## Google Sheets (optional)

```
pip install -e ".[sheets]"
anyreconcile ... --sheet "Reconciliation" --sheet-credentials service-account.json
```

This replaces the `exceptions` tab of the named spreadsheet with `exceptions.csv`. Share the spreadsheet with the service account's e-mail address first. The core never imports `gspread`.

## CSV formats are unconfirmed

No real exports were available when this was written, and the providers' documentation does not list the CSV columns. The column names in `src/anyreconcile/adapters.py` come from public descriptions and may differ from your export. The docstring at the top of that file lists each assumption. If a header differs, change the matching line in that source's `Spec`. The tests prove the matching logic. They do not prove that the adapters read real exports.

## Development

```
pip install -e ".[dev]"
ruff check .
pytest
```

`tests/fixtures/expected.json` holds the expected output for the demo data. Each row there carries a `_how` note that shows how the number was worked out by hand. CI runs ruff and pytest on every push.

## License

MIT, see `LICENSE`.
