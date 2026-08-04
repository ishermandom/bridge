# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for the interactive game session."""

import pytest
from cards import Card, Seat
from engine import GameSession, SessionStatus
from problems import Layout, Problem
from solver import QuantumSolver

_card = Card.from_code


def _make_three_card_squeeze() -> Problem:
  """The bare automatic-squeeze matrix, as in `solver_test`.

  South ♣A ♥K ♠3, North ♠A ♠2 ♥2; guards ♥A ♠K ♠Q sit with West in layout 0 and
  East in layout 1; the idle defender holds ♦543.
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


def _play_correct_line(session: GameSession) -> None:
  """Drive the hand to its end, always choosing a solver-approved card."""
  solver = QuantumSolver(session.problem)
  while session.status is SessionStatus.PLAYING:
    winning = solver.winning_declarer_cards(session.position)
    card = min(winning, key=lambda c: (c.rank, c.suit.value))
    session.play_declarer_card(card)


def test_correct_play_completes_the_hand_at_target() -> None:
  session = GameSession(_make_three_card_squeeze())

  _play_correct_line(session)

  assert session.status is SessionStatus.COMPLETE
  assert session.position.declarer_tricks == 3
  assert len(session.completed_tricks) == 3


def test_defenders_answer_with_the_least_revealing_lowest_card() -> None:
  session = GameSession(_make_three_card_squeeze())

  outcome = session.play_declarer_card(_card('CA'))

  # Every West candidate is consistent with exactly one layout, so the ambiguity
  # tie breaks to the lowest card: the ♦3. Play then pauses for North's discard.
  assert outcome.plays == (
    (Seat.SOUTH, _card('CA')),
    (Seat.WEST, _card('D3')),
  )
  assert session.seat_to_play() is Seat.NORTH


def test_fatal_north_discard_freezes_play_with_a_witness() -> None:
  session = GameSession(_make_three_card_squeeze())
  session.play_declarer_card(_card('CA'))

  # West's diamond marked East with the guards, so North must keep ♠A2; throwing
  # the ♠2 loses the promotion trick.
  outcome = session.play_declarer_card(_card('S2'))

  assert outcome.status is SessionStatus.FAILED
  assert outcome.error is not None
  assert len(outcome.error.witnesses) == 1
  assert outcome.error.witnesses[0].east == frozenset(
    {_card('HA'), _card('SK'), _card('SQ')}
  )
  assert session.seat_to_play() is None
  assert session.legal_cards() == frozenset()


def test_playing_after_failure_requires_a_restart() -> None:
  session = GameSession(_make_three_card_squeeze())
  session.play_declarer_card(_card('CA'))
  session.play_declarer_card(_card('S2'))

  with pytest.raises(RuntimeError, match='restart'):
    session.play_declarer_card(_card('SA'))


def test_restart_returns_to_the_initial_position() -> None:
  session = GameSession(_make_three_card_squeeze())
  session.play_declarer_card(_card('CA'))
  session.play_declarer_card(_card('S2'))

  session.restart()

  assert session.status is SessionStatus.PLAYING
  assert session.completed_tricks == ()
  assert session.position.declarer_tricks == 0
  assert session.legal_cards() == frozenset(
    {_card('CA'), _card('HK'), _card('S3')}
  )


def test_card_not_following_suit_is_rejected() -> None:
  session = GameSession(
    Problem(
      north=frozenset({_card('S2'), _card('H3')}),
      south=frozenset({_card('SA'), _card('H2')}),
      layouts=(
        Layout(
          west=frozenset({_card('SK'), _card('S4')}),
          east=frozenset({_card('S5'), _card('H4')}),
        ),
      ),
      leader=Seat.SOUTH,
      target_tricks=1,
    )
  )
  session.play_declarer_card(_card('SA'))

  # North holds a spade, so discarding the ♥3 on the spade trick is illegal.
  with pytest.raises(ValueError, match='not a legal play'):
    session.play_declarer_card(_card('H3'))
