# How matching works

The tool runs six stages in a fixed order. The order matters, because each stage removes rows the next stage should not see.

1. **Read and convert.** Each file goes through its adapter. Every row gets an EUR value at the ECB rate for its own date. Weekends and holidays use the latest earlier rate. If the closest rate is more than `max_rate_age_days` old (7 by default), the run stops with an error.
2. **Duplicates.** A repeated bank id in one account is dropped and counted. Identical rows with no bank id go to exceptions.
3. **Payout matching.** Each payout looks for candidates among all the de-duplicated bank rows.
4. **Internal transfers.** The tool searches the bank rows that no payout used. It pairs outgoing and incoming rows across your accounts. Paired rows go to `internal.csv`. If a pair is unclear (a tie or a clash), every row involved goes to exceptions.
5. **Leftover Stripe deposits.** A bank row that still mentions a hint word (`STRIPE`) after stages 3 and 4 goes to exceptions with the reason `looks like a Stripe deposit, but no payout matches`. Other leftover rows are only counted in the summary.
6. **Write.** The tool writes the three CSV files and prints the summary.

Payout matching comes before internal transfers so that a real Stripe deposit cannot be taken as a transfer because an outgoing payment of a similar size exists. Duplicates come first so that a repeated row cannot create a false tie. A transfer that looks like a payout (same size, inside the window, no hint word) can still be picked by a payout when nothing ranks higher. A hint word, or a deposit in the payout's own currency, ranks higher, and a real tie goes to exceptions.

## Payout matching in detail

For each payout, a deposit is a candidate when it passes all of these:

1. It points the same way. A payout of money in needs a credit. A negative payout needs a debit.
2. It lands from `early_days` calendar days before the payout's arrival date (bank exports use UTC dates, so a deposit can look a day early) up to `window_days` business days after it.
3. The EUR gap, with both amounts converted at the payout's arrival-date rate, is at most `fee_tolerance_eur`. If the currencies differ, `fx_spread_pct` percent of the payout adds to the limit.

The tool ranks candidates by four keys, in order: a deposit that mentions a hint word (`STRIPE`) first, then the smaller gap, then a deposit in the payout's own currency, then the date closest to the arrival date.

Then the tool decides:

| Situation | Result |
|---|---|
| One best candidate, and no other payout picks it | Match |
| Two or more candidates share the best rank | Exception: `N candidates with the same amount` |
| Two or more payouts pick the same best deposit | Exception for each: `N payouts fit the same deposit` |
| No candidate, but a deposit in the window is within 10 percent of the payout | Exception: `amount differs by X EUR, above tolerance` |
| No candidate and no near deposit | Exception: `no deposit within N business days` |

A payout that hits a tie or a clash does not fall back to its second choice. A second choice would be a guess.

## Internal transfers in detail

After payout matching, the tool searches the bank rows that no payout used. An outgoing row and an incoming row form an internal transfer when all of these hold:

1. They sit in two different accounts of yours.
2. They are at most `internal_days` apart.
3. Their EUR gap is small enough. In one currency the limit is `fee_tolerance_eur`. Across two currencies it is `fx_spread_pct` percent of the outgoing amount, which covers the conversion spread.
4. Neither row mentions a hint word.

If a row has two equally good partners, or two rows want the same partner, every row involved goes to exceptions.

## Worked example

This example uses the demo data. The payout is `po_006`, 550.00 USD with arrival date Wednesday 2026-01-14. The ECB rate that day is 1.10 USD per EUR (in the synthetic rates file).

**Step 1: convert.** 550.00 / 1.10 = 500.00 EUR.

**Step 2: window.** The window starts one calendar day early, on Tuesday the 13th. It runs through 3 business days after the arrival date: Thursday the 15th, Friday the 16th, Monday the 19th. It ends on the 19th.

**Step 3: tolerance.** The payout is in USD. A deposit in another currency gets 1.00 EUR plus 1.5 percent of 500.00 EUR, which is 1.00 + 7.50 = 8.50 EUR. A deposit in USD gets 1.00 EUR.

**Step 4: look at the credits in the window.** Duplicates are already out of the pool. Internal transfers are not, because payouts match first.

| Deposit | Date | In EUR at 2026-01-14 rates | Gap to 500.00 | Limit | Result |
|---|---|---|---|---|---|
| Wise `W-1006` and `W-1007`, 200.00 EUR each | 13th | 200.00 | 300.00 | 8.50 | Too far off |
| Wise `W-1005`, 497.00 EUR | 15th | 497.00 | 3.00 | 8.50 | Candidate |
| Mercury, 625.00 USD | 16th | 568.18 | 68.18 | 1.00 | Too far off |
| Mercury, 546.00 USD (a transfer from Wise) | 14th | 496.36 | 3.64 | 1.00 | Too far off |
| Revolut `R-2004`, 90.00 GBP | 15th | 112.50 | 387.50 | 8.50 | Too far off |
| Wise `W-1019`, 35.00 EUR | 19th | 35.00 | 465.00 | 8.50 | Too far off |

**Step 5: decide.** One candidate is left, and no other payout picks `W-1005`. The tool matches `po_006` to `W-1005`.

**Result in `matched.csv`.** `payout_eur` is 500.00, `deposit_eur` is 497.00 and `diff_eur` is 3.00. A person can read that as a bank or FX cost of 3.00 EUR.

## Where the edge cases live

| Edge case | Code | Test |
|---|---|---|
| Weekend and holiday rates | `fx.rate` | `test_fx.py` |
| Business day arithmetic | `matching.add_business_days` | `test_matching.py` |
| Tie, clash, no guessing | `pairing.pair_up` | `test_pairing.py` |
| Same bank id twice, identical rows without id | `duplicates.drop_duplicates` | `test_duplicates.py` |
| Internal transfers with FX spread | `internal.find_internal` | `test_internal.py` |
| Negative payouts | `matching._in_window` | `test_matching.py` |
| Rounding at output, not before | `report.write_results`, `model.round2` | `test_end_to_end.py` |
