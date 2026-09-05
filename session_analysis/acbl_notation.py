# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Translate the notations ACBL's result pages write.

ACBL publishes club games and tournaments through different software, but both
state the deal's analysis the same way, so the double-dummy and par notations
are read here once for both parsers. Their markup is what differs, and that
stays in the parser modules.

Two things about ACBL's double-dummy line are worth stating plainly, because
neither is guessable from the text:

- The number changes meaning with its position. `4S` — the number first — is the
  *level* a seat can make, six tricks fewer than the count. `S4` — the number
  last — is the *trick count* itself, which ACBL switches to for a side that
  takes fewer than seven tricks and so has no makeable contract to name. The
  page states this in its own tooltip. Where the Palo Alto club's HTML states
  only the contracts that make, ACBL states the low cells too — so its table is
  the fuller of the two.
- A side whose two seats straddle seven tricks has its strain stated twice, once
  in each form: `1/-S` says one seat makes a spade contract and the other makes
  none, and `S7/6` then gives both seats' counts exactly. Only a seat no cell
  states a count for stays `None`.
- A slash splits the two seats of the side, in the order the side is named:
  `3/4D` under `NS` means North makes three diamonds and South four.

A line this module cannot read raises `AcblNotationError`, which both parsers
catch per board and record as an `Issue` rather than losing the rest of a
capture — the same contract `notation` holds to, and for the same reason.
"""

import re
from collections.abc import Mapping

from session_analysis import notation
from session_analysis.enums import Direction, Side, Strain
from session_analysis.models import Resolution
from session_analysis.notation import BOOK
from session_analysis.travellers import DoubleDummyTricks, Par

# The pieces the patterns below are composed from. The strain comes from
# `notation` in its group-free form, since a double-dummy cell names one twice.

_LEVEL = r'[\d-]'  # a makeable level, or a dash for a seat that makes none
_TRICK_COUNT = r'\d'


def _for_each_seat(value: str) -> str:
  """The pattern for a value a double-dummy cell states for both seats.

  It is written once where the two seats agree and twice, split by a slash,
  where they differ — `5` and `7/6` are each a whole cell's worth.
  """
  return rf'{value}(?:/{value})?'


_MAKEABLE_LEVELS = _for_each_seat(_LEVEL)
_TRICK_COUNTS = _for_each_seat(_TRICK_COUNT)

# A double-dummy cell, in whichever of the two forms it was written: the level
# first — `4S`, `1/-S` — or the trick count last — `S4`, `S7/6`.
_MAKEABLE_PATTERN = re.compile(
  rf"""
  (?P<levels>{_MAKEABLE_LEVELS})(?P<level_strain>{notation.ANY_STRAIN})
  |
  (?P<trick_strain>{notation.ANY_STRAIN})(?P<tricks>{_TRICK_COUNTS})
  """,
  re.VERBOSE,
)

# The par line's own label, written with or without its colon. It is part of the
# line in the ACBL club blob and a separate element on the tournament pages, so
# the pattern below leaves it optional and the two surfaces need no branch of
# their own.
_PAR_LABEL = r'Par:?\s*'

# The par line: a score from North-South's perspective, then the contracts
# achieving it separated by slashes — `Par: -800 7H*-NS-4`.
_PAR_PATTERN = re.compile(
  rf"""
  ^\s*
  (?:{_PAR_LABEL})?
  (?P<score>[+-]?\d+)
  \s*
  (?P<contracts>.*?)
  \s*$
  """,
  re.VERBOSE,
)

# One par contract: `3NT-EW+2`, `7H*-NS-4`, `4S-E`. The result is omitted
# whenever par makes exactly.
_PAR_CONTRACT_PATTERN = re.compile(
  rf"""
  {notation.CONTRACT_PATTERN}
  -{notation.DECLARER_PATTERN}
  {notation.RESULT_PATTERN}
  """,
  re.VERBOSE,
)

# What separates the two seats of a side in a double-dummy cell, and what
# separates one par contract from the next.
_SEAT_SEPARATOR = '/'
_CONTRACT_SEPARATOR = '/'

# What stands in for the level of a seat that can make no contract at all. It
# says only that the seat takes fewer than seven tricks, so the cell is `None`
# unless the same strain is also stated as a trick count.
_NO_MAKEABLE_CONTRACT = '-'

# Everything up to and including the side's own label, which the parsers hand
# over along with the cells — `NS: C5 D1 ...`.
_SIDE_LABEL_PATTERN = re.compile(
  r"""
  ^\s*
  (?:N/?S|E/?W)  # the side, with or without a slash between its two seats
  \s*:?\s*
  """,
  re.VERBOSE | re.IGNORECASE,
)


class AcblNotationError(ValueError):
  """An ACBL page wrote an analysis this module could not read."""


def double_dummy_tricks(
  *, north_south: str, east_west: str
) -> DoubleDummyTricks:
  """Return the double-dummy table ACBL's two analysis lines state.

  Args:
    north_south: the `NS:` line, e.g. `NS: 2/3D 5H 2NT C5 S6`.
    east_west: the `EW:` line, e.g. `EW: 2C 1S D0/2 H0 NT0`.

  Raises:
    AcblNotationError: if a line holds a cell in neither of the two forms.
  """
  tricks: dict[Direction, dict[Strain, int | None]] = {
    seat: dict.fromkeys(notation.STRAINS_LOW_TO_HIGH) for seat in Direction
  }
  for side, line in (
    (Side.NORTH_SOUTH, north_south),
    (Side.EAST_WEST, east_west),
  ):
    for strain, by_seat in _cells(side=side, line=line).items():
      for seat, count in by_seat.items():
        tricks[seat][strain] = count
  return tricks


def _cells(
  *, side: Side, line: str
) -> Mapping[Strain, Mapping[Direction, int | None]]:
  """Read one side's analysis line into a trick count per seat and strain."""
  # Every space is dropped rather than treated as a separator. The tournament
  # pages build a line out of nested elements, so flattening them scatters
  # spaces through the middle of cells — `2/ 3 D 5 H` for `2/3D 5H` — while the
  # club's blob writes the same line with none. Dropping them all leaves one
  # spelling to read, and the cells stay unambiguous without separators because
  # a level and a trick count are each a single digit.
  cells = notation.normalize(_SIDE_LABEL_PATTERN.sub('', line))

  read: dict[Strain, dict[Direction, int | None]] = {}
  position = 0
  for match in _MAKEABLE_PATTERN.finditer(cells):
    if cells[position : match.start()]:
      raise AcblNotationError(
        f'unreadable double-dummy cell in {line!r}: '
        f'{cells[position : match.start()]!r}'
      )
    position = match.end()

    if match.group('levels'):
      strain = notation.STRAIN_BY_LETTER[match.group('level_strain')]
      counts = [
        int(level) + BOOK if level != _NO_MAKEABLE_CONTRACT else None
        for level in match.group('levels').split(_SEAT_SEPARATOR)
      ]
    else:
      strain = notation.STRAIN_BY_LETTER[match.group('trick_strain')]
      counts = [
        int(count) for count in match.group('tricks').split(_SEAT_SEPARATOR)
      ]

    # `5D` states one count covering both seats; `3/4D` states one per seat, in
    # the order the side names them — North before South, East before West.
    counts_per_seat = counts * 2 if len(counts) == 1 else counts

    # A side whose two seats straddle seven tricks states its strain twice, once
    # in each form: `1/-S` gives a level for the seat that makes something and
    # nothing for the seat that makes none, and `S7/6` then gives both counts
    # outright. So a count already read survives a later cell that states none,
    # whichever order the two cells arrive in.
    by_seat = read.setdefault(strain, {})
    for seat, count in zip(side.seats, counts_per_seat, strict=True):
      if count is not None or seat not in by_seat:
        by_seat[seat] = count

  if cells[position:]:
    raise AcblNotationError(
      f'unreadable double-dummy cell in {line!r}: {cells[position:]!r}'
    )
  return read


