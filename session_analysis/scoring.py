# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Duplicate bridge scoring: what a played contract is worth.

Scoring exists here for one immediate reason: ACBL's tournament pages publish a
score for every row but no trick count, having disabled that column, so the
canonical trick count has to be recovered from the score. Recovery works by
scoring all fourteen possible results and taking the one that matches — the map
from tricks to score is strictly increasing for a fixed contract, so exactly one
can match, and an inverse never has to be written or maintained.

Scores are stated from declarer's side throughout: positive when the contract
made, negative when it went down. Callers holding a North-South score negate it
for an East-West declarer.
"""

import dataclasses
from collections.abc import Mapping, Sequence

from session_analysis.enums import Penalty, Strain
from session_analysis.notation import BOOK


@dataclasses.dataclass(frozen=True)
class _ByVulnerability[T]:
  """One rule's two values: what it is worth to a declarer at each
  vulnerability.

  Almost every reward and penalty in the scoring table is a pair like this, and
  the pairs are what a reader most easily gets backwards. Naming both sides
  keeps the table legible where it is written and unambiguous where it is read.
  """

  not_vulnerable: T
  vulnerable: T

  def value(self, is_declarer_vulnerable: bool) -> T:
    """Whichever of the two applies to this declarer."""
    return self.vulnerable if is_declarer_vulnerable else self.not_vulnerable


# What each trick of the contract is worth, by strain. Notrump's first trick is
# worth ten more, handled apart.
_TRICK_VALUES: Mapping[Strain, int] = {
  Strain.CLUBS: 20,
  Strain.DIAMONDS: 20,
  Strain.HEARTS: 30,
  Strain.SPADES: 30,
  Strain.NOTRUMP: 30,
}
_NOTRUMP_FIRST_TRICK_BONUS = 10

# Doubling multiplies what the bid tricks score, and that multiplied total is
# what decides whether a contract reaches game.
_PENALTY_MULTIPLIERS: Mapping[Penalty, int] = {
  Penalty.NONE: 1,
  Penalty.DOUBLED: 2,
  Penalty.REDOUBLED: 4,
}

# The bonus for a contract whose bid tricks reach a hundred, and for one that
# falls short.
_GAME_BONUS = _ByVulnerability(not_vulnerable=300, vulnerable=500)
_GAME_THRESHOLD = 100
_PARTSCORE_BONUS = 50

# Slam bonuses, on top of the game bonus, by contract level.
_SLAM_BONUSES: Mapping[int, _ByVulnerability[int]] = {
  6: _ByVulnerability(not_vulnerable=500, vulnerable=750),
  7: _ByVulnerability(not_vulnerable=1000, vulnerable=1500),
}

# The consolation for bringing home a contract the opponents doubled.
_INSULT_BONUSES: Mapping[Penalty, int] = {
  Penalty.NONE: 0,
  Penalty.DOUBLED: 50,
  Penalty.REDOUBLED: 100,
}

# What each overtrick is worth once doubled: a flat rate that ignores the
# strain.
_DOUBLED_OVERTRICK_VALUES: Mapping[Penalty, _ByVulnerability[int]] = {
  Penalty.DOUBLED: _ByVulnerability(not_vulnerable=100, vulnerable=200),
  Penalty.REDOUBLED: _ByVulnerability(not_vulnerable=200, vulnerable=400),
}

# What each undertrick costs when the contract was not doubled.
_UNDERTRICK_VALUES = _ByVulnerability(not_vulnerable=50, vulnerable=100)

# What each undertrick costs once doubled, in order. Not vulnerable the price
# rises twice — a hundred, then two hundred for the second and third, then three
# hundred from the fourth on; vulnerable it rises once. The last entry of each
# repeats for every further undertrick.
_DOUBLED_UNDERTRICK_SCHEDULE: _ByVulnerability[Sequence[int]] = (
  _ByVulnerability(
    not_vulnerable=(100, 200, 200, 300),
    vulnerable=(200, 300),
  )
)


class UnscorableResultError(ValueError):
  """No legal result of this contract produces the score a source printed.

  Raised only by the recovery path. It means the score, the contract, or the
  vulnerability disagree with each other — a capture or parsing fault rather
  than an unusual board.
  """


def score_for_contract(
  *,
  level: int,
  strain: Strain,
  penalty: Penalty,
  tricks_taken: int,
  is_declarer_vulnerable: bool,
) -> int:
  """Return what a played contract scores, from declarer's side.

  Args:
    level: the contract level, 1-7.
    strain: what the contract is played in.
    penalty: whether the contract was doubled or redoubled.
    tricks_taken: how many of the thirteen tricks declarer took.
    is_declarer_vulnerable: whether declarer's side was vulnerable;
      vulnerability raises both the rewards and the penalties.

  Returns:
    The score: positive if the contract made, negative if it went down.
  """
  tricks_the_contract_needed = level + BOOK
  if tricks_taken < tricks_the_contract_needed:
    return -_undertrick_penalty(
      undertricks=tricks_the_contract_needed - tricks_taken,
      penalty=penalty,
      is_declarer_vulnerable=is_declarer_vulnerable,
    )

  bid_trick_score = (
    _bid_trick_score(level=level, strain=strain)
    * (_PENALTY_MULTIPLIERS[penalty])
  )
  overtricks = tricks_taken - tricks_the_contract_needed

  return (
    bid_trick_score
    + _game_or_partscore_bonus(bid_trick_score, is_declarer_vulnerable)
    + _slam_bonus(level, is_declarer_vulnerable)
    + _INSULT_BONUSES[penalty]
    + _overtrick_score(
      overtricks=overtricks,
      strain=strain,
      penalty=penalty,
      is_declarer_vulnerable=is_declarer_vulnerable,
    )
  )


def tricks_taken_from_score(
  *,
  level: int,
  strain: Strain,
  penalty: Penalty,
  score: int,
  is_declarer_vulnerable: bool,
) -> int:
  """Return the trick count that produces this score for this contract.

  For a fixed contract and vulnerability, every extra trick is worth strictly
  more than the last, so at most one trick count can produce a given score and
  the search below has no ambiguity to resolve.

  Args:
    level: the contract level, 1-7.
    strain: what the contract is played in.
    penalty: whether the contract was doubled or redoubled.
    score: the score as published, from declarer's side — positive when the
      contract made.
    is_declarer_vulnerable: whether declarer's side was vulnerable.

  Raises:
    UnscorableResultError: if no legal result produces this score.
  """
  for tricks_taken in range(14):
    candidate = score_for_contract(
      level=level,
      strain=strain,
      penalty=penalty,
      tricks_taken=tricks_taken,
      is_declarer_vulnerable=is_declarer_vulnerable,
    )
    if candidate == score:
      return tricks_taken

  vulnerability = 'vulnerable' if is_declarer_vulnerable else 'not vulnerable'
  raise UnscorableResultError(
    f'no result of {level}{strain} ({penalty}, {vulnerability}) scores {score}'
  )


def _bid_trick_score(*, level: int, strain: Strain) -> int:
  """What the tricks the contract bid are worth, before any doubling."""
  score = _TRICK_VALUES[strain] * level
  if strain == Strain.NOTRUMP:
    score += _NOTRUMP_FIRST_TRICK_BONUS
  return score


def _game_or_partscore_bonus(
  bid_trick_score: int, is_declarer_vulnerable: bool
) -> int:
  """The bonus for reaching game, or the smaller one for staying below it.

  The threshold is read off the bid tricks *after* doubling, which is why a
  doubled two-level major makes game.
  """
  if bid_trick_score < _GAME_THRESHOLD:
    return _PARTSCORE_BONUS
  return _GAME_BONUS.value(is_declarer_vulnerable)


def _slam_bonus(level: int, is_declarer_vulnerable: bool) -> int:
  """The extra bonus a slam earns, on top of the game bonus."""
  bonuses = _SLAM_BONUSES.get(level)
  if not bonuses:
    return 0
  return bonuses.value(is_declarer_vulnerable)


def _overtrick_score(
  *,
  overtricks: int,
  strain: Strain,
  penalty: Penalty,
  is_declarer_vulnerable: bool,
) -> int:
  """What tricks beyond the contract are worth.

  Undoubled they score at the contract's own rate; doubled they score at a flat
  rate that ignores the strain.
  """
  if penalty == Penalty.NONE:
    return _TRICK_VALUES[strain] * overtricks
  each = _DOUBLED_OVERTRICK_VALUES[penalty].value(is_declarer_vulnerable)
  return each * overtricks


def _undertrick_penalty(
  *, undertricks: int, penalty: Penalty, is_declarer_vulnerable: bool
) -> int:
  """What going down costs, as a positive number the caller negates.

  Undoubled, every undertrick costs the same. Doubled, the price climbs for the
  first few and then holds — so the schedule is walked entry by entry, with the
  last entry repeating for every undertrick past it.
  """
  if penalty == Penalty.NONE:
    return _UNDERTRICK_VALUES.value(is_declarer_vulnerable) * undertricks

  schedule = _DOUBLED_UNDERTRICK_SCHEDULE.value(is_declarer_vulnerable)
  cost = sum(
    schedule[min(undertrick_index, len(schedule) - 1)]
    for undertrick_index in range(undertricks)
  )
  # Redoubling doubles the doubled penalty, exactly.
  return cost * (
    _PENALTY_MULTIPLIERS[penalty] // _PENALTY_MULTIPLIERS[Penalty.DOUBLED]
  )
