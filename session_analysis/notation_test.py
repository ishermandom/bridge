# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for the result-notation translator."""

import pytest

from session_analysis.notation import tricks_taken_from_sheet_result

# --- makes ---


def test_making_exactly() -> None:
  # '4S +4' is ten tricks: a 4-level contract making with no overtricks.
  assert tricks_taken_from_sheet_result('+4', 4) == 10


def test_making_with_overtricks() -> None:
  # '4S +6' is twelve tricks: four for the contract plus two overtricks.
  assert tricks_taken_from_sheet_result('+6', 4) == 12


def test_making_every_trick() -> None:
  # '3N +7' is all thirteen tricks, the most possible.
  assert tricks_taken_from_sheet_result('+7', 3) == 13


def test_overtricks_are_counted_from_book_not_the_contract() -> None:
  # '+N' is an absolute count from book, so the level does not change it: '+6'
  # is twelve tricks whether the contract was 4S (making two) or 6C (making
  # exactly).
  assert tricks_taken_from_sheet_result('+6', 4) == 12
  assert tricks_taken_from_sheet_result('+6', 6) == 12


# --- set contracts ---


def test_down_one() -> None:
  # '5H -1' is ten tricks: one short of the eleven the contract needed.
  assert tricks_taken_from_sheet_result('-1', 5) == 10


def test_down_several() -> None:
  # '1N -2' is five tricks: two short of the seven the contract needed.
  assert tricks_taken_from_sheet_result('-2', 1) == 5


def test_down_every_trick() -> None:
  # A 7-level contract '-13' is zero tricks: the whole contract lost.
  assert tricks_taken_from_sheet_result('-13', 7) == 0


# --- transcription tolerance ---


@pytest.mark.parametrize(
  'dash',
  [
    chr(0x2D),  # hyphen-minus (ASCII)
    chr(0x2212),  # minus sign
    chr(0x2013),  # en dash
    chr(0x2014),  # em dash
    chr(0x2015),  # horizontal bar
  ],
)
def test_accepts_any_dash_glyph_as_a_minus(dash: str) -> None:
  # The sheet's minus may be any of several dash glyphs, all read alike.
  assert tricks_taken_from_sheet_result(f'{dash}2', 1) == 5


def test_ignores_surrounding_whitespace() -> None:
  assert tricks_taken_from_sheet_result(' +6 ', 4) == 12


# --- responsibility split ---


def test_translates_without_validating_semantics() -> None:
  # '+5' on a 6-level contract is a notational error — eleven tricks is really
  # down one, not a make — but the translator still computes it. Judging that
  # the notation is inconsistent is the validation pass's job, not this one's.
  assert tricks_taken_from_sheet_result('+5', 6) == 11


@pytest.mark.parametrize('token', ['', '+', '5', 'x', '++6', '+-6'])
def test_malformed_token_raises(token: str) -> None:
  with pytest.raises(ValueError, match='malformed'):
    tricks_taken_from_sheet_result(token, 4)
