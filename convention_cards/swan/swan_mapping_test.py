# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

"""Consistency checks on the mapping table.

The table must cover the Bridgodex key list exactly, map no key or SWAN path
twice, and give each lead holding the right card positions.
"""

import json
from pathlib import Path

from bridgodex_key import BridgodexKey

from swan.swan_mapping import BRIDGODEX_ONLY, MAPPINGS, CircleLink, FieldLink

# The renderer's full-export fixture sets every Bridgodex key, so it doubles as
# the authoritative key list for the format.
_FULL_EXPORT_PATH = (
  Path(__file__).resolve().parent.parent
  / 'renderer'
  / 'testdata'
  / 'full_export.json'
)


def _bridgodex_format_keys() -> set[BridgodexKey]:
  document = json.loads(_FULL_EXPORT_PATH.read_text(encoding='utf-8'))
  return {
    BridgodexKey(section_name, key)
    for section_name, section in document['settings'].items()
    for key in section
  }


def test_every_bridgodex_key_is_mapped_or_bridgodex_only() -> None:
  mapped = {link.bridgodex for link in MAPPINGS}

  assert mapped | set(BRIDGODEX_ONLY) == _bridgodex_format_keys()


def test_no_bridgodex_key_is_both_mapped_and_bridgodex_only() -> None:
  mapped = {link.bridgodex for link in MAPPINGS}

  assert not mapped & set(BRIDGODEX_ONLY)


def test_bridgodex_keys_are_mapped_at_most_once() -> None:
  seen = [link.bridgodex for link in MAPPINGS]

  assert len(seen) == len(set(seen))


def _swan_leaf_paths(link: FieldLink) -> tuple[tuple[str, ...], ...]:
  """Every SWAN leaf path a link occupies — one per position for circles."""
  if isinstance(link, CircleLink):
    return tuple((*link.swan, position) for position in link.positions)
  return (link.swan,)


def test_swan_paths_are_mapped_at_most_once() -> None:
  seen = [path for link in MAPPINGS for path in _swan_leaf_paths(link)]

  assert len(seen) == len(set(seen))


def test_circle_position_counts_match_their_holdings() -> None:
  # The Bridgodex key names its holding (e.g. length_leads_Hxxx has four cards),
  # so the SWAN position list must be exactly that long.
  for link in MAPPINGS:
    if isinstance(link, CircleLink):
      holding = link.bridgodex.key.rsplit('_', 1)[-1]
      assert len(link.positions) == len(holding), link.bridgodex


def test_circle_bold_positions_lie_within_their_holdings() -> None:
  for link in MAPPINGS:
    if isinstance(link, CircleLink) and link.bold_position is not None:
      assert 1 <= link.bold_position <= len(link.positions), link.bridgodex
