# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Parsing one hand's holding, as the suit-combination input file writes it.

The notation is specified in `anki/spec.md` #holding-notation. Parsing accepts
each spelling the input file allows and normalizes it, so equal holdings always
print the same canonical form — the form that feeds each card's identity.
"""

import enum
import itertools
from collections.abc import Mapping
from dataclasses import dataclass


class Card(enum.StrEnum):
  """One card in a holding, as the notation writes it, highest first."""

  ACE = 'A'
  KING = 'K'
  QUEEN = 'Q'
  JACK = 'J'
  TEN = 'T'
  NINE = '9'
  EIGHT = '8'
  SEVEN = '7'
  SIX = '6'
  FIVE = '5'
  FOUR = '4'
  THREE = '3'
  TWO = '2'
  # A spot whose exact rank doesn't matter, so it ranks below every named card.
  SMALL = 'x'


# Each card's position in the notation's high-to-low order, from 0 for the ace.
_HIGH_TO_LOW_POSITION: Mapping[Card, int] = {
  card: position for position, card in enumerate(Card)
}

# The canonical spelling of a void.
_VOID_NOTATION = '(void)'

# Every spelling of a void the input file accepts, once spaces are removed.
_VOID_SPELLINGS = frozenset({'', '-', 'v', 'void', _VOID_NOTATION})

# The number of cards in a suit, and so the most any holding can have.
SUIT_SIZE = 13


@dataclass(frozen=True)
class Holding:
  """One hand's cards in a suit, high to low; empty for a void."""

  cards: tuple[Card, ...]

  def __str__(self) -> str:
    """The canonical notation, such as `AQTx` or `(void)`."""
    if not self.cards:
      return _VOID_NOTATION
    return ''.join(self.cards)


def parse_holding(text: str) -> Holding:
  """Parse one hand's holding from the input file's notation.

  Raises `ValueError` when the text names an unknown card, lists its cards out
  of high-to-low order or names one twice, or has more cards than a suit holds.
  """
  # Spacing is cosmetic, so it never distinguishes two holdings.
  compact = ''.join(text.split())
  if compact in _VOID_SPELLINGS:
    return Holding(cards=())

  # The input file may write a ten as `10`, the one card spelled with two
  # symbols.
  symbols = compact.replace('10', Card.TEN)
  cards = tuple(_parse_card(symbol, text) for symbol in symbols)
  if len(cards) > SUIT_SIZE:
    raise ValueError(
      f'Holding {text!r} has {len(cards)} cards; a suit has only {SUIT_SIZE}'
    )

  for higher, lower in itertools.pairwise(cards):
    # Small cards may repeat; each named card appears at most once.
    is_repeated_small = higher is Card.SMALL and lower is Card.SMALL
    is_in_order = _HIGH_TO_LOW_POSITION[lower] > _HIGH_TO_LOW_POSITION[higher]
    if not is_repeated_small and not is_in_order:
      raise ValueError(
        f'{lower} follows {higher} in holding {text!r}; list cards high to low,'
        ' naming each at most once'
      )
  return Holding(cards=cards)


def _parse_card(symbol: str, holding_text: str) -> Card:
  """The card that one symbol of the notation names."""
  try:
    return Card(symbol)
  except ValueError:
    raise ValueError(
      f'Unknown card {symbol!r} in holding {holding_text!r}; cards are'
      ' A K Q J T 9-2 (or 10 for T), and x for a small card'
    ) from None
