"""One pairing rule, shared by internal-transfer detection and payout matching.

Given two lists and a score function, pair items one-to-one without guessing:
- a left item whose two best candidates score equally is a tie (not paired);
- two left items that both pick the same right item are a clash (neither is paired).
Everything else that has a candidate is paired with its single best one.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Pairing:
    pairs: list[tuple[int, int]] = field(default_factory=list)  # (left index, right index)
    ties: dict[int, list[int]] = field(default_factory=dict)  # left index -> equally good rights
    clashes: dict[int, list[int]] = field(default_factory=dict)  # right index -> lefts wanting it


def pair_up[L, R](
    lefts: Sequence[L],
    rights: Sequence[R],
    score: Callable[[L, R], tuple | None],
) -> Pairing:
    """score returns None when the two do not fit, else a tuple where smaller is better."""
    result = Pairing()
    claims: dict[int, list[int]] = {}
    for i, left in enumerate(lefts):
        scored = sorted(
            (s, j) for j, right in enumerate(rights) if (s := score(left, right)) is not None
        )
        if not scored:
            continue
        if len(scored) > 1 and scored[0][0] == scored[1][0]:
            result.ties[i] = [j for s, j in scored if s == scored[0][0]]
        else:
            claims.setdefault(scored[0][1], []).append(i)
    for j, claimants in claims.items():
        if len(claimants) == 1:
            result.pairs.append((claimants[0], j))
        else:
            result.clashes[j] = claimants
    result.pairs.sort()
    return result
