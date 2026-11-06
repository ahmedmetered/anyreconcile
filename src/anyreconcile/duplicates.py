"""Handle repeated bank rows before any matching.

Same account and same bank id: a true duplicate, drop the extra copy and count it.
No bank id and every field identical: we cannot tell a duplicate from two real
transactions, so all copies go to exceptions for a human to decide.
"""

from anyreconcile.model import Transaction, Unmatched

AMBIGUOUS = "identical rows, cannot tell a duplicate from two real transactions"


def drop_duplicates(bank: list[Transaction]) -> tuple[list[Transaction], int, list[Unmatched]]:
    """Return (rows to keep, number of true duplicates dropped, rows sent to exceptions)."""
    seen_ids: set[tuple[str, str]] = set()
    rows: list[Transaction] = []
    dropped = 0
    for t in bank:
        if t.id and (t.account, t.id) in seen_ids:
            dropped += 1
            continue
        seen_ids.add((t.account, t.id))
        rows.append(t)

    groups: dict[tuple, list[Transaction]] = {}
    for t in rows:
        if not t.id:
            key = (t.account, t.date, t.amount, t.currency, t.description, t.reference)
            groups.setdefault(key, []).append(t)
    kept: list[Transaction] = []
    issues: list[Unmatched] = []
    for t in rows:
        if t.id:
            kept.append(t)
            continue
        key = (t.account, t.date, t.amount, t.currency, t.description, t.reference)
        if len(groups[key]) > 1:
            issues.append(Unmatched(t, AMBIGUOUS))
        else:
            kept.append(t)
    return kept, dropped, issues
