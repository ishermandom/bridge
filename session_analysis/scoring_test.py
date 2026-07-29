# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for duplicate bridge scoring and the trick count recovered from it."""

import pytest

from session_analysis.enums import Penalty, Strain
from session_analysis.scoring import (
  UnscorableResultError,
  score_for_contract,
  tricks_taken_from_score,
)


def score(
  level: int,
  strain: Strain,
  tricks_taken: int,
  *,
  penalty: Penalty = Penalty.NONE,
  vulnerable: bool = False,
) -> int:
  """Score a contract, spelled to keep the cases below readable."""
  return score_for_contract(
    level=level,
    strain=strain,
    penalty=penalty,
    tricks_taken=tricks_taken,
    is_declarer_vulnerable=vulnerable,
  )


# --- partscores ---


def test_minor_partscore() -> None:
  # 2D making: forty for the two bid tricks, plus the partscore bonus.
  assert score(2, Strain.DIAMONDS, 8) == 90


def test_major_partscore_with_overtricks() -> None:
  # 2S making four: sixty bid, sixty in overtricks at the major's own rate.
  assert score(2, Strain.SPADES, 10) == 170


def test_notrump_first_trick_is_worth_ten_more() -> None:
  # 1NT is forty rather than thirty, which is the whole of notrump's premium.
  assert score(1, Strain.NOTRUMP, 7) == 90


# --- games and slams ---


def test_game_in_a_major() -> None:
  assert score(4, Strain.HEARTS, 10) == 420
  assert score(4, Strain.HEARTS, 10, vulnerable=True) == 620


def test_game_in_notrump() -> None:
  assert score(3, Strain.NOTRUMP, 9) == 400
  assert score(3, Strain.NOTRUMP, 9, vulnerable=True) == 600


def test_five_of_a_minor_is_game() -> None:
  # A hundred in bid tricks is the threshold, which 5C reaches exactly.
  assert score(5, Strain.CLUBS, 11) == 400


def test_small_slam() -> None:
  assert score(6, Strain.HEARTS, 12) == 980
  assert score(6, Strain.HEARTS, 12, vulnerable=True) == 1430


def test_grand_slam() -> None:
  assert score(7, Strain.SPADES, 13) == 1510
  assert score(7, Strain.SPADES, 13, vulnerable=True) == 2210


def test_doubling_can_carry_a_partscore_to_game() -> None:
  # 2S doubled scores 120 in bid tricks, past the hundred game needs — hence the
  # game bonus, the insult, and the doubled overtrick.
  assert score(2, Strain.SPADES, 9, penalty=Penalty.DOUBLED) == 570


# --- set contracts ---


def test_undoubled_undertricks() -> None:
  assert score(4, Strain.HEARTS, 9) == -50
  assert score(4, Strain.HEARTS, 7) == -150
  assert score(4, Strain.HEARTS, 9, vulnerable=True) == -100


def test_doubled_undertricks_climb_then_hold() -> None:
  # Not vulnerable the price steps 100, 200, 200, then 300 for each further
  # undertrick — the sequence a sacrifice is priced against.
  penalties = [
    score(7, Strain.DIAMONDS, 13 - down, penalty=Penalty.DOUBLED)
    for down in range(1, 6)
  ]
  assert penalties == [-100, -300, -500, -800, -1100]


def test_doubled_undertricks_when_vulnerable() -> None:
  # Vulnerable the price steps once — 200, then 300 apiece.
  penalties = [
    score(
      7, Strain.DIAMONDS, 13 - down, penalty=Penalty.DOUBLED, vulnerable=True
    )
    for down in range(1, 4)
  ]
  assert penalties == [-200, -500, -800]


def test_redoubling_doubles_the_doubled_penalty() -> None:
  doubled = score(3, Strain.NOTRUMP, 6, penalty=Penalty.DOUBLED)
  redoubled = score(3, Strain.NOTRUMP, 6, penalty=Penalty.REDOUBLED)
  assert redoubled == doubled * 2


# --- recovering the trick count from a published score ---


def test_recovers_a_making_contract() -> None:
  assert (
    tricks_taken_from_score(
      level=4,
      strain=Strain.HEARTS,
      penalty=Penalty.NONE,
      score=450,
      is_declarer_vulnerable=False,
    )
    == 11
  )


def test_recovers_a_doubled_sacrifice() -> None:
  # The 1100 an ACBL tournament prints for a five-trick doubled set.
  assert (
    tricks_taken_from_score(
      level=6,
      strain=Strain.DIAMONDS,
      penalty=Penalty.DOUBLED,
      score=-1100,
      is_declarer_vulnerable=False,
    )
    == 7
  )


@pytest.mark.parametrize('tricks_taken', range(14))
@pytest.mark.parametrize('vulnerable', [False, True])
@pytest.mark.parametrize(
  'penalty', [Penalty.NONE, Penalty.DOUBLED, Penalty.REDOUBLED]
)
def test_every_result_round_trips(
  tricks_taken: int, vulnerable: bool, penalty: Penalty
) -> None:
  # The recovery rests on the map from tricks to score being one-to-one for a
  # fixed contract. Scoring each result and recovering it back is the direct
  # test of that, and the reason no inverse has to be maintained.
  scored = score_for_contract(
    level=4,
    strain=Strain.SPADES,
    penalty=penalty,
    tricks_taken=tricks_taken,
    is_declarer_vulnerable=vulnerable,
  )
  assert (
    tricks_taken_from_score(
      level=4,
      strain=Strain.SPADES,
      penalty=penalty,
      score=scored,
      is_declarer_vulnerable=vulnerable,
    )
    == tricks_taken
  )


def test_a_score_no_result_produces_is_refused() -> None:
  # 455 is not a score 4H can produce, so recovery raises rather than guessing
  # at the nearest.
  with pytest.raises(UnscorableResultError, match='455'):
    tricks_taken_from_score(
      level=4,
      strain=Strain.HEARTS,
      penalty=Penalty.NONE,
      score=455,
      is_declarer_vulnerable=False,
    )
