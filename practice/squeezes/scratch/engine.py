# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Interactive practice session: the user plays declarer, the engine defends.

Implements the BridgeMaster-style contract (../spec.md #exact-solver): play
stops at the first declarer card that forfeits the position, with witness
layouts explaining why; while declarer stays on a winning path, the defenders
play the least-revealing legal card, so their carding never leaks which layout
actually holds.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from cards import Card, Seat
from problems import Layout, Problem
from solver import Position, QuantumSolver, trick_winner


class SessionStatus(enum.Enum):
  """Where an interactive hand stands."""

  PLAYING = 'playing'
  FAILED = 'failed'
  COMPLETE = 'complete'


@dataclass(frozen=True)
class ErrorReport:
  """Why the last declarer card forfeited the position."""

  played: Card
  message: str
  witnesses: tuple[Layout, ...]


@dataclass(frozen=True)
class CompletedTrick:
  """One finished trick, in play order."""

  plays: tuple[tuple[Seat, Card], ...]
  winner: Seat


@dataclass(frozen=True)
class PlayOutcome:
  """Everything that happened in response to one declarer card."""

  plays: tuple[tuple[Seat, Card], ...]
  error: ErrorReport | None
  status: SessionStatus


class GameSession:
  """One hand in progress against the quantum defenders."""

  def __init__(self, problem: Problem) -> None:
    self._problem = problem
    self._solver = QuantumSolver(problem)
    self._position = self._solver.initial_position()
    self._completed_tricks: list[CompletedTrick] = []
    self._status = SessionStatus.PLAYING
    self._error: ErrorReport | None = None

  @property
  def problem(self) -> Problem:
    """The problem this session plays."""
    return self._problem

  @property
  def position(self) -> Position:
    """The current game state."""
    return self._position

  @property
  def status(self) -> SessionStatus:
    """Whether the hand is live, failed, or complete."""
    return self._status

  @property
  def error(self) -> ErrorReport | None:
    """The report for the card that failed the hand, if any."""
    return self._error

  @property
  def completed_tricks(self) -> tuple[CompletedTrick, ...]:
    """All finished tricks, oldest first."""
    return tuple(self._completed_tricks)

  def seat_to_play(self) -> Seat | None:
    """The seat due to play, or None when the hand is over or frozen."""
    if self._status is not SessionStatus.PLAYING:
      return None
    return self._solver.seat_to_play(self._position)

  def legal_cards(self) -> frozenset[Card]:
    """Cards the user may play now (empty when it isn't their turn)."""
    seat = self.seat_to_play()
    if seat is None or not seat.is_declarer_side:
      return frozenset()
    return self._solver.legal_declarer_cards(self._position)

  def play_declarer_card(self, card: Card) -> PlayOutcome:
    """Play one declarer-side card.

    On a sound card, the defenders answer until the user is due again or the
    hand completes. On a fatal card, play freezes immediately with an
    `ErrorReport` — restart to try the hand again.
    """
    if self._status is not SessionStatus.PLAYING:
      raise RuntimeError(f'hand is {self._status.value}; restart to continue')
    seat = self._solver.seat_to_play(self._position)
    if not seat.is_declarer_side:
      raise RuntimeError(f'not the user\'s turn: {seat.value} is due to play')
    if card not in self._solver.legal_declarer_cards(self._position):
      raise ValueError(
        f'{card} is not a legal play from the {seat.value} hand now'
      )

    self._apply(seat, card)
    plays = [(seat, card)]

    if not self._solver.declarer_can_force(self._position):
      self._status = SessionStatus.FAILED
      self._error = self._build_error(card)
      return PlayOutcome(tuple(plays), self._error, self._status)

    plays.extend(self._autoplay_defenders())
    if self._solver.is_over(self._position):
      self._status = SessionStatus.COMPLETE
    return PlayOutcome(tuple(plays), None, self._status)

  def restart(self) -> None:
    """Reset to the initial position, keeping the same problem."""
    self._position = self._solver.initial_position()
    self._completed_tricks.clear()
    self._status = SessionStatus.PLAYING
    self._error = None

  def _apply(self, seat: Seat, card: Card) -> None:
    """Advance the position by one card, recording any completed trick."""
    full_trick = self._position.trick + ((seat, card),)
    self._position = self._solver.play(self._position, card)
    if not self._position.trick and len(full_trick) == 4:
      self._completed_tricks.append(
        CompletedTrick(full_trick, trick_winner(full_trick))
      )

  def _autoplay_defenders(self) -> list[tuple[Seat, Card]]:
    """Defenders play until the user is due again or the hand ends."""
    plays: list[tuple[Seat, Card]] = []
    while not self._solver.is_over(self._position):
      seat = self._solver.seat_to_play(self._position)
      if seat.is_declarer_side:
        break
      card = self._defender_card()
      self._apply(seat, card)
      plays.append((seat, card))
    return plays

  def _defender_card(self) -> Card:
    """The defender's choice: least revealing while declarer is winning,
    refuting once declarer has erred.
    """
    candidates = self._solver.defender_candidates(self._position)
    pool = dict(candidates)
    if not self._solver.declarer_can_force(self._position):
      refuting = self._solver.refuting_defender_cards(self._position)
      pool = {card: candidates[card] for card in refuting}
    # Most surviving layouts first (least revealing), then lowest rank; suit
    # letter only as a final deterministic tiebreak.
    return min(
      pool, key=lambda card: (-len(pool[card]), card.rank, card.suit.value)
    )

  def _build_error(self, played: Card) -> ErrorReport:
    """Describe why `played` lost the hand, with witness layouts."""
    witnesses = self._solver.witness_layouts(self._position)
    if len(witnesses) == 1:
      message = (
        f'After {played}, a still-possible layout beats the target outright.'
      )
    else:
      message = (
        f'After {played}, no single line handles every still-possible '
        f'layout — these lies can no longer all be covered at once.'
      )
    return ErrorReport(played, message, witnesses)
