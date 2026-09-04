# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

"""Suit-symbol markup in entered text.

Card JSON values write suits as `!c !d !h !s` (the Bridgodex convention).
Parsing splits a value into runs — plain text and single suit symbols — so the
overlay can give each run its own font and color.
"""

import re
from dataclasses import dataclass
from enum import Enum


class Suit(Enum):
  """A card suit; the value is the symbol the overlay prints.

  The heart and diamond print in their open forms, matching the monochrome
  card-print convention encoded by Unicode's default suit symbols. The rationale
  lives at spec.md #appearance.
  """

  SPADES = '♠'
  HEARTS = '♡'
  DIAMONDS = '♢'
  CLUBS = '♣'


_SUIT_BY_LETTER = {
  's': Suit.SPADES,
  'h': Suit.HEARTS,
  'd': Suit.DIAMONDS,
  'c': Suit.CLUBS,
}

# A bang introduces a suit only when a letter follows; a bare '!' (one not
# followed by a letter) is ordinary text, since entries may legitimately
# exclaim. An unknown letter is a loud error — it is almost certainly a mistyped
# suit.
_MARKUP_PATTERN = re.compile(r'!(?P<letter>[A-Za-z])')


@dataclass(frozen=True)
class TextRun:
  """A stretch of an entry rendered in one font and color.

  `suit` is None for plain text; for a suit run, `text` is the suit's printed
  symbol.
  """

  text: str
  suit: Suit | None = None


def parse_suit_markup(text: str) -> tuple[TextRun, ...]:
  """Split an entry value into plain-text and suit-symbol runs.

  Raises:
    ValueError: if a `!x` marker names no suit.
  """
  runs: list[TextRun] = []
  position = 0

  for match in _MARKUP_PATTERN.finditer(text):
    suit = _SUIT_BY_LETTER.get(match.group('letter').lower())
    if suit is None:
      raise ValueError(
        f'unknown suit letter {match.group(0)!r} in {text!r}'
        ' — expected one of !s !h !d !c'
      )
    if match.start() > position:
      runs.append(TextRun(text[position : match.start()]))
    runs.append(TextRun(suit.value, suit))
    position = match.end()

  if position < len(text):
    runs.append(TextRun(text[position:]))
  return tuple(runs)
