# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Translate between how bridge is written down and the canonical values.

A sheet and a traveller state the same facts by different conventions: a result
as tricks beyond book or as overtricks, a holding as spaced ranks or as a run of
characters, a ten as `10` or as `T`, a par contract for one seat or for a whole
side. Downstream work needs one form to compare on, so everything written is
translated here into the canonical model's types.

What belongs here is pure, general-purpose translation — logic that depends only
on bridge notation, never on how a particular source lays out its document. So a
source's HTML structure stays in its parser, and a spelling peculiar to one
publisher stays with that publisher (see `acbl_notation`); nothing here knows
which source it is serving. Holding to that membership test is what keeps this
module from becoming a drawer of parser helpers.

Nothing is thrown away for being unreadable. A value a source declines to state
comes back as None; a value it states unreadably raises `NotationError`, which
the parsers catch per row and record as an `Issue` rather than losing the rest
of a capture (see travellers.py).
"""

import enum
import re
from collections.abc import Mapping, Sequence

from session_analysis import board_rotation, glyphs
from session_analysis.enums import (
  Direction,
  IssueSeverity,
  Penalty,
  Rank,
  Side,
  Strain,
  Suit,
  Vulnerability,
)
from session_analysis.models import (
  Card,
  Contract,
  Deal,
  Hand,
  Issue,
  PlayedContract,
  Result,
)
from session_analysis.travellers import DoubleDummyTricks

# Book is the first six tricks, which no contract scores. A contract's level is
# stated above book: a 4-level contract needs ten tricks, book plus four. Public
# — other modules need it to compute the tricks a contract requires.
BOOK = 6

# The suits of a hand, in the order every source lists them: highest-ranking
# first.
SUITS_HIGH_TO_LOW = (Suit.SPADES, Suit.HEARTS, Suit.DIAMONDS, Suit.CLUBS)

# Every strain in ascending order, which is the order the double-dummy tables
# walk them in. Named to sit beside `SUITS_HIGH_TO_LOW`, which runs the other
# way because that is the order a hand is printed in.
STRAINS_LOW_TO_HIGH = (
  Strain.CLUBS,
  Strain.DIAMONDS,
  Strain.HEARTS,
  Strain.SPADES,
  Strain.NOTRUMP,
)

# The seats, in the clockwise order a PBN deal and a printed diagram both use.
SEATS_CLOCKWISE = (
  Direction.NORTH,
  Direction.EAST,
  Direction.SOUTH,
  Direction.WEST,
)

# Every letter a contract's strain is written with. `NT` is the usual spelling
# of notrump; a bare `N` turns up wherever a source wants the strain one
# character wide, and means the same thing. Every capture spells the four suits
# by their initials, so one map serves them all.
STRAIN_BY_LETTER: Mapping[str, Strain] = {
  'NT': Strain.NOTRUMP,
  'N': Strain.NOTRUMP,
  'S': Strain.SPADES,
  'H': Strain.HEARTS,
  'D': Strain.DIAMONDS,
  'C': Strain.CLUBS,
}

# What the marks a written contract trails say about the opponents doubling it:
# `4HX` is doubled, `4HXX` redoubled, `4H` neither. Sources disagree on which
# mark to write — a PBN and the club's HTML trail an `X`, ACBL an asterisk —
# while all of them mean doubled by one mark and redoubled by two, so it is the
# count that carries the meaning and the mark is left to each parser's own
# pattern. Zero is a key too, so a pattern whose `X{0,2}` matched nothing needs
# no special case at its call site.
PENALTY_BY_MARK_COUNT: Mapping[int, Penalty] = {
  0: Penalty.NONE,
  1: Penalty.DOUBLED,
  2: Penalty.REDOUBLED,
}

# The pattern of a result token: a sign followed by one or more digits.
_RESULT_TOKEN_PATTERN = re.compile(r'(?P<sign>[+-])(?P<count>\d+)')

# Fold every dash glyph (see glyphs.DASHES) to an ASCII hyphen, so the token
# pattern needs to know only the one form a minus may be written with.
_DASH_TO_HYPHEN = str.maketrans(glyphs.DASHES, '-' * len(glyphs.DASHES))

# What the travellers write for a contract that came home with nothing to spare.
# The sheet has no such token: its makes are always counted from book.
_MADE_EXACTLY = '='

# A ten written in full, as the ACBL surfaces and the club's HTML print it. The
# canonical `Rank` spells it with a single character, so it is folded before the
# holding is read one character per card.
_PRINTED_TEN = '10'

# Every character a source marks a void with: an em dash in ACBL's rendered
# pages, a hyphen in its data, and nothing at all in the club's. ACBL's data
# writes a run of them rather than one, so a holding is a void when it holds no
# character but these.
_VOID_CHARACTERS = frozenset(glyphs.DASHES)

# The spellings the captures actually print, normalized to lowercase with
# punctuation dropped — so `N-S` and `NS` both arrive as `ns`.
_VULNERABILITY_SPELLINGS: Mapping[Vulnerability, frozenset[str]] = {
  Vulnerability.NONE: frozenset({'none'}),
  Vulnerability.NORTH_SOUTH: frozenset({'ns'}),
  Vulnerability.EAST_WEST: frozenset({'ew'}),
  Vulnerability.BOTH: frozenset({'both', 'all'}),
}


class NotationError(ValueError):
  """Something written down here could not be read.

  Distinct from a value a source legitimately declines to state: that is
  reported as `None`, not raised. This is raised for text that should have been
  readable and was not, which means the source's format has moved or the capture
  is damaged — either way a person needs to look.
  """


class ResultNotation(enum.StrEnum):
  """Which convention a written result follows.

  The two agree that `-N` is N tricks short of the contract, and part ways on
  one point only: what `+N` counts up from. Only the travellers write `=`.
  """

  # The BridgeMate 'American style' entry mode the handwritten sheets use. `+N`
  # is N tricks beyond book and says nothing about the contract, so `+6` is
  # twelve tricks whether it was written against `4S` or against `6C`.
  SHEET = 'sheet'
  # The standard notation every traveller source writes. `+N` is N tricks beyond
  # what the contract needed, so `4S +2` is twelve.
  TRAVELLER = 'traveller'


def tricks_taken(
  result: str, *, contract_level: int, written_as: ResultNotation
) -> int:
  """Return the tricks declarer took, from a written result token.

  Translation only: this does not judge whether the level or the resulting trick
  count is a legal bridge value — that is the caller's responsibility — and it
  raises only when the token cannot be read at all.

  Args:
    result: the token as written, e.g. `+6`, `-2`, or a traveller's `=`. A minus
      may be any of several dash glyphs (see glyphs.DASHES); surrounding space
      is ignored.
    contract_level: the contract's level, which every form is relative to except
      the sheet's `+N`.
    written_as: which convention `result` follows; `ResultNotation` says what
      the two disagree about.

  Returns:
    The number of tricks declarer took.

  Raises:
    NotationError: if result is not a token this notation writes.
  """
  # Fold every dash variant to an ASCII hyphen so all spellings parse alike: a
  # sheet or traveller may be written, or transcribed, with any of them.
  token = result.strip().translate(_DASH_TO_HYPHEN)
  tricks_the_contract_needed = contract_level + BOOK

  if token == _MADE_EXACTLY and written_as is ResultNotation.TRAVELLER:
    return tricks_the_contract_needed

  match = _RESULT_TOKEN_PATTERN.fullmatch(token)
  if not match:
    raise NotationError(f'malformed {written_as} result token: {result!r}')

  count = int(match.group('count'))
  if match.group('sign') == '-':
    # Both notations count a set down from the tricks the contract needed.
    return tricks_the_contract_needed - count
  # The one place they differ.
  if written_as is ResultNotation.SHEET:
    return BOOK + count
  return tricks_the_contract_needed + count


def tricks_taken_from_par_result(result: str, level: int) -> int | None:
  """Return the trick count a par contract's result token states.

  Par results come in the three forms the sources print: `=` for making exactly,
  `+N` for overtricks, and `-N` for a sacrifice going down. An empty token means
  the source stated no result, which is reported as None rather than guessed at
  — `par_contracts` recovers it from the double-dummy table.

  Args:
    result: the token as written, e.g. `=`, `+2`, `-4`. A minus may be any dash
      glyph (see glyphs.DASHES).
    level: the contract's level.

  Raises:
    NotationError: if the token is not one of the three forms.
  """
  token = result.strip()
  if not token:
    return None
  return tricks_taken(
    token, contract_level=level, written_as=ResultNotation.TRAVELLER
  )


def hand_from_holdings(holdings: Sequence[str]) -> Hand:
  """Return the `Hand` a source's four suit holdings describe.

  Args:
    holdings: four holdings, whose suits are fixed by their position: spades,
      hearts, diamonds, clubs. Every source prints them in that order today, so
      a parser passes them straight through; one that printed them another way
      would reorder before calling. Each holding is the ranks held in that suit,
      with or without separating spaces (`A J 10 9 4`, `AJT94`), a ten written
      either way, and a void written as any dash or as nothing at all.

  Raises:
    NotationError: if a holding contains something that is not a rank.
  """
  if len(holdings) != len(SUITS_HIGH_TO_LOW):
    raise NotationError(
      f'expected {len(SUITS_HIGH_TO_LOW)} suit holdings, got '
      f'{len(holdings)}: {list(holdings)!r}'
    )

  cards: list[Card] = []
  for suit, holding in zip(SUITS_HIGH_TO_LOW, holdings, strict=True):
    # Fold the two-character ten to its single-character canonical rank, so what
    # remains is exactly one character per card.
    compact = holding.strip().replace(' ', '').replace(_PRINTED_TEN, Rank.TEN)
    if all(character in _VOID_CHARACTERS for character in compact):
      # Nothing but dashes, or nothing at all: the player held no card in this
      # suit.
      continue
    for rank in compact:
      try:
        cards.append(Card(rank=Rank(rank.upper()), suit=suit))
      except ValueError as error:
        raise NotationError(
          f'unreadable rank {rank!r} in {suit.name.lower()} holding {holding!r}'
        ) from error

  return Hand(cards=tuple(cards))


def deal_from_hands(hands: Mapping[Direction, Hand]) -> Deal:
  """Return the `Deal` these hands make up, requiring one hand per seat.

  Well-formedness beyond that — fifty-two distinct cards, thirteen to a hand —
  is left to reconciliation, which surfaces a malformed deal for review rather
  than refusing to store it.

  Raises:
    NotationError: if a seat is missing a hand.
  """
  missing = [seat for seat in SEATS_CLOCKWISE if seat not in hands]
  if missing:
    raise NotationError(f'deal is missing a hand for {", ".join(missing)}')
  return Deal(hands=dict(hands))


def declarer_from_token(token: str) -> Direction | Side:
  """Return the seat or side a declarer token names.

  Every source writes a declarer as either a single seat (`N`) or a whole side
  (`NS`), differing only in the case they print it in.

  Raises:
    ValueError: if the token names neither a seat nor a side.
  """
  spelled = token.strip().upper()
  if spelled in tuple(Side):
    return Side(spelled)
  return Direction(spelled)


def par_contracts(
  *,
  level: int,
  strain: Strain,
  penalty: Penalty,
  declarer: Direction | Side,
  stated_tricks: int | None,
  double_dummy_tricks: DoubleDummyTricks | None,
) -> Sequence[PlayedContract]:
  """Return one par contract per seat that achieves it.

  A source states par either for a seat (`4H-E`) or for a whole side (`4S-EW`).
  A side means both of its seats reach the score, so a side-level statement
  expands to one contract per seat: verbose, but it spares every reader the
  special case, and `Contract.declarer` is a single seat besides.

  The result is recovered where a source omits it, which the ACBL surfaces do
  whenever par makes exactly. A contract's double-dummy trick count is its
  declarer's makeable tricks in that strain — true of a sacrifice as much as of
  a making contract — so the table supplies what the source left out.

  Args:
    level: the contract level, 1-7.
    strain: what par is played in.
    penalty: whether par is doubled — a sacrifice usually is.
    declarer: the seat, or the side whose seats both achieve par.
    stated_tricks: the result the source stated, as a trick count, or None to
      recover it from `double_dummy_tricks`.
    double_dummy_tricks: the board's trick table, used only for that recovery.

  Raises:
    NotationError: if the result was neither stated nor recoverable.
  """
  seats = declarer.seats if isinstance(declarer, Side) else (declarer,)

  contracts: list[PlayedContract] = []
  for seat in seats:
    seat_tricks = stated_tricks
    if seat_tricks is None:
      seat_tricks = _double_dummy_by(double_dummy_tricks, seat, strain)
    if seat_tricks is None:
      raise NotationError(
        f'par contract {level}{strain} by {seat} states no result, and the '
        f'double-dummy table supplies none to recover it from'
      )
    contracts.append(
      PlayedContract(
        contract=Contract(
          level=level, strain=strain, declarer=seat, penalty=penalty
        ),
        result=Result(tricks_taken=seat_tricks),
      )
    )

  return tuple(contracts)


def _double_dummy_by(
  double_dummy_tricks: DoubleDummyTricks | None, seat: Direction, strain: Strain
) -> int | None:
  """The double-dummy tricks a seat takes in a strain, when the table says."""
  if not double_dummy_tricks:
    return None
  return double_dummy_tricks.get(seat, {}).get(strain)


def board_schedule_issues(
  *,
  board_number: int,
  dealer: Direction | None,
  vulnerability: str | None,
) -> Sequence[Issue]:
  """Report a printed dealer or vulnerability that contradicts the board number.

  Both follow from the board number under the standard schedule, so neither is
  stored (see board_rotation). What a source prints is therefore not new
  information — but a contradiction is, because the likely cause is that the
  board number was read off the wrong part of the capture, which would put
  everything else about the board against the wrong deal.

  This check has to run while parsing, unlike the deal's own well-formedness: it
  compares the source's text against a derived value, and the text is not kept,
  so nothing downstream could repeat it.

  Args:
    board_number: the board number the parser assigned.
    dealer: the dealer the source printed, or None if it printed none.
    vulnerability: the vulnerability the source printed, in the source's own
      spelling; compared case- and punctuation-insensitively against the
      computed value, since every source spells it differently.
  """
  issues: list[Issue] = []

  scheduled_dealer = board_rotation.dealer_for_board(board_number)
  if dealer and dealer != scheduled_dealer:
    issues.append(
      Issue(
        code='dealer_contradicts_board_number',
        severity=IssueSeverity.HIGH,
        message=(
          f'board {board_number} prints dealer {dealer}, but the schedule '
          f'gives {scheduled_dealer} — the board number may have been read '
          f'from the wrong place'
        ),
        location='dealer',
      )
    )

  if vulnerability is None:
    return issues
  scheduled = board_rotation.vulnerability_for_board(board_number)
  # Sources spell the same value as `None`/`none`, `N-S`/`NS`, `All`/`Both`, so
  # compare on a form that drops the punctuation and the case.
  printed = vulnerability.replace('-', '').replace(' ', '').lower()
  if printed not in _VULNERABILITY_SPELLINGS[scheduled]:
    issues.append(
      Issue(
        code='vulnerability_contradicts_board_number',
        severity=IssueSeverity.HIGH,
        message=(
          f'board {board_number} prints vulnerability {vulnerability!r}, but '
          f'the schedule gives {scheduled} — the board number may have been '
          f'read from the wrong place'
        ),
        location='vulnerability',
      )
    )
  return issues
