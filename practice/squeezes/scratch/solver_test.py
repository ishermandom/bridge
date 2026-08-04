# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for the quantum single-dummy solver."""

from cards import Card, Seat
from problems import Layout, Problem
from solver import QuantumSolver, trick_winner

_card = Card.from_code


def _make_three_card_squeeze() -> Problem:
  """The bare automatic-squeeze matrix.

  South ♣A ♥K ♠3, North ♠A ♠2 ♥2, and one defender holding every guard (♥A ♠K
  ♠Q) while the other holds idle diamonds. Layout 0 puts the guards with West,
  layout 1 with East. Only the ♣A squeeze wins all three tricks.
  """
  guards = frozenset({_card('HA'), _card('SK'), _card('SQ')})
  idles = frozenset({_card('D5'), _card('D4'), _card('D3')})
  return Problem(
    north=frozenset({_card('SA'), _card('S2'), _card('H2')}),
    south=frozenset({_card('CA'), _card('HK'), _card('S3')}),
    layouts=(
      Layout(west=guards, east=idles),
      Layout(west=idles, east=guards),
    ),
    leader=Seat.SOUTH,
    target_tricks=3,
  )


# --- trick mechanics ---


def test_trick_winner_is_highest_card_of_the_led_suit() -> None:
  trick = (
    (Seat.SOUTH, _card('S5')),
    (Seat.WEST, _card('HA')),
    (Seat.NORTH, _card('SK')),
    (Seat.EAST, _card('D2')),
  )

  # The ♥A does not beat the led spades in notrump.
  assert trick_winner(trick) is Seat.NORTH


def test_follow_suit_is_forced_when_the_layout_holds_the_led_suit() -> None:
  problem = Problem(
    north=frozenset({_card('S2')}),
    south=frozenset({_card('SA')}),
    layouts=(
      Layout(west=frozenset({_card('SK')}), east=frozenset({_card('H3')})),
    ),
    leader=Seat.SOUTH,
    target_tricks=1,
  )
  solver = QuantumSolver(problem)

  position = solver.play(solver.initial_position(), _card('SA'))

  assert dict(solver.defender_candidates(position)) == {
    _card('SK'): frozenset({0})
  }


def test_completed_tricks_score_and_end_the_game() -> None:
  problem = Problem(
    north=frozenset({_card('S2')}),
    south=frozenset({_card('SA')}),
    layouts=(
      Layout(west=frozenset({_card('SK')}), east=frozenset({_card('SQ')})),
    ),
    leader=Seat.SOUTH,
    target_tricks=1,
  )
  solver = QuantumSolver(problem)

  position = solver.initial_position()
  for code in ['SA', 'SK', 'S2', 'SQ']:  # South, West, North, East in turn
    position = solver.play(position, _card(code))

  assert position.declarer_tricks == 1
  assert solver.is_over(position)


# --- the squeeze matrix ---


def test_squeeze_position_is_winnable_against_either_guard_holder() -> None:
  solver = QuantumSolver(_make_three_card_squeeze())

  assert solver.declarer_can_force(solver.initial_position())


def test_only_the_squeeze_card_preserves_the_win_at_trick_one() -> None:
  solver = QuantumSolver(_make_three_card_squeeze())

  # Leading either threat instead gives up the tempo the squeeze needs.
  assert solver.winning_declarer_cards(solver.initial_position()) == {
    _card('CA')
  }


def test_split_guards_leave_no_uniform_winning_line() -> None:
  matrix = _make_three_card_squeeze()
  split = Problem(
    north=matrix.north,
    south=matrix.south,
    # Each defender guards one threat: no single-defender squeeze exists.
    layouts=(
      Layout(
        west=frozenset({_card('HA'), _card('D4'), _card('D3')}),
        east=frozenset({_card('SK'), _card('SQ'), _card('D5')}),
      ),
    ),
    leader=Seat.SOUTH,
    target_tricks=3,
  )
  solver = QuantumSolver(split)

  assert not solver.declarer_can_force(solver.initial_position())


def test_defender_void_play_filters_the_layout_family() -> None:
  solver = QuantumSolver(_make_three_card_squeeze())

  position = solver.play(solver.initial_position(), _card('CA'))
  # A diamond discard is impossible in layout 0, where West holds the guards.
  position = solver.play(position, _card('D3'))

  assert position.surviving == {1}


def test_north_keeps_both_spade_threats_once_west_shows_a_guard() -> None:
  solver = QuantumSolver(_make_three_card_squeeze())

  position = solver.play(solver.initial_position(), _card('CA'))
  position = solver.play(position, _card('SQ'))

  # With West marked with the guards, North's ♠A2 must both stay: the ♠A fells
  # West's remaining honor and the ♠2 becomes the third trick.
  assert solver.winning_declarer_cards(position) == {_card('H2')}


def test_witness_layout_names_a_beating_lie_after_a_losing_lead() -> None:
  problem = _make_three_card_squeeze()
  solver = QuantumSolver(problem)

  position = solver.play(solver.initial_position(), _card('HK'))

  # The unguarded ♥K lead loses to the ♥A wherever it sits; the first single
  # beating layout found is the West-guards one.
  witnesses = solver.witness_layouts(position)
  assert witnesses == (problem.layouts[0],)
