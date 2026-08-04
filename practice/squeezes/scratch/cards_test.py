# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for the card vocabulary."""

import pytest
from cards import Card, Rank, Seat, Suit

# --- card notation ---


@pytest.mark.parametrize('code', ['SA', 'HT', 'D9', 'C2'])
def test_card_code_round_trips(code: str) -> None:
  assert Card.from_code(code).code == code


@pytest.mark.parametrize('code', ['', 'S', 'SAX', 'XA', 'S1', 's a'])
def test_malformed_card_codes_are_rejected(code: str) -> None:
  with pytest.raises(ValueError, match='card code'):
    Card.from_code(code)


def test_card_displays_with_suit_glyph() -> None:
  assert str(Card(Suit.SPADES, Rank.ACE)) == '\N{BLACK SPADE SUIT}A'


# --- seats ---


def test_seats_rotate_clockwise() -> None:
  assert Seat.SOUTH.next_clockwise is Seat.WEST
  assert Seat.WEST.next_clockwise is Seat.NORTH


def test_north_and_south_are_the_declarer_side() -> None:
  assert Seat.NORTH.is_declarer_side
  assert Seat.SOUTH.is_declarer_side
  assert not Seat.EAST.is_declarer_side
  assert not Seat.WEST.is_declarer_side
