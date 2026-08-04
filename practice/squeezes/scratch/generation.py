# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Generate certified automatic-simple-squeeze endings.

Instantiates the classic matrix (../spec.md #generation) with randomized suit
roles and spot cards. Schematically, before randomization (a 5-card ending, `x`
marking idle cards):

```text
        North: ♠A6 xxx      (two-card threat under its ace entry, plus idles
                             to throw on the run)
        South: ♣AKQ ♥K ♠3   (the run, the one-card threat, a link to dummy)
    Squeezed defender: ♠KQ ♥A + idles; the other defender: all idles.
```

The last card of the run squeezes whichever defender holds all three guards:
throwing the ♥A establishes South's ♥K, and throwing a spade lets the ♠A fell
the remaining guard to promote North's ♠6. The layout family deals the guards to
West in some layouts and to East in others, with idle cards split several ways,
so only the full squeeze line — keep both threats, cash the run, read the
discard — wins against every layout.

Every generated problem is certified by the exact solver before it is returned;
see `CertificationError`.
"""

from __future__ import annotations

import itertools
import random
from dataclasses import dataclass, replace

from cards import SUITS_HIGH_TO_LOW, Card, Rank, Seat, Suit
from problems import Layout, Problem
from solver import QuantumSolver


class CertificationError(Exception):
  """A generated position failed its solver certification.

  Raised loudly rather than retried: the template is meant to certify by
  construction, so a failure signals a generator bug worth surfacing.
  """


@dataclass(frozen=True)
class GeneratedProblem:
  """A certified problem plus teaching metadata revealed post-mortem."""

  problem: Problem
  summary: str
  # The busy cards — both threats' guards — that one defender holds entire.
  guard_cards: frozenset[Card]


def generate_automatic_simple_squeeze(
  rng: random.Random, ending_size: int = 5
) -> GeneratedProblem:
  """Deal one certified automatic simple squeeze ending.

  `ending_size` is cards per hand, 3–6: size 3 is the bare matrix; larger sizes
  prepend winners to the run, adding idle-card discards for both North and the
  defenders before the squeeze bites.
  """
  if not 3 <= ending_size <= 6:
    raise ValueError(f'ending_size must be 3–6, got {ending_size}')
  size = ending_size

  suits = list(SUITS_HIGH_TO_LOW)
  rng.shuffle(suits)
  run_suit, south_threat_suit, north_threat_suit, idle_suit = suits

  # The run: South's top winners, the last of which is the squeeze card.
  run_winners = [
    Card(run_suit, rank)
    for rank in (Rank.ACE, Rank.KING, Rank.QUEEN, Rank.JACK)[: size - 2]
  ]

  # One-card threat: South's king, guarded only by the missing ace.
  south_threat = Card(south_threat_suit, Rank.KING)
  south_threat_guard = Card(south_threat_suit, Rank.ACE)

  # Two-card threat: North's low card under its ace entry. The guards are any
  # two defender cards above the low threat; South's link card (below the low
  # threat) reaches the entry after the guards fall.
  north_entry = Card(north_threat_suit, Rank.ACE)
  low_threat_rank = Rank(rng.randint(Rank.FIVE, Rank.EIGHT))
  north_low_threat = Card(north_threat_suit, low_threat_rank)
  guard_ranks = rng.sample(
    [Rank(value) for value in range(low_threat_rank + 1, Rank.ACE)], 2
  )
  north_threat_guards = [
    Card(north_threat_suit, rank) for rank in guard_ranks
  ]
  south_link = Card(north_threat_suit, Rank(rng.randint(Rank.TWO, Rank.FOUR)))

  south = frozenset(run_winners) | {south_threat, south_link}
  guards = frozenset({south_threat_guard, *north_threat_guards})

  # Idle pools, stratified by rank so a spare card never quietly grows into a
  # winner: North's idles stop at the four while defender idles in the same
  # suits start at the five, so whatever spare North keeps to the very end, the
  # defense still holds a higher card of its suit. The cover in the south-threat
  # suit is free (the guard ace tops everything), so two high idle-suit cards go
  # to the defense unconditionally to guarantee the other one. North avoids the
  # run suit so every run trick poses a real discard choice; defenders may hold
  # low run-suit cards, following under the winners. Neither pool touches the
  # north-threat suit, so the two dealt guards are that suit's only defenders.
  north_idle_pool = _cards(idle_suit, Rank.TWO, Rank.FOUR) + _cards(
    south_threat_suit, Rank.TWO, Rank.FOUR
  )
  north_idles = rng.sample(north_idle_pool, size - 2)
  cover_cards = rng.sample(_cards(idle_suit, Rank.FIVE, Rank.NINE), 2)
  defender_idle_pool = [
    card
    for card in _cards(idle_suit, Rank.FIVE, Rank.NINE)
    + _cards(south_threat_suit, Rank.FIVE, Rank.NINE)
    + _cards(run_suit, Rank.TWO, Rank.SIX)
    if card not in cover_cards
  ]
  defender_idles = cover_cards + rng.sample(defender_idle_pool, 2 * size - 5)

  north = frozenset({north_entry, north_low_threat, *north_idles})
  defender_pool = guards | frozenset(defender_idles)

  layouts = _guard_side_layouts(rng, guards, defender_idles, size)
  problem = Problem(
    north=north,
    south=south,
    layouts=tuple(layouts),
    leader=Seat.SOUTH,
    target_tricks=size,
  )
  _certify(problem, guards, defender_pool, size)

  summary = (
    f'Automatic simple squeeze: run the {run_suit.glyph}s and watch the '
    f'discards. Threats: {south_threat} with South and {north_low_threat} '
    f'with North behind the {north_entry} entry; one defender holds '
    f'{south_threat_guard} and both {north_threat_suit.glyph} guards, so '
    f'the last run winner squeezes them whichever side they sit.'
  )
  return GeneratedProblem(problem, summary, guards)


def _cards(suit: Suit, low: Rank, high: Rank) -> list[Card]:
  """All cards of `suit` from `low` to `high` inclusive, ascending."""
  return [Card(suit, Rank(value)) for value in range(low, high + 1)]


def _guard_side_layouts(
  rng: random.Random,
  guards: frozenset[Card],
  defender_idles: list[Card],
  size: int,
) -> list[Layout]:
  """Layouts placing the guards with either defender, idle splits varied."""
  idle_splits = list(itertools.combinations(defender_idles, size - 3))
  chosen_splits = rng.sample(idle_splits, min(3, len(idle_splits)))
  layouts = []
  for squeezed_seat in (Seat.WEST, Seat.EAST):
    for split in chosen_splits:
      squeezed_hand = guards | frozenset(split)
      other_hand = frozenset(defender_idles) - frozenset(split)
      if squeezed_seat is Seat.WEST:
        layouts.append(Layout(west=squeezed_hand, east=other_hand))
      else:
        layouts.append(Layout(west=other_hand, east=squeezed_hand))
  return layouts


def _certify(
  problem: Problem,
  guards: frozenset[Card],
  defender_pool: frozenset[Card],
  size: int,
) -> None:
  """Prove the problem drills a squeeze; raise `CertificationError` if not.

  Three certificates, per ../spec.md #generation: a uniform winning line exists;
  the family poses the guards on both sides; and splitting the guards between
  the defenders makes the position unwinnable, proving the win rides on one
  defender holding every guard.
  """
  solver = QuantumSolver(problem)
  if not solver.declarer_can_force(solver.initial_position()):
    raise CertificationError(f'no uniform winning line exists: {problem}')

  has_west_guarding = any(guards <= layout.west for layout in problem.layouts)
  has_east_guarding = any(guards <= layout.east for layout in problem.layouts)
  if not (has_west_guarding and has_east_guarding):
    raise CertificationError(
      f'guards {guards} must appear on both sides across the family'
    )

  split_problem = replace(
    problem, layouts=problem.layouts + (_split_guard_layout(guards, defender_pool, size),)
  )
  split_solver = QuantumSolver(split_problem)
  if split_solver.declarer_can_force(split_solver.initial_position()):
    raise CertificationError(
      f'position is winnable even with guards split between the defenders — '
      f'the winning line is not (only) a squeeze: {problem}'
    )


def _split_guard_layout(
  guards: frozenset[Card],
  defender_pool: frozenset[Card],
  size: int,
) -> Layout:
  """A layout dividing the guards between the defenders, no squeeze possible.

  West takes the one-card-threat guard (the lone ace among the guards) and East
  the two-card-threat guards, idle cards filling both hands to size.
  """
  lone_ace = frozenset(card for card in guards if card.rank is Rank.ACE)
  idles = sorted(defender_pool - guards, key=lambda c: (c.suit.value, c.rank))
  west = lone_ace | frozenset(idles[: size - 1])
  east = defender_pool - west
  return Layout(west=west, east=east)