def par(
  statement: str, *, double_dummy_tricks: DoubleDummyTricks | None
) -> Par | None:
  """Return the par an ACBL page states, or None when it states none.

  ACBL writes no result at all when par makes exactly, so the result is
  recovered from the double-dummy table — which is why the table is passed in
  rather than looked up afterwards.

  Args:
    statement: the par line, e.g. `Par: -450 4S-EW+1/4H-EW+1`.
    double_dummy_tricks: the board's trick table, for recovering an omitted
      result.

  Raises:
    AcblNotationError: if the line states a score but no contract this module
      can read.
  """
  match = _PAR_PATTERN.match(statement)
  if not match:
    return None

  # Spaces are dropped for the same reason as in the double-dummy line: the
  # tournament pages scatter them through a contract they build out of nested
  # elements, and the notation carries none of its own.
  contracts = notation.normalize(match.group('contracts'))

  resolutions: list[Resolution] = []
  for contract in contracts.split(_CONTRACT_SEPARATOR):
    if not contract:
      continue
    parsed = _PAR_CONTRACT_PATTERN.fullmatch(contract)
    if not parsed:
      raise AcblNotationError(f'unreadable par contract in {statement!r}')
    level = int(parsed.group('level'))
    try:
      resolutions.extend(
        notation.par_contracts(
          level=level,
          strain=notation.STRAIN_BY_LETTER[parsed.group('strain')],
          penalty=notation.PENALTY_BY_MARK_COUNT[len(parsed.group('penalty'))],
          declarer=_declarer(parsed.group('declarer')),
          stated_tricks=notation.tricks_taken_from_par_result(
            parsed.group('result') or '', level
          ),
          double_dummy_tricks=double_dummy_tricks,
        )
      )
    except notation.NotationError as error:
      # A result this line omits and the double-dummy table cannot supply.
      # Re-raised in this module's own terms so a caller catching what the
      # docstring promises catches every way this function fails — the two error
      # types are siblings, so catching one would not catch the other.
      raise AcblNotationError(f'{error} — in {statement!r}') from error

  return Par(score=int(match.group('score')), resolutions=tuple(resolutions))


def _declarer(value: str) -> Direction | Side:
  """The seat or side a par contract's declarer names."""
  if value in tuple(Side):
    return Side(value)
  return Direction(value)


def player_name(name: str) -> str:
  """Return a player's name given name first, as a traveller holds one.

  ACBL writes a name surname first, with a comma between — `Alfa, Ann` — where
  every other source puts the given name first. Turning it around here is what
  lands an ACBL capture in the one order every traveller keeps;
  `models.PairIdentity.names` says why the order is fixed. A name with no comma
  is already in that order and is returned unchanged.
  """
  surname, separator, given = name.partition(',')
  if not separator:
    return name.strip()
  return f'{given.strip()} {surname.strip()}'.strip()
