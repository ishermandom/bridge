# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for the `Suit combination` note type."""

import re

from suit_combination_note_type import make_note_type

# A template's field reference, such as `{{North holding}}` or `{{#Remarks}}`.
#
# An optional marker comes first: `#` opens a section shown only when the field
# has text, `^` opens one shown only when it's empty, and `/` closes either.
_CONDITIONAL_MARKER = r'[#/^]?'
_FIELD_NAME = r'(?P<field_name>[^}]+)'
_FIELD_REFERENCE = re.compile(
  r'\{\{' + _CONDITIONAL_MARKER + _FIELD_NAME + r'\}\}'
)


# --- frozen schema ---


def test_note_type_schema_is_frozen() -> None:
  # Frozen: see `flashcards/spec.md` #note-type-evolution.
  note_type = make_note_type()

  assert note_type.model_id == 1191707489
  assert [field['name'] for field in note_type.fields] == [
    'Suit combination',
    'North holding',
    'South holding',
    'Target # of tricks',
    'Constraints',
    'Success %',
    'Best line',
    'Remarks',
    'Source',
  ]
  assert [template['name'] for template in note_type.templates] == [
    'Suit combination'
  ]


# --- templates ---


def test_card_shows_every_field_but_the_summary() -> None:
  note_type = make_note_type()
  # The summary field serves Anki's card browser, not the card.
  shown_field_names = {field['name'] for field in note_type.fields} - {
    'Suit combination'
  }
  [template] = note_type.templates

  references = {
    match.group('field_name')
    for side in (template['qfmt'], template['afmt'])
    for match in _FIELD_REFERENCE.finditer(side)
  }

  # `FrontSide` is Anki's own: the rendered front, shown atop the back.
  assert references - {'FrontSide'} == shown_field_names
