# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

"""Convert a Bridgodex card to SWAN format (BridgeWinners import).

The output carries every field a BridgeWinners export does, the SWAN-only ones
included, since BridgeWinners' import fails on a file that lacks any of them.
Each field starts unset — checkboxes false, text blank — and the input's content
is applied over that. Where a lead holding is uncircled and the ACBL card prints
a bold default for it, the output marks that bold card: on the ACBL card, an
uncircled holding means the bold card is led. An unrecognized Bridgodex key is a
hard error; keys with no SWAN home are warned about when they carry content.

Usage, run from `convention_cards/`:
    python3 -m swan.bridgodex_to_swan INPUT.json OUTPUT.json
"""

import argparse
import json
import pathlib
import sys
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import TextIO

from bridgodex_key import BridgodexKey

from swan.swan_mapping import (
  BRIDGODEX_ONLY,
  MAPPINGS,
  SWAN_ONLY,
  CheckLink,
  CircleLink,
  FieldLink,
  TextLink,
  unset_leaves,
)


@dataclass(frozen=True)
class ConversionResult:
  """The converted document plus warnings about content that didn't fit."""

  document: dict[str, object]
  warnings: tuple[str, ...]


def _set_leaf(
  root: dict[str, object], path: tuple[str, ...], value: object
) -> None:
  """Write one leaf into the nested SWAN tree, creating objects as needed."""
  node = root
  for part in path[:-1]:
    child = node.setdefault(part, {})
    assert isinstance(child, dict)
    node = child
  node[path[-1]] = value


def _skeleton() -> dict[str, object]:
  """Every field a BridgeWinners export carries, each at its unset value."""
  root: dict[str, object] = {'New_Format': True}
  for field in (*MAPPINGS, *SWAN_ONLY):
    for path, value in unset_leaves(field).items():
      _set_leaf(root, path, value)
  return root


def _mark_bold_defaults(
  root: dict[str, object], circled: Collection[BridgodexKey]
) -> None:
  """Mark the bold card of every uncircled holding that has one.

  On the ACBL card, players circle a lead only where it departs from the card
  printed in bold, so an uncircled holding means its bold card is led. Marking
  that card keeps the agreement explicit on the SWAN side, whatever default
  BridgeWinners would otherwise show.
  """
  for link in MAPPINGS:
    if (
      isinstance(link, CircleLink)
      and link.bold_position is not None
      and link.bridgodex not in circled
    ):
      bold_card = link.positions[link.bold_position - 1]
      _set_leaf(root, (*link.swan, bold_card), True)


def _links_by_bridgodex_key() -> dict[BridgodexKey, FieldLink]:
  """Index the mapping table by its Bridgodex side."""
  return {link.bridgodex: link for link in MAPPINGS}


def convert(bridgodex_document: object) -> ConversionResult:
  """Convert a parsed Bridgodex document into a SWAN document.

  Raises:
    ValueError: if the Bridgodex input holds anything this converter can't
      account for.
  """
  if not isinstance(bridgodex_document, dict):
    raise ValueError(f'input must be an object, got {type(bridgodex_document)}')
  settings = bridgodex_document.get('settings')
  if not isinstance(settings, dict):
    raise ValueError("input has no 'settings' object")
  notes = bridgodex_document.get('notes', '')
  if notes:
    raise ValueError(f'notes have no home on a SWAN card, got {notes!r:.120}')

  links = _links_by_bridgodex_key()
  root = _skeleton()
  warnings: list[str] = []
  problems: list[str] = []
  circled: set[BridgodexKey] = set()

  for section_name, section in sorted(settings.items()):
    if not isinstance(section, dict):
      problems.append(f'section {section_name!r} is not an object')
      continue
    for key, value in sorted(section.items()):
      setting = BridgodexKey(section_name, key)
      reason = BRIDGODEX_ONLY.get(setting)
      if reason is not None:
        if value:
          warnings.append(f'dropped {setting} = {value!r}: {reason}')
        continue

      link = links.get(setting)
      match link:
        case None:
          problems.append(f'unknown key {setting}')
        case CheckLink():
          if value != 'on':
            problems.append(f"{setting} expects 'on', got {value!r}")
          else:
            _set_leaf(root, link.swan, True)
        case TextLink():
          if not isinstance(value, str) or not value:
            problems.append(f'{setting} expects non-empty text, got {value!r}')
          else:
            _set_leaf(root, link.swan, value)
        case CircleLink():
          position_count = len(link.positions)
          # bool subclasses int, so screen it out before the integer checks.
          if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 1 <= value <= position_count
          ):
            problems.append(
              f'{setting} expects a card position 1..{position_count},'
              f' got {value!r}'
            )
          else:
            _set_leaf(root, (*link.swan, link.positions[value - 1]), True)
            circled.add(setting)

  if problems:
    details = '\n  '.join(problems)
    raise ValueError(f'Bridgodex input problems:\n  {details}')

  _mark_bold_defaults(root, circled)

  return ConversionResult(
    document={'Convention_Card': root}, warnings=tuple(warnings)
  )


def main(argv: Sequence[str] | None = None, stdin: TextIO = sys.stdin) -> int:
  """CLI entry point; returns a process exit status."""
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('input', help="Bridgodex JSON path, or '-' for stdin")
  parser.add_argument('output', help='SWAN JSON output path')
  args = parser.parse_args(argv)

  if args.input == '-':
    bridgodex_document = json.load(stdin)
  else:
    with pathlib.Path(args.input).open(encoding='utf-8') as handle:
      bridgodex_document = json.load(handle)

  result = convert(bridgodex_document)

  with pathlib.Path(args.output).open('w', encoding='utf-8') as handle:
    json.dump(result.document, handle, indent=2)
    handle.write('\n')

  for warning in result.warnings:
    print(f'warning: {warning}')
  print(f'Written: {args.output}')
  return 0


if __name__ == '__main__':
  sys.exit(main())
