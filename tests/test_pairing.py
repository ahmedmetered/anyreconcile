from anyreconcile.pairing import pair_up


def gap(a: int, b: int) -> tuple | None:
    """Fits when within 1. Smaller difference is better."""
    return (abs(a - b),) if abs(a - b) <= 1 else None


def test_each_picks_its_single_best():
    r = pair_up([10, 20], [11, 20], gap)
    assert r.pairs == [(0, 0), (1, 1)] and not r.ties and not r.clashes


def test_no_candidate_means_no_pair():
    r = pair_up([10], [50], gap)
    assert r.pairs == [] and not r.ties and not r.clashes


def test_equal_best_candidates_are_a_tie():
    r = pair_up([10], [9, 11], gap)
    assert r.pairs == [] and r.ties == {0: [0, 1]}


def test_better_candidate_beats_worse_one():
    r = pair_up([10], [11, 10], gap)
    assert r.pairs == [(0, 1)]


def test_two_lefts_wanting_one_right_is_a_clash():
    r = pair_up([10, 10], [10], gap)
    assert r.pairs == [] and r.clashes == {0: [0, 1]}
