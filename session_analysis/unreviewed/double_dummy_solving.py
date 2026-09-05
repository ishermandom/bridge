# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Solving a deal for the tricks one particular opening lead leaves behind.

A published double-dummy table states what best play by both sides yields, and
best play by the defense includes its choice of lead — so a table answers what
the *best* lead holds declarer to and nothing about any other. The lead actually
made leaves a different position, and reading which one it left is a search
rather than a lookup. That search is what this module runs.

It is the project's only seam onto a double-dummy solver. Everything else states
the question in this project's own terms — a `Deal`, a `Direction`, a `Strain`,
a `Card` — and this module alone knows how the solver spells them. Keeping the
adaptation in one place is what makes the solver replaceable: `endplay` bundles
Bo Haglund's DDS and is the only Python package that ships it in a usable form
today, but it is a thin ctypes wrapper over a C library that has since moved on
without it, so the day may come to swap it.

The count that comes back is declarer's, as a published table's cells are, so
the two compare directly and their difference is what the opening lead cost.
"""

import collections
from collections.abc import Mapping, Sequence

import endplay.dds
import endplay.types

from session_analysis.enums import Direction, Rank, Strain, Suit
from session_analysis.models import Card, Deal, Hand

_SOLVER_SEATS: Mapping[Direction, endplay.types.Player] = {
  Direction.NORTH: endplay.types.Player.north,
  Direction.EAST: endplay.types.Player.east,
  Direction.SOUTH: endplay.types.Player.south,
  Direction.WEST: endplay.types.Player.west,
}

_SOLVER_STRAINS: Mapping[Strain, endplay.types.Denom] = {
  Strain.CLUBS: endplay.types.Denom.clubs,
  Strain.DIAMONDS: endplay.types.Denom.diamonds,
  Strain.HEARTS: endplay.types.Denom.hearts,
  Strain.SPADES: endplay.types.Denom.spades,
  Strain.NOTRUMP: endplay.types.Denom.nt,
}

# The seats a written deal names in turn, and the suits each hand writes in
# turn. Both orders are the notation's rather than ours, so they are spelled out
# here instead of taken from the enums' own declaration order.
_WRITTEN_SEATS = (
  Direction.NORTH,
  Direction.EAST,
  Direction.SOUTH,
  Direction.WEST,
)
_WRITTEN_SUITS = (Suit.SPADES, Suit.HEARTS, Suit.DIAMONDS, Suit.CLUBS)

# Where each rank falls when a suit is written high card first. `Rank` declares
# its members the other way up, so the order is reversed once here rather than
# at each hand.
_RANK_ORDER: Mapping[Rank, int] = {
  rank: position for position, rank in enumerate(reversed(list(Rank)))
}


def tricks_after_lead(
  deal: Deal,
  *,
  declarer: Direction,
  strain: Strain,
  opening_lead: Card,
) -> int:
  """Declarer's tricks with best play by both sides after that opening lead.

  Args:
    deal: the four hands, which must be well formed — four seats, thirteen
      cards each, no card twice.
    declarer: the seat that played the contract. Who leads follows from it,
      being the seat to its left.
    strain: what the contract was played in.
    opening_lead: the card actually led, which must be in the leading hand.

  Returns:
    How many of the thirteen tricks declarer takes, counting from the position
    the lead leaves rather than from the start of the deal.

  Raises:
    KeyError: if the deal states no hand for some seat.
    endplay._dds.DDSError: if the deal is malformed or the lead is not in the
      leading hand.

  Both preconditions are checked, and reported as issues, by
  `deal_checks.find_deal_issues` and `deal_checks.find_lead_issues`. This raises
  rather than repeating those checks, so that a caller which skipped them hears
  about it instead of receiving a number that means nothing.
  """
  position = endplay.types.Deal(
    _written_deal(deal), first=_SOLVER_SEATS[declarer.left_hand_opponent]
  )
  position.trump = _SOLVER_STRAINS[strain]

  # The solver reports the position before the first card and after each one, so
  # a single lead comes back as two counts and the second is the one wanted.
  # Unpacking rather than indexing is what holds it to two: a solver that
  # answered otherwise would be doing something this has misunderstood.
  _, after_lead = endplay.dds.analyse_play(
    position, [_written_card(opening_lead)]
  )
  # The solver's result type carries no element annotation, so the count arrives
  # untyped. Converting narrows it here, at the one boundary this project has
  # onto the library, rather than letting an unchecked value travel on as though
  # it had been verified.
  return int(after_lead)


def _written_deal(deal: Deal) -> str:
  """The deal as the solver spells one: four hands, from North clockwise."""
  hands = ' '.join(_written_hand(deal.hands[seat]) for seat in _WRITTEN_SEATS)
  return f'N:{hands}'


def _written_hand(hand: Hand) -> str:
  """One hand as its four suits, each high card first, in the written order.

  A void is written as the empty string between its dots, which is what falls
  out of grouping by suit and joining — the suit simply contributes nothing.
  """
  # A default dictionary rather than a plain one, so that the void suits below
  # answer with an empty list instead of raising.
  by_suit: collections.defaultdict[Suit, list[Card]] = collections.defaultdict(
    list
  )
  for card in hand.cards:
    by_suit[card.suit].append(card)

  return '.'.join(
    ''.join(card.rank.value for card in _high_to_low(by_suit[suit]))
    for suit in _WRITTEN_SUITS
  )


def _high_to_low(cards: Sequence[Card]) -> Sequence[Card]:
  """One suit's cards, ace first, as a written hand orders them."""
  return sorted(cards, key=lambda card: _RANK_ORDER[card.rank])


def _written_card(card: Card) -> str:
  """A card as the solver spells one: its suit, then its rank."""
  # Both halves are already the letters the solver reads — a ten is `T` on both
  # sides — so the spelling is a concatenation rather than a translation.
  return f'{card.suit.value}{card.rank.value}'
