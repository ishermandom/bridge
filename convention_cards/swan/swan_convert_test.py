# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

"""Behavior tests for the SWAN <-> Bridgodex converters."""

import pytest
from bridgodex_key import BridgodexKey

from swan import swan_to_bridgodex


def _swan(card: dict[str, object]) -> dict[str, object]:
  """Wrap section content in the SWAN envelope."""
  return {'Convention_Card': {'New_Format': True, **card}}


# --- SWAN -> Bridgodex ---


def test_a_true_swan_checkbox_becomes_on() -> None:
  result = swan_to_bridgodex.convert(
    _swan({'Majors': {'drury': {'two_clubs': True, 'two_diamonds': False}}})
  )

  assert result.document['settings'] == {'majors': {'drury_2c': 'on'}}
  assert result.warnings == ()


def test_swan_text_passes_through_and_empty_text_is_omitted() -> None:
  result = swan_to_bridgodex.convert(
    _swan({'Overview': {'general_approach': '2/1 Game Forcing', 'names': ''}})
  )

  assert result.document['settings'] == {
    'overview': {'general_approach': '2/1 Game Forcing'}
  }


def test_a_circled_swan_position_becomes_its_number() -> None:
  result = swan_to_bridgodex.convert(
    _swan(
      {
        'Leads_vs_suits': {
          'honor_leads': {'king_queen': {'king': False, 'queen': True}}
        }
      }
    )
  )

  assert result.document['settings'] == {
    'leads_vs_suits': {'honor_leads_KQx': 2}
  }


def test_a_circle_on_the_bold_default_converts_to_nothing() -> None:
  # The ACBL card prints KQx's K (position 1) in bold, so a SWAN mark on the K
  # repeats the default and is dropped without a warning.
  result = swan_to_bridgodex.convert(
    _swan({'Leads_vs_suits': {'honor_leads': {'king_queen': {'king': True}}}})
  )

  assert result.document['settings'] == {}
  assert result.warnings == ()


def test_multiple_circles_keep_the_lowest_and_warn() -> None:
  result = swan_to_bridgodex.convert(
    _swan(
      {
        'Leads_vs_notrump': {
          'length_leads': {
            'five_small': {'second': True, 'fourth': True, 'first': False}
          }
        }
      }
    )
  )

  assert result.document['settings'] == {
    'leads_vs_nt': {'length_leads_xxxxx': 2}
  }
  assert len(result.warnings) == 1
  assert 'five_small' in result.warnings[0]


def test_an_unknown_swan_field_is_a_hard_error() -> None:
  with pytest.raises(ValueError, match='brand_new_toy'):
    swan_to_bridgodex.convert(_swan({'Majors': {'brand_new_toy': True}}))


def test_a_swan_only_field_with_content_warns_and_is_dropped() -> None:
  result = swan_to_bridgodex.convert(
    _swan({'Carding': {'smith': {'smith_expl': 'special agreement'}}})
  )

  assert result.document['settings'] == {}
  assert len(result.warnings) == 1
  assert 'smith_expl' in result.warnings[0]


def test_an_empty_swan_only_field_passes_silently() -> None:
  result = swan_to_bridgodex.convert(
    _swan({'Carding': {'smith': {'smith_expl': ''}}})
  )

  assert result.warnings == ()


# --- circle synthesis from BridgeWinners bolds ---


def test_an_unmarked_holding_is_circled_at_the_bridgewinners_bold() -> None:
  result = swan_to_bridgodex.convert(
    _swan({'Leads_vs_notrump': {'length_leads': {'doubleton': {}}}}),
    bridgewinners_length_bolds={
      BridgodexKey('leads_vs_nt', 'length_leads_xx'): 1
    },
  )

  assert result.document['settings'] == {'leads_vs_nt': {'length_leads_xx': 1}}
  assert len(result.synthesized) == 1
  assert 'length_leads_xx' in result.synthesized[0]


def test_an_explicit_mark_beats_the_bridgewinners_bold_default() -> None:
  result = swan_to_bridgodex.convert(
    _swan(
      {'Leads_vs_notrump': {'length_leads': {'doubleton': {'second': True}}}}
    ),
    bridgewinners_length_bolds={
      BridgodexKey('leads_vs_nt', 'length_leads_xx'): 1
    },
  )

  assert result.document['settings'] == {'leads_vs_nt': {'length_leads_xx': 2}}
  assert result.synthesized == ()


def test_without_a_bolds_map_nothing_is_synthesized() -> None:
  result = swan_to_bridgodex.convert(
    _swan({'Leads_vs_notrump': {'length_leads': {'doubleton': {}}}})
  )

  assert result.document['settings'] == {}
  assert result.synthesized == ()
