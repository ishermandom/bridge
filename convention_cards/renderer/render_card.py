# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

"""Render a convention card JSON file onto the official ACBL card PDF.

The base card page passes through untouched — pixel-perfect by construction —
and the entered content merges on top as an overlay in a swappable font (see
`spec.md`). The tool prints a report of every field whose entry had to shrink
below the field's default size, so the user can see where content is pushing the
limits.

Usage, run from `convention_cards/`:
    python3 -m renderer.render_card INPUT.json OUTPUT.pdf
"""

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass, replace
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, TextIO

from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject
from reportlab.lib.colors import HexColor

from renderer.fonts import (
  DEFAULT_TEXT_FONT_PATH,
  DEFAULT_TEXT_FONT_SUBFONT,
  EntryFonts,
  register_entry_fonts,
)
from renderer.geometry import load_card_fields
from renderer.overlay import (
  DEFAULT_PALETTE,
  DEFAULT_SIZE_FLOOR,
  Palette,
  ResizedField,
  build_overlay,
)
from renderer.private_paths import discover_private_assets
from renderer.vocabulary import resolve_settings

DEFAULT_BASE_PDF_PATH = discover_private_assets().base_acbl_card_pdf


@dataclass(frozen=True)
class RenderResult:
  """The finished card, plus every entry that had to shrink to fit its field."""

  pdf: bytes
  resized: tuple[ResizedField, ...]


def render_card(
  card_json: TextIO,
  base_pdf: BinaryIO,
  fonts: EntryFonts,
  palette: Palette = DEFAULT_PALETTE,
  size_floor: float = DEFAULT_SIZE_FLOOR,
) -> RenderResult:
  """Render the card JSON over the base card and return the merged PDF.

  Raises:
    ValueError: if the card JSON is malformed or asks for something the card
      can't show, or if `base_pdf` isn't the card the vocabulary describes.
  """
  settings = _validated_settings(card_json)
  placements = resolve_settings(settings)

  base_bytes = base_pdf.read()
  fields = load_card_fields(BytesIO(base_bytes))
  overlay = build_overlay(placements, fields, fonts, palette, size_floor)

  writer = PdfWriter()
  writer.append(PdfReader(BytesIO(base_bytes)))
  page = writer.pages[0]
  page.merge_page(PdfReader(BytesIO(overlay.pdf)).pages[0])
  _strip_form(writer)

  output = BytesIO()
  writer.write(output)
  return RenderResult(pdf=output.getvalue(), resized=overlay.resized)


def print_resized_entries(resized: Sequence[ResizedField]) -> None:
  """Print one line per entry that had to shrink below its default size."""
  for entry in resized:
    wrap = f' on {entry.line_count} lines' if entry.line_count > 1 else ''
    print(
      f'resized: {entry.field_name} {entry.default_size:g}pt'
      f' -> {entry.fitted_size:.2f}pt{wrap}  {entry.text!r}'
    )


def _validated_settings(card_json: TextIO) -> dict[str, object]:
  """Parse and structurally validate the card JSON's top level."""
  document = json.load(card_json)
  if not isinstance(document, dict):
    raise ValueError(f'card JSON must be an object, got {type(document)}')

  unknown = sorted(set(document) - {'settings', 'notes'})
  if unknown:
    raise ValueError(f'unknown top-level keys: {", ".join(unknown)}')

  # `notes` has no home on the one-page card, so non-empty notes would drop
  # content silently — a hard error instead (spec.md #vocabulary).
  notes = document.get('notes', '')
  if notes:
    raise ValueError(f'notes are unsupported, got {notes!r:.120}')

  settings = document.get('settings')
  if not isinstance(settings, dict):
    raise ValueError(f'settings must be an object, got {settings!r:.120}')
  return settings


def _strip_form(writer: PdfWriter) -> None:
  """Remove the form dictionary and widgets, leaving a plain document."""
  page = writer.pages[0]
  if '/Annots' in page:
    del page[NameObject('/Annots')]
  root = writer.root_object
  if '/AcroForm' in root:
    del root[NameObject('/AcroForm')]


def main(argv: Sequence[str] | None = None, stdin: TextIO = sys.stdin) -> int:
  """CLI entry point; returns a process exit status."""
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('input', help="card JSON path, or '-' for standard input")
  parser.add_argument('output', type=Path, help='output PDF path')
  parser.add_argument(
    '--base-pdf',
    type=Path,
    default=DEFAULT_BASE_PDF_PATH,
    help='blank ACBL card PDF (default: %(default)s)',
  )
  parser.add_argument(
    '--font',
    type=Path,
    default=None,
    help='entry text font file (default: the pinned Google Sans Flex cut)',
  )
  parser.add_argument(
    '--font-subfont',
    type=int,
    default=None,
    help='face index within a .ttc collection (default: 0)',
  )
  parser.add_argument(
    '--color',
    default=None,
    help='entry color as hex, e.g. #1230B0 (default: black)',
  )
  parser.add_argument(
    '--size-floor',
    type=float,
    default=DEFAULT_SIZE_FLOOR,
    help='minimum font size before erroring (default: %(default)s)',
  )
  args = parser.parse_args(argv)

  if args.font is None and args.font_subfont is not None:
    parser.error('--font-subfont requires --font')
  if args.font is None:
    font_path, subfont = DEFAULT_TEXT_FONT_PATH, DEFAULT_TEXT_FONT_SUBFONT
  else:
    font_path, subfont = args.font, args.font_subfont or 0

  palette = DEFAULT_PALETTE
  if args.color is not None:
    palette = replace(palette, entry=HexColor(args.color))

  fonts = register_entry_fonts(font_path, subfont)

  def _render(card_json: TextIO) -> RenderResult:
    with args.base_pdf.open('rb') as base_pdf:
      return render_card(card_json, base_pdf, fonts, palette, args.size_floor)

  if args.input == '-':
    result = _render(stdin)
  else:
    with Path(args.input).open(encoding='utf-8') as card_json:
      result = _render(card_json)

  args.output.write_bytes(result.pdf)
  print_resized_entries(result.resized)
  return 0


if __name__ == '__main__':
  sys.exit(main())
