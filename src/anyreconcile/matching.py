"""Match each Stripe payout to one bank deposit.

A deposit is a candidate for a payout when all of these hold:
- same direction (money in for a payout, money out for a negative payout);
- it lands from 0 to `window_days` business days after the payout's arrival date;
- the EUR gap between payout and deposit is within the tolerance. Both amounts are
  converted at the payout's arrival-date rate, so equal amounts in one currency always
  give a gap of zero. The tolerance is `fee_tolerance_eur`, plus `fx_spread_pct` percent of
  the payout when the two currencies differ.

Among candidates the best is: a Stripe hint in the description first, then the smallest
gap, then a deposit in the payout's own currency, then the earliest date. Ties and clashes
are never guessed, see pairing.py.
"""

from datetime import date, timedelta
from decimal import Decimal

from anyreconcile.config import Config
from anyreconcile.fx import Rates, to_eur
from anyreconcile.internal import is_stripe_hinted
from anyreconcile.model import Match, Transaction, Unmatched, round2
from anyreconcile.pairing import pair_up

STRIPE_LEFTOVER = "looks like a Stripe deposit, but no payout matches"

# A deposit within this share of the payout counts as a near miss in the exception reason.
NEAR_MISS = Decimal("0.10")


def add_business_days(day: date, n: int) -> date:
    """Move forward n weekdays. Weekends are skipped, public holidays are not."""
    while n > 0:
        day += timedelta(days=1)
        if day.weekday() < 5:
            n -= 1
    return day


def _gap(payout: Transaction, dep: Transaction, cfg: Config, rates: Rates) -> Decimal:
    """Payout minus deposit in EUR, both at the payout's arrival-date rate."""
    age = cfg.max_rate_age_days
    payout_eur = to_eur(payout.amount, payout.currency, payout.date, rates, age)
    return payout_eur - to_eur(dep.amount, dep.currency, payout.date, rates, age)


def _in_window(payout: Transaction, dep: Transaction, cfg: Config) -> bool:
    same_direction = (payout.amount > 0) == (dep.amount > 0)
    last_day = add_business_days(payout.date, cfg.window_days)
    return same_direction and payout.date <= dep.date <= last_day


def _score(payout: Transaction, dep: Transaction, cfg: Config, rates: Rates) -> tuple | None:
    if not _in_window(payout, dep, cfg):
        return None
    gap = abs(_gap(payout, dep, cfg, rates))
    tolerance = cfg.fee_tolerance_eur
    if payout.currency != dep.currency:
        payout_eur = to_eur(
            payout.amount, payout.currency, payout.date, rates, cfg.max_rate_age_days
        )
        tolerance += abs(payout_eur) * cfg.fx_spread_pct / 100
    if gap > tolerance:
        return None
    other_currency = payout.currency != dep.currency
    return (not is_stripe_hinted(dep, cfg), gap, other_currency, (dep.date - payout.date).days)


def _why_unmatched(
    payout: Transaction, deposits: list[Transaction], cfg: Config, rates: Rates
) -> str:
    """Explain a payout that had no usable candidate."""
    payout_eur = to_eur(payout.amount, payout.currency, payout.date, rates, cfg.max_rate_age_days)
    near = [
        abs(_gap(payout, d, cfg, rates))
        for d in deposits
        if _in_window(payout, d, cfg)
        and abs(_gap(payout, d, cfg, rates)) <= abs(payout_eur) * NEAR_MISS
    ]
    if near:
        return f"amount differs by {round2(min(near))} EUR, above tolerance"
    return f"no deposit within {cfg.window_days} business days"


def stripe_leftovers(
    pool: list[Transaction], cfg: Config
) -> tuple[list[Unmatched], list[Transaction]]:
    """Bank rows that mention a hint word but matched no payout need a person to look."""
    issues = [Unmatched(t, STRIPE_LEFTOVER) for t in pool if is_stripe_hinted(t, cfg)]
    rest = [t for t in pool if not is_stripe_hinted(t, cfg)]
    return issues, rest


def match_payouts(
    payouts: list[Transaction], deposits: list[Transaction], cfg: Config, rates: Rates
) -> tuple[list[Match], list[Unmatched]]:
    """Return (matches, payouts that need a human). Output is sorted by payout date."""
    result = pair_up(payouts, deposits, lambda p, d: _score(p, d, cfg, rates))

    matches = [
        Match(payouts[i], deposits[j], _gap(payouts[i], deposits[j], cfg, rates))
        for i, j in result.pairs
    ]
    reasons: dict[int, str] = {}
    for i, js in result.ties.items():
        reasons[i] = f"{len(js)} candidates with the same amount"
    for claimants in result.clashes.values():
        for i in claimants:
            reasons[i] = f"{len(claimants)} payouts fit the same deposit"
    matched = {i for i, _ in result.pairs}
    issues = []
    for i, payout in enumerate(payouts):
        if i in matched:
            continue
        reason = reasons.get(i) or _why_unmatched(payout, deposits, cfg, rates)
        issues.append(Unmatched(payout, reason))
    matches.sort(key=lambda m: (m.payout.date, m.payout.id))
    issues.sort(key=lambda u: (u.txn.date, u.txn.id))
    return matches, issues
