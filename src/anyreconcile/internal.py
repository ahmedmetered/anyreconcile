"""Find transfers between my own accounts, so they are not counted as income or expense.

This runs after payout matching, on the bank rows no payout used. A pair is: one row of money
out, one row of money in, in different accounts of mine, at most `internal_days` apart, and
equal in EUR. In one currency the gap may be at most `fee_tolerance_eur`. Across two currencies
it may be `fx_spread_pct` percent of the amount (conversion spread). Rows that look like Stripe
deposits are never used. If a pair is not clear-cut (a tie or a clash), every row involved
goes to exceptions.
"""

from anyreconcile.config import Config
from anyreconcile.model import Internal, Transaction, Unmatched
from anyreconcile.pairing import pair_up

TIE = "possible internal transfer, but {n} candidates fit equally well"
CLASH = "possible internal transfer, but {n} rows claim the same counterpart"


def is_stripe_hinted(t: Transaction, cfg: Config) -> bool:
    text = f"{t.description} {t.reference}".upper()
    return any(word.upper() in text for word in cfg.hint_words)


def _score(out: Transaction, into: Transaction, cfg: Config) -> tuple | None:
    assert out.eur is not None and into.eur is not None  # fx step ran first
    days = abs((into.date - out.date).days)
    gap = abs(-out.eur - into.eur)
    if out.account == into.account or days > cfg.internal_days:
        return None
    same_currency = out.currency == into.currency
    limit = cfg.fee_tolerance_eur if same_currency else abs(out.eur) * cfg.fx_spread_pct / 100
    if gap > limit:
        return None
    return (gap, days)


def find_internal(
    bank: list[Transaction], cfg: Config
) -> tuple[list[Internal], list[Unmatched], list[Transaction]]:
    """Return (internal pairs, rows sent to exceptions, rows left for payout matching)."""
    mine = [
        t
        for t in bank
        if (not cfg.my_accounts or t.account in cfg.my_accounts) and not is_stripe_hinted(t, cfg)
    ]
    outs = [t for t in mine if t.amount < 0]
    ins = [t for t in mine if t.amount > 0]
    result = pair_up(outs, ins, lambda o, i: _score(o, i, cfg))

    internal = [Internal(outs[i], ins[j]) for i, j in result.pairs]
    issues: list[Unmatched] = []
    for i, js in result.ties.items():
        issues.append(Unmatched(outs[i], TIE.format(n=len(js))))
        issues.extend(Unmatched(ins[j], TIE.format(n=len(js))) for j in js)
    for j, wanting in result.clashes.items():
        issues.append(Unmatched(ins[j], CLASH.format(n=len(wanting))))
        issues.extend(Unmatched(outs[i], CLASH.format(n=len(wanting))) for i in wanting)
    taken = {id(u.txn) for u in issues}
    taken |= {id(t) for pair in internal for t in (pair.out, pair.into)}
    remaining = [t for t in bank if id(t) not in taken]
    return internal, _unique(issues), remaining


def _unique(issues: list[Unmatched]) -> list[Unmatched]:
    """A row can be named by several ties or clashes. Keep its first reason only."""
    seen: set[int] = set()
    out = []
    for u in issues:
        if id(u.txn) not in seen:
            seen.add(id(u.txn))
            out.append(u)
    return out
