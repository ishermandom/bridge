# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for parsing one hand's holding in the suit-combination notation."""

import pytest
from holding_notation import Card, Holding, parse_holding

# --- parsing ---


def test_named_and_small_cards_parse_high_to_low() -> None:
  holding = parse_holding('AQTx')

  assert holding == Holding(cards=(Card.ACE, Card.QUEEN, Card.TEN, Card.SMALL))


def test_named_spot_card_keeps_its_rank() -> None:
  holding = parse_holding('K8xx')

  assert holding == Holding(
    cards=(Card.KING, Card.EIGHT, Card.SMALL, Card.SMALL)
  )


# --- normalization ---


def test_canonical_notation_lists_cards_high_to_low() -> None:
  assert str(parse_holding('AQTx')) == 'AQTx'


def test_ten_written_as_10_normalizes_to_t() -> None:
  assert str(parse_holding('A10x')) == 'ATx'


def test_spaces_are_ignored() -> None:
  assert str(parse_holding(' A Q x x ')) == 'AQxx'


@pytest.mark.parametrize(
  'spelling', ['', ' ', '-', 'v', 'void', '(void)', ' - ']
)
def test_every_void_spelling_normalizes_to_one_notation(spelling: str) -> None:
  assert str(parse_holding(spelling)) == '(void)'


# --- rejection ---


@pytest.mark.parametrize('text', ['QA', 'xA', 'AA', 'K9x8'])
def test_cards_out_of_order_or_repeated_are_rejected(text: str) -> None:
  with pytest.raises(ValueError, match='high to low'):
    parse_holding(text)


@pytest.mark.parametrize('text', ['aqx', 'AQX', 'A1', 'AQ?'])
def test_unknown_cards_are_rejected(text: str) -> None:
  with pytest.raises(ValueError, match='Unknown card'):
    parse_holding(text)


def test_more_cards_than_a_suit_holds_are_rejected() -> None:
  # Every rank plus one small card: 14 cards, all in valid order.
  with pytest.raises(ValueError, match='13'):
    parse_holding('AKQJT98765432x')
