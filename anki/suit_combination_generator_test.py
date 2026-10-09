# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for building the suit-combination cards."""

from collections.abc import Sequence
from decimal import Decimal

import genanki
from holding_notation import parse_holding
from suit_combination_generator import build_deck
from suit_combination_note_type import Field
from suit_combination_parsing import SuitCombinationEntry


def _make_entry(
  *,
  north: str = 'AQ',
  south: str = 'xx',
  tricks_target: int = 2,
  success_percent: str = '50',
  best_line: str = 'Low to the Q',
  remarks: str = 'Finesse',
  source: str = 'A book',
) -> SuitCombinationEntry:
  """An entry, taking each holding in the input file's notation."""
  return SuitCombinationEntry(
    north=parse_holding(north),
    south=parse_holding(south),
    tricks_target=tricks_target,
    success_percent=Decimal(success_percent),
    best_line=best_line,
    remarks=remarks,
    source=source,
  )


def _build_note(entry: SuitCombinationEntry) -> genanki.Note:
  """The note the generator builds for a single entry."""
  [note] = build_deck([entry]).notes
  return note


def _field_value(note: genanki.Note, field: Field) -> str:
  """One field's value in `note`."""
  return note.fields[list(Field).index(field)]


def _build_guids(entries: Sequence[SuitCombinationEntry]) -> Sequence[str]:
  """Each entry's note identity, in order."""
  return [note.guid for note in build_deck(entries).notes]


# --- deck ---


def test_each_entry_becomes_a_note_in_the_suit_combination_deck() -> None:
  deck = build_deck([_make_entry(north='AQ'), _make_entry(north='AJ')])

  assert deck.name == 'Bridge::Suit combinations'
  assert [_field_value(note, Field.NORTH_HOLDING) for note in deck.notes] == [
    'AQ',
    'AJ',
  ]


def test_note_carries_the_category_tags() -> None:
  note = _build_note(_make_entry())

  assert note.tags == [
    'cat::suit-combination',
    'origin::generated',
    'publish::yes',
  ]


# --- fields ---


def test_note_fields_hold_the_entry_in_field_order() -> None:
  entry = _make_entry(
    north='AQT',
    south='xx',
    tricks_target=3,
    success_percent='24',
    best_line='Low to the T',
    remarks='Finesse twice',
    source='A book',
  )

  assert list(_build_note(entry).fields) == [
    'AQT-xx, 3 tricks',
    'AQT',
    'xx',
    '3',
    '',  # no constraint columns yet
    '24',
    '<p>Low to the T</p>\n',
    '<p>Finesse twice</p>\n',
    'A book',
  ]


def test_holdings_are_stored_normalized() -> None:
  note = _build_note(_make_entry(north='A10x', south=''))

  assert _field_value(note, Field.NORTH_HOLDING) == 'ATx'
  assert _field_value(note, Field.SOUTH_HOLDING) == '(void)'


def test_blank_remarks_stay_blank() -> None:
  note = _build_note(_make_entry(remarks=''))

  # Empty, so the card leaves out its remarks section.
  assert _field_value(note, Field.REMARKS) == ''


def test_summary_names_a_single_trick_in_the_singular() -> None:
  note = _build_note(_make_entry(north='Kx', south='xx', tricks_target=1))

  assert _field_value(note, Field.SUIT_COMBINATION) == 'Kx-xx, 1 trick'


def test_best_line_and_remarks_render_as_markdown() -> None:
  note = _build_note(
    _make_entry(best_line='Low to the *Q*', remarks='Tip: Count')
  )

  assert _field_value(note, Field.BEST_LINE) == '<p>Low to the <em>Q</em></p>\n'
  assert (
    _field_value(note, Field.REMARKS)
    == '<p><em><strong>Tip:</strong> Count</em></p>\n'
  )


def test_source_shows_as_typed() -> None:
  note = _build_note(_make_entry(source='Smith & Jones <2nd edition>'))

  # Escaped, so the card shows the characters rather than reading them as
  # markup.
  assert (
    _field_value(note, Field.SOURCE) == 'Smith &amp; Jones &lt;2nd edition&gt;'
  )


# --- identity ---


def test_note_identity_is_frozen() -> None:
  # Frozen: see `flashcards/spec.md` #card-identity.
  [guid] = _build_guids([_make_entry(north='AQ', south='xx', tricks_target=2)])

  assert guid == 'I7fnuf@X-G'


def test_note_identity_ignores_fields_outside_the_key() -> None:
  original = _make_entry(
    success_percent='50',
    best_line='Low to the Q',
    remarks='Finesse',
    source='A book',
  )
  # The same holdings and target; every other field differs.
  edited = _make_entry(
    success_percent='51',
    best_line='Finesse the Q',
    remarks='Edited',
    source='Another book',
  )

  [original_guid, edited_guid] = _build_guids([original, edited])

  assert original_guid == edited_guid


def test_note_identity_uses_the_normalized_holding() -> None:
  [ten_guid, t_guid] = _build_guids(
    [_make_entry(north='A10x'), _make_entry(north='ATx')]
  )

  assert ten_guid == t_guid


def test_note_identity_differs_by_tricks_target() -> None:
  [two_guid, three_guid] = _build_guids(
    [
      _make_entry(north='AQT', tricks_target=2),
      _make_entry(north='AQT', tricks_target=3),
    ]
  )

  assert two_guid != three_guid
