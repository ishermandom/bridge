# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Parsing the suit-combination input file into validated entries.

The input file's layout — its headers, which cells may be blank, and the rows
and columns to skip — is specified in `anki/spec.md` #suit-combination-input.
Reading reports every invalid row in a single error, each by the row number it
has in the Google Sheet, so one pass over the input file finds all of its
errors.
"""

import csv
import decimal
import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TextIO

from holding_notation import SUIT_SIZE, Card, Holding, parse_holding


class Column(enum.StrEnum):
  """A column of the input file, by its header."""

  NORTH = 'North'
  SOUTH = 'South'
  TRICKS_TARGET = 'Tricks target'
  SUCCESS_PERCENT = 'Success %'
  BEST_LINE = 'Best line'
  REMARKS = 'Remarks'
  SOURCE = 'Source'


# A row whose first cell starts with this is a comment, such as a label for the
# rows below it. The rest of a comment row must be empty.
_COMMENT_MARKER = '#'


@dataclass(frozen=True)
class SuitCombinationEntry:
  """One entry from the input file: how to play a suit for a trick target."""

  north: Holding
  south: Holding
  tricks_target: int
  # As written, so `52.5` keeps its precision and `50` stays whole.
  success_percent: decimal.Decimal
  best_line: str
  # Empty when the cell is blank.
  remarks: str
  # Empty when the cell is blank.
  source: str


def read_entries(stream: TextIO) -> Sequence[SuitCombinationEntry]:
  """Read and validate every entry in the input file.

  Raises `ValueError` when the headers don't match the expected columns, or when
  any row is invalid, listing every invalid row by its row number in the Google
  Sheet.
  """
  records = csv.reader(stream)
  header = next(records, None)
  if header is None:
    raise ValueError('The input file is empty; expected a header row')
  positions = _locate_columns(header)

  entries: list[SuitCombinationEntry] = []
  row_errors: list[str] = []
  # The first row holding each identity, to catch the same holdings and target
  # entered twice.
  first_row_by_identity: dict[tuple[Holding, Holding, int], int] = {}
  # Count rows as the Google Sheet does: the header is row 1, so the rows after
  # it count from 2.
  for row_number, cells in enumerate(records, start=2):
    if cells and cells[0].strip().startswith(_COMMENT_MARKER):
      # Data beside a comment would otherwise be skipped along with it.
      if any(cell.strip() for cell in cells[1:]):
        row_errors.append(
          f'Row {row_number}: a comment row holds data beyond its first cell'
        )
      continue
    try:
      entry = _parse_row(cells, positions)
    except ValueError as error:
      row_errors.append(f'Row {row_number}: {error}')
      continue

    identity = (entry.north, entry.south, entry.tricks_target)
    if identity in first_row_by_identity:
      row_errors.append(
        f'Row {row_number}: repeats row {first_row_by_identity[identity]}, with'
        ' the same holdings and tricks target'
      )
      continue
    first_row_by_identity[identity] = row_number
    entries.append(entry)

  if row_errors:
    raise ValueError(
      'Invalid rows in the input file:\n' + '\n'.join(row_errors)
    )
  return entries


def _locate_columns(header: Sequence[str]) -> Mapping[Column, int]:
  """Each column's position in the header row.

  Raises `ValueError` when a header is unknown, repeated, or missing. A blank
  header marks an unnamed column, which is left out.
  """
  positions: dict[Column, int] = {}
  header_errors: list[str] = []
  for position, name in enumerate(header):
    stripped_name = name.strip()
    if not stripped_name:
      continue
    try:
      column = Column(stripped_name)
    except ValueError:
      header_errors.append(f'unknown header {stripped_name!r}')
      continue
    if column in positions:
      header_errors.append(f'repeated header {stripped_name!r}')
      continue
    positions[column] = position

  header_errors.extend(
    f'missing header {column.value!r}'
    for column in Column
    if column not in positions
  )
  if header_errors:
    mismatches = '; '.join(header_errors)
    expected = ', '.join(repr(column.value) for column in Column)
    raise ValueError(
      f"The input file's headers don't match: {mismatches}. Expected {expected}"
    )
  return positions


def _parse_row(
  cells: Sequence[str], positions: Mapping[Column, int]
) -> SuitCombinationEntry:
  """One row of the input file, parsed and validated."""
  # Google Sheets pads rows with unnamed columns, which must stay empty.
  named_positions = set(positions.values())
  for position, text in enumerate(cells):
    if position not in named_positions and text.strip():
      raise ValueError(
        f'column {position + 1} has no header but holds {text.strip()!r}'
      )

  north = parse_holding(_cell(cells, positions, Column.NORTH))
  south = parse_holding(_cell(cells, positions, Column.SOUTH))
  _check_holdings_share_one_suit(north, south)

  best_line = _cell(cells, positions, Column.BEST_LINE)
  if not best_line:
    raise ValueError('Best line is blank')

  return SuitCombinationEntry(
    north=north,
    south=south,
    tricks_target=_parse_tricks_target(
      _cell(cells, positions, Column.TRICKS_TARGET), north, south
    ),
    success_percent=_parse_success_percent(
      _cell(cells, positions, Column.SUCCESS_PERCENT)
    ),
    best_line=best_line,
    remarks=_cell(cells, positions, Column.REMARKS),
    source=_cell(cells, positions, Column.SOURCE),
  )


def _cell(
  cells: Sequence[str], positions: Mapping[Column, int], column: Column
) -> str:
  """A column's text in one row, stripped; empty if the row stops short."""
  position = positions[column]
  if position >= len(cells):
    return ''
  return cells[position].strip()


def _check_holdings_share_one_suit(north: Holding, south: Holding) -> None:
  """Raise `ValueError` unless both holdings could come from a single suit."""
  if not north.cards and not south.cards:
    raise ValueError('North and South are both void')

  card_count = len(north.cards) + len(south.cards)
  if card_count > SUIT_SIZE:
    raise ValueError(
      f'North {north} and South {south} hold {card_count} cards together; a'
      f' suit has only {SUIT_SIZE}'
    )

  # A suit has one of each named card, so naming one in both hands is an error.
  # An `x` in each hand is fine: each `x` stands for a different low spot.
  shared_cards = (set(north.cards) & set(south.cards)) - {Card.SMALL}
  if shared_cards:
    # Iterating `Card` lists the shared cards high to low.
    shared_text = ''.join(card for card in Card if card in shared_cards)
    raise ValueError(f'North {north} and South {south} both hold {shared_text}')


def _parse_tricks_target(text: str, north: Holding, south: Holding) -> int:
  """The tricks target, from 1 up to the longer hand's length."""
  try:
    tricks_target = int(text)
  except ValueError:
    raise ValueError(f'Tricks target {text!r} is not a whole number') from None

  # Without ruffing, a suit takes at most one trick per card in its longer hand.
  most_tricks = max(len(north.cards), len(south.cards))
  if not 1 <= tricks_target <= most_tricks:
    raise ValueError(
      f'Tricks target {tricks_target} is outside 1 to {most_tricks}, the'
      " longer hand's length"
    )
  return tricks_target


def _parse_success_percent(text: str) -> decimal.Decimal:
  """The success percentage, a number from 0 to 100."""
  try:
    percent = decimal.Decimal(text)
  except decimal.InvalidOperation:
    raise ValueError(f'Success % {text!r} is not a number') from None

  # Checking finiteness first matters: comparing a NaN raises rather than
  # returning False.
  if not percent.is_finite() or not 0 <= percent <= 100:
    raise ValueError(f'Success % {text!r} is outside 0 to 100')
  return percent
