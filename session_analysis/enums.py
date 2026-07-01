# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Bounded value sets for the bridge domain.

String-valued so they serialize directly to and from the canonical JSON. This
module holds the shared vocabulary; more sets join it as the models that use
them arrive.
"""

import enum


class Direction(enum.StrEnum):
  """A seat at the table — and so a dealer or declarer."""

  NORTH = 'N'
  EAST = 'E'
  SOUTH = 'S'
  WEST = 'W'


class Vulnerability(enum.StrEnum):
  """Which side is vulnerable on a board."""

  NONE = 'none'
  NORTH_SOUTH = 'NS'
  EAST_WEST = 'EW'
  BOTH = 'both'


class Strain(enum.StrEnum):
  """What a bid or contract is played in — a suit or notrump."""

  CLUBS = 'C'
  DIAMONDS = 'D'
  HEARTS = 'H'
  SPADES = 'S'
  NOTRUMP = 'NT'


class Suit(enum.StrEnum):
  """A card's suit (no notrump, unlike a strain)."""

  CLUBS = 'C'
  DIAMONDS = 'D'
  HEARTS = 'H'
  SPADES = 'S'


class Rank(enum.StrEnum):
  """A card's rank."""

  TWO = '2'
  THREE = '3'
  FOUR = '4'
  FIVE = '5'
  SIX = '6'
  SEVEN = '7'
  EIGHT = '8'
  NINE = '9'
  TEN = 'T'
  JACK = 'J'
  QUEEN = 'Q'
  KING = 'K'
  ACE = 'A'


class Penalty(enum.StrEnum):
  """A doubling applied to a contract."""

  NONE = 'none'
  DOUBLED = 'doubled'
  REDOUBLED = 'redoubled'


class CallKind(enum.StrEnum):
  """What kind of call a player made."""

  BID = 'bid'
  PASS = 'pass'
  DOUBLE = 'double'
  REDOUBLE = 'redouble'


class AnnouncementType(enum.StrEnum):
  """The meaning an announcement conveys about a bid."""

  ARTIFICIAL_SUIT = 'artificial_suit'
  MIN_SUIT_LENGTH = 'min_suit_length'
  FORCING = 'forcing'
  SEMI_FORCING = 'semi_forcing'
  NT_RANGE = 'nt_range'
  OTHER = 'other'


class IssueSeverity(enum.StrEnum):
  """How strongly an issue should pull a board up the review queue."""

  LOW = 'low'
  MEDIUM = 'medium'
  HIGH = 'high'
