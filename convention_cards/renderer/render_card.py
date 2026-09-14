# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

"""Render a convention card JSON file onto the official ACBL card PDF.

The base card page passes through untouched — pixel-perfect by construction —
and the entered content goes on top as an overlay in a swappable font (see
`spec.md`). The tool prints a report of every field whose entry had to shrink
below the field's default size, so the user can see where content is pushing the
limits.

Usage, run from `convention_cards/`:
    python3 -m renderer.render_card INPUT.json OUTPUT.pdf
"""

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, TextIO

from pypdf import PageObject, PdfReader, PdfWriter
from pypdf.generic import (
  ContentStream,
  DictionaryObject,
  NameObject,
  StreamObject,
)
from reportlab.lib.colors import HexColor

from renderer.fonts import (
  DEFAULT_TEXT_FONT_PATH,
  DEFAULT_TEXT_FONT_SUBFONT,
  EntryFonts,
  register_entry_fonts,
)
from renderer.geometry import CardField, load_card_fields
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

# The name the output page's resources give the overlay's form XObject.
_OVERLAY_FORM_NAME = NameObject('/CardOverlay')


@dataclass(frozen=True)
class BaseCard:
  """The blank ACBL card, parsed once so that any number of renders share it.

  `page` is the card's only page, stripped of its form widgets, and `fields` the
  widgets' geometry (see `geometry.load_card_fields`). Rendering copies the page
  into its own output rather than drawing on it, so the page stays blank from
  one render to the next.
  """

  page: PageObject
  fields: Mapping[str, CardField]


@dataclass(frozen=True)
class RenderResult:
  """The finished card, plus every entry that had to shrink to fit its field."""

  pdf: bytes
  resized: tuple[ResizedField, ...]


def load_base_card(base_pdf: BinaryIO) -> BaseCard:
  """Parse the blank card PDF for rendering.

  Raises:
    ValueError: if the PDF's page or form doesn't match the card the renderer
      expects.
  """
  base_bytes = base_pdf.read()
  fields = load_card_fields(BytesIO(base_bytes))

  # The output never carries the widgets, so drop them from the page up front:
  # pypdf's page copy otherwise reads every one of them looking for links, which
  # costs more than the rest of the first copy combined.
  page = PdfReader(BytesIO(base_bytes)).pages[0]
  del page[NameObject('/Annots')]
  return BaseCard(page=page, fields=fields)


def render_card(
  card_json: TextIO,
  base_card: BaseCard,
  fonts: EntryFonts,
  palette: Palette = DEFAULT_PALETTE,
  size_floor: float = DEFAULT_SIZE_FLOOR,
) -> RenderResult:
  """Render the card JSON over the base card and return the finished PDF.

  Raises:
    ValueError: if the card JSON is malformed or asks for something the card
      can't show, or if `base_card` isn't the card the vocabulary describes.
  """
  settings = _validated_settings(card_json)
  placements = resolve_settings(settings)
  overlay = build_overlay(
    placements, base_card.fields, fonts, palette, size_floor
  )

  # The page carries no widgets, and the copy leaves out the form dictionary,
  # which lives on the document rather than the page — so the output prints as a
  # plain document.
  writer = PdfWriter()
  page = writer.add_page(base_card.page)
  _draw_overlay(writer, page, PdfReader(BytesIO(overlay.pdf)).pages[0])

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


def _draw_overlay(
  writer: PdfWriter, page: PageObject, overlay_page: PageObject
) -> None:
  """Draw `overlay_page` over `page`, which belongs to `writer`.

  The overlay goes in as a form XObject: a self-contained drawing that `page`
  paints by name. The form keeps the overlay's drawing instructions as they are,
  still compressed, and its own resources, so none of the overlay's resource
  names can collide with the page's.

  Raises:
    ValueError: if the overlay's page holds anything but a single stream of
      drawing instructions, or `page` already has a resource by the form's
      name.
  """
  # Cloning the stream's reference copies the stream into `writer`, which gives
  # the copy a reference of its own there.
  form_reference = overlay_page.raw_get(NameObject('/Contents')).clone(writer)
  form = form_reference.get_object()
  if not isinstance(form, StreamObject):
    raise ValueError(
      f'overlay page must hold one content stream, got {type(form).__name__}'
    )
  form[NameObject('/Type')] = NameObject('/XObject')
  form[NameObject('/Subtype')] = NameObject('/Form')
  # A form draws only inside its box, so the overlay stays on its page.
  form[NameObject('/BBox')] = overlay_page.mediabox
  form[NameObject('/Resources')] = overlay_page.raw_get(
    NameObject('/Resources')
  ).clone(writer)

  resources = _subdictionary(page, '/Resources')
  xobjects = _subdictionary(resources, '/XObject')
  if _OVERLAY_FORM_NAME in xobjects:
    raise ValueError(
      f'the card page already has a resource named {_OVERLAY_FORM_NAME}'
    )
  xobjects[_OVERLAY_FORM_NAME] = form_reference

  # Draw the page's own content inside a saved graphics state, so no state it
  # leaves behind reaches the overlay, and then paint the form over it.
  content = page.get_contents()
  if content is None:
    content = ContentStream(None, writer)
  content.isolate_graphics_state()
  content.set_data(content.get_data() + f'{_OVERLAY_FORM_NAME} Do\n'.encode())
  page.replace_contents(content)


def _subdictionary(parent: DictionaryObject, key: str) -> DictionaryObject:
  """The dictionary `parent` holds under `key`, added empty if absent.

  Raises:
    ValueError: if `key` holds something other than a dictionary.
  """
  name = NameObject(key)
  if name not in parent:
    parent[name] = DictionaryObject()
  value = parent[name]
  if not isinstance(value, DictionaryObject):
    raise ValueError(f'{key} holds a {type(value).__name__}, not a dictionary')
  return value


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
  with args.base_pdf.open('rb') as base_pdf:
    base_card = load_base_card(base_pdf)

  def _render(card_json: TextIO) -> RenderResult:
    return render_card(card_json, base_card, fonts, palette, args.size_floor)

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
