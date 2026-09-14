# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

"""Convert a SWAN card (BridgeWinners export) to Bridgodex format.

Every leaf in the SWAN input must be accounted for: mapped to a Bridgodex key,
listed as SWAN-only (warned about when it carries content), or known format
metadata. An unrecognized leaf is a hard error, so a future BridgeWinners field
can't be dropped silently; the fix is to add the field to `swan_mapping`.

With `--synthesize-from-bridgewinners-pdf`, the card's own BridgeWinners PDF
supplies the bold length-lead defaults (see `bridgewinners_lead_bolds`), and
each unmarked length holding converts as if its bold card were circled — those
defaults are real agreements the ACBL card has no other way to show.

Usage, run from `convention_cards/`:
    python3 -m swan.swan_to_bridgodex INPUT.json OUTPUT.json \
        [--synthesize-from-bridgewinners-pdf CARD.pdf]
"""

import argparse
import json
import pathlib
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TextIO

from bridgodex_key import BridgodexKey

from swan.bridgewinners_lead_bolds import measure_length_bolds
from swan.swan_mapping import (
  IGNORED_SWAN_PATHS,
  MAPPINGS,
  SWAN_ONLY,
  CheckLink,
  CircleLink,
  TextLink,
  unset_leaves,
)


@dataclass(frozen=True)
class ConversionResult:
  """The converted document plus warnings about content that didn't fit.

  `synthesized` names the lead circles added from the BridgeWinners PDF's bold
  defaults rather than from explicit marks in the export.
  """

  document: dict[str, object]
  warnings: tuple[str, ...]
  synthesized: tuple[str, ...] = ()


def _flatten(
  node: object, path: tuple[str, ...], leaves: dict[tuple[str, ...], object]
) -> None:
  """Collect every non-dict value in the tree, keyed by its path."""
  if isinstance(node, dict):
    for key, child in node.items():
      # JSON object keys are always strings, but the narrowed dict's keys are
      # untyped; str() gives the type checker that guarantee.
      _flatten(child, (*path, str(key)), leaves)
  else:
    leaves[path] = node


def _swan_only_reason(path: tuple[str, ...]) -> str | None:
  """The `SWAN_ONLY` reason for this leaf, or None if it isn't SWAN-only."""
  for field in SWAN_ONLY:
    if path in unset_leaves(field):
      return field.reason
  return None


def convert(
  swan_document: object,
  bridgewinners_length_bolds: Mapping[BridgodexKey, int] | None = None,
) -> ConversionResult:
  """Convert a parsed SWAN document into a Bridgodex document.

  `bridgewinners_length_bolds` (from
  `bridgewinners_lead_bolds.measure_length_bolds`) maps length holdings to their
  bold position on the BridgeWinners card. Each unmarked holding in the map
  converts as if that bold card were circled.

  Raises:
    ValueError: if the SWAN input holds anything this converter can't account
      for.
  """
  if not isinstance(swan_document, dict):
    raise ValueError(f'input must be an object, got {type(swan_document)}')
  card = swan_document.get('Convention_Card')
  if not isinstance(card, dict):
    raise ValueError("input has no 'Convention_Card' object")

  leaves: dict[tuple[str, ...], object] = {}
  _flatten(card, (), leaves)

  settings: dict[str, dict[str, object]] = {}
  warnings: list[str] = []
  synthesized: list[str] = []
  problems: list[str] = []

  def place(setting: BridgodexKey, value: object) -> None:
    settings.setdefault(setting.section, {})[setting.key] = value

  for link in MAPPINGS:
    match link:
      case CheckLink():
        # SWAN checkboxes are booleans; an absent leaf counts as unchecked.
        if leaves.pop(link.swan, None):
          place(link.bridgodex, 'on')
      case TextLink():
        text = leaves.pop(link.swan, None)
        if text:
          if not isinstance(text, str):
            problems.append(f'{".".join(link.swan)} expects text, got {text!r}')
            continue
          place(link.bridgodex, text)
      case CircleLink():
        circled = [
          position
          for position in link.positions
          if leaves.pop((*link.swan, position), None)
        ]
        # On the ACBL card the bold card is already the default lead ("circle
        # card led if not bold"), so a SWAN mark at the bold position converts
        # to nothing.
        if link.bold_position is not None:
          bold_name = link.positions[link.bold_position - 1]
          circled = [position for position in circled if position != bold_name]
        if len(circled) > 1:
          kept = circled[0]
          warnings.append(
            f'{".".join(link.swan)}: positions {circled} are all circled,'
            f' but Bridgodex holds one circle — kept {kept!r}'
          )
        if circled:
          place(link.bridgodex, link.positions.index(circled[0]) + 1)
        elif (
          bridgewinners_length_bolds
          and link.bridgodex in bridgewinners_length_bolds
        ):
          position = bridgewinners_length_bolds[link.bridgodex]
          place(link.bridgodex, position)
          synthesized.append(
            f'{link.bridgodex} = {position}'
            " (the BridgeWinners card's bold default)"
          )

  # The link loop above popped every leaf it matched, so the leaves left are
  # exactly those no link covers, empty or not.
  for path, value in sorted(leaves.items()):
    if path in IGNORED_SWAN_PATHS:
      continue
    reason = _swan_only_reason(path)
    if reason is None:
      problems.append(f'unrecognized SWAN field {".".join(path)}')
    elif value:
      warnings.append(f'dropped {".".join(path)} = {value!r}: {reason}')

  if problems:
    details = '\n  '.join(problems)
    raise ValueError(f'SWAN input problems:\n  {details}')

  ordered = {
    name: dict(sorted(settings[name].items())) for name in sorted(settings)
  }
  return ConversionResult(
    document={'settings': ordered, 'notes': ''},
    warnings=tuple(warnings),
    synthesized=tuple(synthesized),
  )


def main(argv: Sequence[str] | None = None, stdin: TextIO = sys.stdin) -> int:
  """CLI entry point; returns a process exit status."""
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('input', help="SWAN JSON path, or '-' for stdin")
  parser.add_argument('output', help='Bridgodex JSON output path')
  parser.add_argument(
    '--synthesize-from-bridgewinners-pdf',
    metavar='CARD_PDF',
    help="the same card's BridgeWinners PDF; each unmarked length holding then"
    " converts as if the PDF's bold card were circled",
  )
  args = parser.parse_args(argv)

  if args.input == '-':
    swan_document = json.load(stdin)
  else:
    with pathlib.Path(args.input).open(encoding='utf-8') as handle:
      swan_document = json.load(handle)

  bridgewinners_length_bolds = None
  if args.synthesize_from_bridgewinners_pdf:
    bridgewinners_pdf = pathlib.Path(args.synthesize_from_bridgewinners_pdf)
    bridgewinners_length_bolds = measure_length_bolds(
      bridgewinners_pdf.read_bytes()
    )

  result = convert(swan_document, bridgewinners_length_bolds)

  with pathlib.Path(args.output).open('w', encoding='utf-8') as handle:
    json.dump(result.document, handle, indent=2)
    handle.write('\n')

  for warning in result.warnings:
    print(f'warning: {warning}')
  for note in result.synthesized:
    print(f'synthesized: {note}')
  print(f'Written: {args.output}')
  return 0


if __name__ == '__main__':
  sys.exit(main())
