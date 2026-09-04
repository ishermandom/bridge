# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

"""Tests for suit-symbol markup parsing."""

import pytest

from renderer.markup import Suit, TextRun, parse_suit_markup


def test_plain_text_is_a_single_run() -> None:
  assert parse_suit_markup('2/1 Game Forcing') == (TextRun('2/1 Game Forcing'),)


def test_suit_markup_becomes_a_symbol_run() -> None:
  assert parse_suit_markup('tfr to 3!c') == (
    TextRun('tfr to 3'),
    TextRun('♣', Suit.CLUBS),
  )


def test_all_four_suits_map_to_their_symbols() -> None:
  # The red suits map to their open forms (see the `Suit` docstring).
  assert parse_suit_markup('!s!h!d!c') == (
    TextRun('♠', Suit.SPADES),
    TextRun('♡', Suit.HEARTS),
    TextRun('♢', Suit.DIAMONDS),
    TextRun('♣', Suit.CLUBS),
  )


def test_text_may_continue_after_a_suit() -> None:
  assert parse_suit_markup("!c's + another suit") == (
    TextRun('♣', Suit.CLUBS),
    TextRun("'s + another suit"),
  )


def test_uppercase_suit_letter_is_accepted() -> None:
  assert parse_suit_markup('!H') == (TextRun('♡', Suit.HEARTS),)


def test_unknown_suit_letter_is_rejected() -> None:
  with pytest.raises(ValueError, match='unknown suit'):
    parse_suit_markup('bid 2!x here')


def test_bang_without_a_letter_is_plain_text() -> None:
  assert parse_suit_markup('forcing!') == (TextRun('forcing!'),)
