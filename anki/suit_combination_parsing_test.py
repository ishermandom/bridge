# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for parsing the suit-combination input file."""

import csv
import io
from collections.abc import Sequence
from decimal import Decimal

import pytest
from holding_notation import Card, Holding
from suit_combination_parsing import SuitCombinationEntry, read_entries

_HEADER = [
  'North',
  'South',
  'Tricks target',
  'Success %',
  'Best line',
  'Remarks',
  'Source',
]


def _make_row(
  *,
  north: str = 'AQ',
  south: str = 'xx',
  tricks_target: str = '2',
  success_percent: str = '50',
  best_line: str = 'Low to the Q',
  remarks: str = 'Finesse hoping the K is onside',
  source: str = 'A book',
) -> Sequence[str]:
  """One row's cells, in the header's column order."""
  return [
    north,
    south,
    tricks_target,
    success_percent,
    best_line,
    remarks,
    source,
  ]


def _make_input_file(
  rows: Sequence[Sequence[str]], *, header: Sequence[str] = _HEADER
) -> io.StringIO:
  """An input file holding `header` and then `rows`."""
  stream = io.StringIO()
  writer = csv.writer(stream)
  writer.writerow(header)
  writer.writerows(rows)
  stream.seek(0)
  return stream


# --- reading ---


def test_row_becomes_a_suit_combination() -> None:
  input_file = _make_input_file(
    [['AQ', 'xx', '2', '50', 'Low to the Q', 'Finesse', 'A book']]
  )

  assert read_entries(input_file) == [
    SuitCombinationEntry(
      north=Holding(cards=(Card.ACE, Card.QUEEN)),
      south=Holding(cards=(Card.SMALL, Card.SMALL)),
      tricks_target=2,
      success_percent=Decimal('50'),
      best_line='Low to the Q',
      remarks='Finesse',
      source='A book',
    )
  ]


def test_blank_remarks_and_source_are_allowed() -> None:
  input_file = _make_input_file([_make_row(remarks='', source='')])

  [entry] = read_entries(input_file)

  assert (entry.remarks, entry.source) == ('', '')


def test_blank_holding_is_a_void() -> None:
  input_file = _make_input_file([_make_row(north='AKQ', south='')])

  [entry] = read_entries(input_file)

  assert str(entry.south) == '(void)'


def test_success_percent_keeps_its_written_precision() -> None:
  input_file = _make_input_file([_make_row(success_percent='52.5')])

  [entry] = read_entries(input_file)

  assert entry.success_percent == Decimal('52.5')


def test_comment_rows_are_skipped() -> None:
  input_file = _make_input_file([['# From a class'], _make_row(north='AQ')])

  entries = read_entries(input_file)

  assert [str(entry.north) for entry in entries] == ['AQ']


def test_empty_unnamed_columns_are_ignored() -> None:
  # As Google Sheets exports them: blank headers, and rows running past the
  # header.
  input_file = _make_input_file(
    [[*_make_row(), '', '', '', '']], header=[*_HEADER, '', '']
  )

  assert len(read_entries(input_file)) == 1


def test_same_holdings_with_another_target_are_both_kept() -> None:
  input_file = _make_input_file(
    [
      _make_row(north='AQT', tricks_target='3'),
      _make_row(north='AQT', tricks_target='2'),
    ]
  )

  assert len(read_entries(input_file)) == 2


# --- rejecting the header ---


def test_empty_export_is_rejected() -> None:
  with pytest.raises(ValueError, match='empty'):
    read_entries(io.StringIO(''))


def test_missing_header_is_rejected() -> None:
  header = ['North', 'South', 'Tricks target', 'Success %', 'Best line']

  with pytest.raises(ValueError, match="missing header 'Remarks'"):
    read_entries(_make_input_file([], header=header))


def test_unknown_header_is_rejected() -> None:
  header = [
    'North',
    'South',
    'Tricks target',
    'Likelihood',
    'Best line',
    'Remarks',
    'Source',
  ]

  with pytest.raises(ValueError, match="unknown header 'Likelihood'"):
    read_entries(_make_input_file([], header=header))


# --- rejecting rows ---


def test_data_in_an_unnamed_column_is_rejected() -> None:
  input_file = _make_input_file(
    [[*_make_row(), 'stray']], header=[*_HEADER, '']
  )

  with pytest.raises(ValueError, match='no header'):
    read_entries(input_file)


def test_comment_row_with_data_beyond_its_first_cell_is_rejected() -> None:
  input_file = _make_input_file([['# From a class', 'AQ']])

  with pytest.raises(ValueError, match='comment row'):
    read_entries(input_file)


def test_invalid_holding_is_reported_with_its_row() -> None:
  input_file = _make_input_file([_make_row(north='AQX')])

  # The header is row 1, so the first row of data is row 2.
  with pytest.raises(ValueError, match='Row 2: Unknown card'):
    read_entries(input_file)


def test_blank_best_line_is_rejected() -> None:
  input_file = _make_input_file([_make_row(best_line='')])

  with pytest.raises(ValueError, match='Best line'):
    read_entries(input_file)


@pytest.mark.parametrize('tricks_target', ['', 'two', '0', '3'])
def test_tricks_target_outside_the_longer_hand_is_rejected(
  tricks_target: str,
) -> None:
  # AQ opposite xx: the longer hand has two cards, so at most two tricks.
  input_file = _make_input_file(
    [_make_row(north='AQ', south='xx', tricks_target=tricks_target)]
  )

  with pytest.raises(ValueError, match='Tricks target'):
    read_entries(input_file)


@pytest.mark.parametrize(
  'success_percent', ['', 'fifty', '50%', '-1', '101', 'NaN']
)
def test_success_percent_outside_0_to_100_is_rejected(
  success_percent: str,
) -> None:
  input_file = _make_input_file([_make_row(success_percent=success_percent)])

  with pytest.raises(ValueError, match='Success %'):
    read_entries(input_file)


def test_card_named_in_both_hands_is_rejected() -> None:
  input_file = _make_input_file([_make_row(north='AQ', south='Qx')])

  with pytest.raises(ValueError, match='both hold Q'):
    read_entries(input_file)


def test_more_cards_than_a_suit_across_both_hands_is_rejected() -> None:
  # Seven cards in each hand: 14 together.
  input_file = _make_input_file([_make_row(north='AKQJT98', south='xxxxxxx')])

  with pytest.raises(ValueError, match='14 cards'):
    read_entries(input_file)


def test_both_hands_void_is_rejected() -> None:
  input_file = _make_input_file([_make_row(north='', south='-')])

  with pytest.raises(ValueError, match='both void'):
    read_entries(input_file)


def test_repeated_holdings_and_target_are_rejected() -> None:
  input_file = _make_input_file([_make_row(), _make_row()])

  with pytest.raises(ValueError, match='Row 3: repeats row 2'):
    read_entries(input_file)


def test_one_error_lists_every_invalid_row() -> None:
  input_file = _make_input_file(
    [
      _make_row(north='AQX'),
      _make_row(north='KQ'),
      _make_row(south='xxQ'),
    ]
  )

  with pytest.raises(ValueError) as raised:
    read_entries(input_file)

  # Rows 2 and 4 are invalid; row 3 between them is fine.
  assert 'Row 2' in str(raised.value)
  assert 'Row 4' in str(raised.value)
