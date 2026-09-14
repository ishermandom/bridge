# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

"""Behavior tests for the SWAN <-> Bridgodex converters."""

import json
from pathlib import Path

import pytest
from bridgodex_key import BridgodexKey

from swan import bridgodex_to_swan, swan_to_bridgodex
from swan.swan_mapping import BRIDGODEX_ONLY

_FULL_EXPORT_PATH = (
  Path(__file__).resolve().parent.parent
  / 'renderer'
  / 'testdata'
  / 'full_export.json'
)

# A real BridgeWinners export of a card holding only test text, kept for its
# shape: the fields BridgeWinners writes, all of which its import requires.
_BRIDGEWINNERS_EXPORT_PATH = (
  Path(__file__).resolve().parent / 'testdata' / 'bridgewinners_export.json'
)


def _swan(card: dict[str, object]) -> dict[str, object]:
  """Wrap section content in the SWAN envelope."""
  return {'Convention_Card': {'New_Format': True, **card}}


def _leaf_paths(
  node: object, path: tuple[str, ...] = ()
) -> set[tuple[str, ...]]:
  """Every leaf path in a nested JSON object."""
  if not isinstance(node, dict):
    return {path}
  return {
    leaf
    for key, child in node.items()
    for leaf in _leaf_paths(child, (*path, key))
  }


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


# --- Bridgodex -> SWAN ---


def test_an_on_checkbox_becomes_true_in_the_swan_skeleton() -> None:
  result = bridgodex_to_swan.convert(
    {'settings': {'majors': {'drury_2c': 'on'}}, 'notes': ''}
  )

  card = result.document['Convention_Card']
  assert isinstance(card, dict)
  assert card['New_Format'] is True
  drury = card['Majors']['drury']
  # The skeleton carries the unset sibling checkbox as false.
  assert drury['two_clubs'] is True
  assert drury['two_diamonds'] is False


def test_the_output_has_exactly_the_fields_of_a_bridgewinners_export() -> None:
  # BridgeWinners' import fails on a file missing any field its own export
  # carries, so the output must match a real export field for field.
  export = json.loads(_BRIDGEWINNERS_EXPORT_PATH.read_text(encoding='utf-8'))

  result = bridgodex_to_swan.convert({'settings': {}, 'notes': ''})

  assert _leaf_paths(result.document) == _leaf_paths(export)


def test_a_circle_number_sets_exactly_its_position() -> None:
  result = bridgodex_to_swan.convert(
    {'settings': {'leads_vs_suits': {'honor_leads_KQx': 2}}, 'notes': ''}
  )

  card = result.document['Convention_Card']
  assert isinstance(card, dict)
  king_queen = card['Leads_vs_suits']['honor_leads']['king_queen']
  assert king_queen == {'king': False, 'queen': True, 'low': False}


def test_an_uncircled_holding_is_marked_at_its_bold_default() -> None:
  # The ACBL card prints KQx's K in bold, and players circle a lead there only
  # when it departs from the bold card, so an uncircled KQx means the K.
  result = bridgodex_to_swan.convert({'settings': {}, 'notes': ''})

  card = result.document['Convention_Card']
  assert isinstance(card, dict)
  king_queen = card['Leads_vs_suits']['honor_leads']['king_queen']
  assert king_queen == {'king': True, 'queen': False, 'low': False}


def test_an_uncircled_holding_without_a_bold_default_stays_unmarked() -> None:
  # The ACBL card prints no bold card in AKx, so there is no default to mark.
  result = bridgodex_to_swan.convert({'settings': {}, 'notes': ''})

  card = result.document['Convention_Card']
  assert isinstance(card, dict)
  ace_king = card['Leads_vs_suits']['honor_leads']['ace_king']
  # The AKx node also holds the "Varies" checkbox and its description; compare
  # only the three card positions.
  assert (ace_king['ace'], ace_king['king'], ace_king['low']) == (
    False,
    False,
    False,
  )


def test_an_unknown_bridgodex_key_is_a_hard_error() -> None:
  with pytest.raises(ValueError, match='mystery'):
    bridgodex_to_swan.convert(
      {'settings': {'majors': {'mystery': 'on'}}, 'notes': ''}
    )


def test_a_bridgodex_only_key_with_content_warns() -> None:
  result = bridgodex_to_swan.convert(
    {'settings': {'two_level': {'2h_2_suits': 'on'}}, 'notes': ''}
  )

  assert len(result.warnings) == 1
  assert '2h_2_suits' in result.warnings[0]


def test_a_boolean_circle_value_is_rejected() -> None:
  with pytest.raises(ValueError, match='honor_leads_KQx'):
    bridgodex_to_swan.convert(
      {'settings': {'leads_vs_suits': {'honor_leads_KQx': True}}, 'notes': ''}
    )


# --- round trip ---


def test_the_full_export_round_trips_through_swan() -> None:
  document = json.loads(_FULL_EXPORT_PATH.read_text(encoding='utf-8'))
  for setting in BRIDGODEX_ONLY:
    document['settings'][setting.section].pop(setting.key, None)

  swan_result = bridgodex_to_swan.convert(document)
  round_tripped = swan_to_bridgodex.convert(swan_result.document)

  assert round_tripped.document['settings'] == document['settings']
  assert round_tripped.warnings == ()
