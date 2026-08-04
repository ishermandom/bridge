# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Exact solver for the quantum single-dummy game.

Declarer sees only the North-South cards plus whatever has hit the table; the
defenders commit to nothing beyond staying consistent with at least one layout
in the problem's family. `QuantumSolver.declarer_can_force` asks whether one
uniform declarer line reaches the trick target against every consistent defender
continuation — exhaustive search rather than per-layout double dummy, for the
reasons in ../spec.md #exact-solver.

Notrump only: a trick is won by the highest card of the suit led.
"""

from __future__ import annotations

import itertools
from collections.abc import Mapping
from dataclasses import dataclass, replace

from cards import Card, Seat, Suit
from problems import Layout, Problem


@dataclass(frozen=True)
class Position:
  """A game state, canonical enough to memoize on.

  The defenders' concrete holdings are deliberately absent. What the state
  carries instead is everything declarer could know: which defender cards have
  been seen (`west_played`, `east_played`) and which layouts remain consistent
  with the whole play so far (`surviving`, indices into the problem's layout
  family).
  """

  north: frozenset[Card]
  south: frozenset[Card]
  west_played: frozenset[Card]
  east_played: frozenset[Card]
  surviving: frozenset[int]
  leader: Seat
  # Plays so far in the current, incomplete trick (empty at a trick boundary).
  trick: tuple[tuple[Seat, Card], ...]
  declarer_tricks: int


def trick_winner(trick: tuple[tuple[Seat, Card], ...]) -> Seat:
  """The seat whose card wins a completed notrump trick."""
  led_suit = trick[0][1].suit
  winning_play = max(
    (play for play in trick if play[1].suit is led_suit),
    key=lambda play: play[1].rank,
  )
  return winning_play[0]


class QuantumSolver:
  """Game-tree search and play-policy queries over one problem.

  Search results are memoized on `Position`, so repeated queries across one
  interactive session (error checks, witness hunts, defender policy) share work.
  """

  def __init__(self, problem: Problem) -> None:
    self._problem = problem
    self._memo: dict[Position, bool] = {}

  def initial_position(self) -> Position:
    """The position before any card of the ending has been played."""
    return Position(
      north=self._problem.north,
      south=self._problem.south,
      west_played=frozenset(),
      east_played=frozenset(),
      surviving=frozenset(range(len(self._problem.layouts))),
      leader=self._problem.leader,
      trick=(),
      declarer_tricks=0,
    )

  def layout(self, index: int) -> Layout:
    """The family layout at `index` (as referenced by `Position.surviving`)."""
    return self._problem.layouts[index]

  # --- state mechanics ---

  def seat_to_play(self, position: Position) -> Seat:
    """Whose turn it is: the trick's leader, or after the last play."""
    if position.trick:
      return position.trick[-1][0].next_clockwise
    return position.leader

  def is_over(self, position: Position) -> bool:
    """Whether every card has been played."""
    return not position.trick and not (position.north | position.south)

  def _led_suit(self, position: Position) -> Suit | None:
    """The suit that must be followed, or None when leading to a trick."""
    if position.trick:
      return position.trick[0][1].suit
    return None

  def _declarer_hand(self, position: Position, seat: Seat) -> frozenset[Card]:
    return position.north if seat is Seat.NORTH else position.south

  def _defender_remaining(
    self, position: Position, layout_index: int, seat: Seat
  ) -> frozenset[Card]:
    """The cards `seat` still holds if the true layout is `layout_index`."""
    layout = self._problem.layouts[layout_index]
    if seat is Seat.WEST:
      return layout.west - position.west_played
    return layout.east - position.east_played

  def legal_declarer_cards(self, position: Position) -> frozenset[Card]:
    """The cards the declarer-side seat to play may legally choose."""
    seat = self.seat_to_play(position)
    if not seat.is_declarer_side:
      raise RuntimeError(f'{seat} to play; not a declarer-side turn')
    hand = self._declarer_hand(position, seat)
    led_suit = self._led_suit(position)
    following = frozenset(card for card in hand if card.suit is led_suit)
    return following if following else hand

  def defender_candidates(
    self, position: Position
  ) -> Mapping[Card, frozenset[int]]:
    """Each card the defender to play might legally hold, with the layouts that
    allow it.

    Playing a card commits the defense only to the returned layout subset:
    holding the card, and — when not following suit — being void in the led
    suit, both filter the family.
    """
    seat = self.seat_to_play(position)
    if seat.is_declarer_side:
      raise RuntimeError(f'{seat} to play; not a defender turn')
    led_suit = self._led_suit(position)
    allowing: dict[Card, set[int]] = {}
    for index in position.surviving:
      remaining = self._defender_remaining(position, index, seat)
      following = frozenset(c for c in remaining if c.suit is led_suit)
      legal = following if led_suit and following else remaining
      for card in legal:
        allowing.setdefault(card, set()).add(index)
    return {card: frozenset(indices) for card, indices in allowing.items()}

  def _advance(
    self,
    position: Position,
    seat: Seat,
    card: Card,
    surviving: frozenset[int],
  ) -> Position:
    """The position after `seat` plays `card`; legality already checked."""
    north = position.north - {card}
    south = position.south - {card}
    west_played = position.west_played
    east_played = position.east_played
    if seat is Seat.WEST:
      west_played = west_played | {card}
    elif seat is Seat.EAST:
      east_played = east_played | {card}

    trick = (*position.trick, (seat, card))
    if len(trick) < 4:
      return replace(
        position,
        north=north,
        south=south,
        west_played=west_played,
        east_played=east_played,
        surviving=surviving,
        trick=trick,
      )
    winner = trick_winner(trick)
    return replace(
      position,
      north=north,
      south=south,
      west_played=west_played,
      east_played=east_played,
      surviving=surviving,
      leader=winner,
      trick=(),
      declarer_tricks=position.declarer_tricks
      + (1 if winner.is_declarer_side else 0),
    )

  def play(self, position: Position, card: Card) -> Position:
    """Advance by one card from the seat to play, validating legality."""
    seat = self.seat_to_play(position)
    if seat.is_declarer_side:
      if card not in self.legal_declarer_cards(position):
        raise ValueError(f'{card} is not a legal play for {seat}')
      return self._advance(position, seat, card, position.surviving)
    allowed = self.defender_candidates(position).get(card)
    if not allowed:
      raise ValueError(f'{card} is not playable by {seat} in any layout')
    return self._advance(position, seat, card, allowed)

  def _tricks_remaining(self, position: Position) -> int:
    """How many tricks, counting the one in progress, are left to fight for."""
    any_layout = next(iter(position.surviving))
    cards_in_hands = (
      len(position.north)
      + len(position.south)
      + len(self._defender_remaining(position, any_layout, Seat.WEST))
      + len(self._defender_remaining(position, any_layout, Seat.EAST))
    )
    return (cards_in_hands + len(position.trick)) // 4

  # --- search ---

  def declarer_can_force(self, position: Position) -> bool:
    """Whether some uniform declarer line reaches the target from here.

    Uniform means the line branches only on what declarer has observed: at
    declarer turns one card must work for *all* surviving layouts at once (`any`
    over cards), while every legal defender reply must be survivable (`all` over
    the candidate cards of every surviving layout).
    """
    target = self._problem.target_tricks
    if position.declarer_tricks >= target:
      return True
    if position.declarer_tricks + self._tricks_remaining(position) < target:
      return False

    memoized = self._memo.get(position)
    if memoized is not None:
      return memoized

    seat = self.seat_to_play(position)
    if seat.is_declarer_side:
      result = any(
        self.declarer_can_force(
          self._advance(position, seat, card, position.surviving)
        )
        for card in self.legal_declarer_cards(position)
      )
    else:
      result = all(
        self.declarer_can_force(self._advance(position, seat, card, allowed))
        for card, allowed in self.defender_candidates(position).items()
      )
    self._memo[position] = result
    return result

  # --- policy queries built on the search ---

  def winning_declarer_cards(self, position: Position) -> frozenset[Card]:
    """The legal declarer cards that keep the target forceable."""
    return frozenset(
      card
      for card in self.legal_declarer_cards(position)
      if self.declarer_can_force(self.play(position, card))
    )

  def refuting_defender_cards(self, position: Position) -> frozenset[Card]:
    """Defender cards after which declarer can no longer force the target."""
    return frozenset(
      card
      for card, allowed in self.defender_candidates(position).items()
      if not self.declarer_can_force(
        self._advance(position, self.seat_to_play(position), card, allowed)
      )
    )

  def witness_layouts(self, position: Position) -> tuple[Layout, ...]:
    """A smallest set of surviving layouts the position cannot handle.

    One layout when even knowing the cards declarer falls short against it;
    otherwise a pair no uniform line covers at once — the signature of a lost
    squeeze, where each lie is beatable but not both blind. Empty when the
    position is still winnable.
    """
    if self.declarer_can_force(position):
      return ()
    indices = sorted(position.surviving)
    for index in indices:
      restricted = replace(position, surviving=frozenset({index}))
      if not self.declarer_can_force(restricted):
        return (self._problem.layouts[index],)
    for pair in itertools.combinations(indices, 2):
      restricted = replace(position, surviving=frozenset(pair))
      if not self.declarer_can_force(restricted):
        return tuple(self._problem.layouts[index] for index in pair)
    # Minimal unwinnable cores larger than two layouts are possible but rare;
    # fall back to naming the whole surviving family.
    return tuple(self._problem.layouts[index] for index in indices)
