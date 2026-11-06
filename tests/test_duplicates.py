from helpers import txn

from anyreconcile.duplicates import AMBIGUOUS, drop_duplicates


def test_same_id_in_same_account_is_dropped_and_counted():
    rows = [txn("10", id="W1"), txn("10", id="W1"), txn("10", id="W2")]
    kept, dropped, issues = drop_duplicates(rows)
    assert [t.id for t in kept] == ["W1", "W2"] and dropped == 1 and issues == []


def test_same_id_in_different_accounts_is_not_a_duplicate():
    rows = [txn("10", id="1", account="wise"), txn("10", id="1", account="revolut")]
    kept, dropped, _ = drop_duplicates(rows)
    assert len(kept) == 2 and dropped == 0


def test_identical_rows_without_id_all_go_to_exceptions():
    rows = [txn("250", account="mercury"), txn("250", account="mercury"), txn("99")]
    kept, dropped, issues = drop_duplicates(rows)
    assert [t.amount for t in kept] == [99] and dropped == 0
    assert len(issues) == 2 and all(u.reason == AMBIGUOUS for u in issues)


def test_rows_without_id_that_differ_are_kept():
    rows = [txn("250", day=5), txn("250", day=6), txn("250", description="other")]
    kept, _, issues = drop_duplicates(rows)
    assert len(kept) == 3 and issues == []
