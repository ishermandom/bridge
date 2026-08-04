# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Card vocabulary for the squeeze trainer: suits, ranks, cards, and seats.

Only what notrump endings need: cards compare by rank within a suit, seats
rotate clockwise, and North–South is the declaring side. Kept independent of
`session_analysis`'s models while this prototype lives in scratch; unifying the
vocabularies is a graduation question (see ../spec.md #architecture).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class Suit(enum.Enum):
  """A card suit, valued by its one-letter notation."""

  SPADES = 'S'
  HEARTS = 'H'
  DIAMONDS = 'D'
  CLUBS = 'C'

  @property
  def glyph(self) -> str:
    """The suit's display symbol, e.g. `♠`."""
    return _SUIT_GLYPHS[self]


_SUIT_GLYPHS = {
  Suit.SPADES: '\N{BLACK SPADE SUIT}',
  Suit.HEARTS: '\N{BLACK HEART SUIT}',
  Suit.DIAMONDS: '\N{BLACK DIAMOND SUIT}',
  Suit.CLUBS: '\N{BLACK CLUB SUIT}',
}

# Display and sorting convention: spades first, clubs last.
SUITS_HIGH_TO_LOW = (Suit.SPADES, Suit.HEARTS, Suit.DIAMONDS, Suit.CLUBS)


class Rank(enum.IntEnum):
  """A card rank; comparisons follow trick-taking power (ace high)."""

  TWO = 2
  THREE = 3
  FOUR = 4
  FIVE = 5
  SIX = 6
  SEVEN = 7
  EIGHT = 8
  NINE = 9
  TEN = 10
  JACK = 11
  QUEEN = 12
  KING = 13
  ACE = 14

  @property
  def symbol(self) -> str:
    """The rank's one-character notation: `2`–`9`, `T`, `J`, `Q`, `K`, `A`."""
    return '23456789TJQKA'[self - Rank.TWO]


_RANK_BY_SYMBOL = {rank.symbol: rank for rank in Rank}


@dataclass(frozen=True)
class Card:
  """One playing card."""

  suit: Suit
  rank: Rank

  @classmethod
  def from_code(cls, code: str) -> Card:
    """Parse two-character notation, suit letter then rank symbol: `SA`, `H7`."""
    if len(code) != 2:
      raise ValueError(f'not a two-character card code: {code!r}')
    try:
      suit = Suit(code[0])
    except ValueError:
      raise ValueError(f'unknown suit letter in card code: {code!r}') from None
    try:
      rank = _RANK_BY_SYMBOL[code[1]]
    except KeyError:
      raise ValueError(f'unknown rank symbol in card code: {code!r}') from None
    return cls(suit, rank)

  @property
  def code(self) -> str:
    """The card's two-character notation, the inverse of `from_code`."""
    return self.suit.value + self.rank.symbol

  def __str__(self) -> str:
    return self.suit.glyph + self.rank.symbol


class Seat(enum.Enum):
  """A position at the table, valued by its compass letter."""

  NORTH = 'N'
  EAST = 'E'
  SOUTH = 'S'
  WEST = 'W'

  @property
  def next_clockwise(self) -> Seat:
    """The seat that plays after this one."""
    return _NEXT_CLOCKWISE[self]

  @property
  def is_declarer_side(self) -> bool:
    """Whether this seat is played by the user (North–South declares)."""
    return self in (Seat.NORTH, Seat.SOUTH)


_NEXT_CLOCKWISE = {
  Seat.NORTH: Seat.EAST,
  Seat.EAST: Seat.SOUTH,
  Seat.SOUTH: Seat.WEST,
  Seat.WEST: Seat.NORTH,
}
