# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

"""Tests for reading BridgeWinners' bold length-lead defaults."""

from collections.abc import Set as AbstractSet

import pytest
from bridgodex_key import BridgodexKey

from swan.bridgewinners_lead_bolds import Char, length_bolds_from_chars


def _row(
  text: str, y: float, bold_indices: AbstractSet[int] = frozenset()
) -> list[Char]:
  """Lay a string out as one text row, 10pt per character."""
  return [
    Char(character, column * 10.0, y, column in bold_indices)
    for column, character in enumerate(text)
    if character != ' '
  ]


def _card_chars(
  plain_bolds: AbstractSet[int] = frozenset(),
  honor_bolds: AbstractSet[int] = frozenset(),
) -> list[Char]:
  """A minimal card: a label row, the plain row, and the honor row.

  `plain_bolds` and `honor_bolds` are 0-based indices into a row's cards,
  counted left to right across both panels — not 1-based positions within a
  holding.
  """
  plain = 'xx xxx xxxx xxxxx  xx xxx xxxx xxxxx'.replace(' ', '')
  honor = 'Hxx Hxxx Hxxxx  Hxx Hxxx Hxxxx'.replace(' ', '')
  return (
    _row('Length Leads', 300.0)
    + _row(plain, 200.0, plain_bolds)
    + _row(honor, 190.0, honor_bolds)
  )


def test_bolds_map_to_their_holdings_and_panels() -> None:
  # Plain index 0 = suits xx position 1; index 5 = suits xxxx position 1 (2+3
  # cards precede it); index 14 = notrump xx position 1. Honor index 1 = suits
  # Hxx position 2.
  bolds = length_bolds_from_chars(
    _card_chars(plain_bolds={0, 5, 14}, honor_bolds={1})
  )

  assert bolds == {
    BridgodexKey('leads_vs_suits', 'length_leads_xx'): 1,
    BridgodexKey('leads_vs_suits', 'length_leads_xxxx'): 1,
    BridgodexKey('leads_vs_nt', 'length_leads_xx'): 1,
    BridgodexKey('leads_vs_suits', 'length_leads_Hxx'): 2,
  }


def test_a_card_with_no_bolds_yields_an_empty_map() -> None:
  assert length_bolds_from_chars(_card_chars()) == {}


def test_missing_length_rows_are_a_loud_error() -> None:
  with pytest.raises(ValueError, match='length-lead rows'):
    length_bolds_from_chars(_row('just prose here', 100.0))


def test_two_bolds_in_one_holding_are_a_loud_error() -> None:
  # Indices 0 and 1 are both in the suits xx holding.
  with pytest.raises(ValueError, match='length_leads_xx'):
    length_bolds_from_chars(_card_chars(plain_bolds={0, 1}))
