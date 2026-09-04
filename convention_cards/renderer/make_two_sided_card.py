# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

"""Compose a two-sided, single-cut print sheet for a convention card.

Takes the two maintained versions of one card — a Bridgodex JSON export and a
hand-built HTML page — and produces a two-page US Letter PDF that prints
double-sided (long-edge duplex): the ACBL-rendered JSON version on the front,
the HTML version on the back. One straight cut along the front's dashed guide
yields an 8.5" x 8.42" piece, empirically verified to fit well into a standard
convention card holder. The odd height is a sum, not a chosen dimension — hard
margin plus content budget plus cut allowance; padding the cut allowance to
square the piece at 8.5" would buy only blank paper.

Layout: ink keeps `HARD_MARGIN` (0.18") clear of every paper edge of the piece —
the printer's non-printable allowance, the difference between paper size and
printable area. The one exception is the cut edge: interior paper, printable to
the line, needing only `CUT_ALLOWANCE` of clearance for the error of a
hand-guided cut.

Between the side margins, letter paper offers 8.14" of printable width, and each
face's content fits a square of that width, `CARD_BUDGET`. Both cards print
upright, so the long-edge duplex flip — turning the piece like a book page —
carries one card straight to the other, both reading the same way up.

The ACBL card prints scaled down to `ACBL_CARD_SCALE` with its proportions kept,
its taller side spanning the budget exactly; the HTML card's own layout already
fits the budget, so it prints at 100%. Three edges of the cut piece are paper
edges, so a single cut suffices.

The HTML is converted through Playwright's bundled headless Chromium — the same
engine family the card was proofed in — with the maintained HTML untouched: its
text renders as the page content, and the font faces the stack needs are
injected into the live page (see `convert_html_card`).

Usage, run from `convention_cards/`:
    python3 -m renderer.make_two_sided_card CARD.html CARD.json OUTPUT.pdf
"""

import argparse
import base64
import pathlib
from collections.abc import Mapping
from io import BytesIO

import pypdfium2
from playwright.sync_api import sync_playwright
from pypdf import PdfReader, PdfWriter, Transformation
from reportlab.pdfgen import canvas

from renderer.fonts import register_entry_fonts
from renderer.private_paths import discover_private_assets
from renderer.render_card import (
  DEFAULT_BASE_PDF_PATH,
  RenderResult,
  print_resized_entries,
  render_card,
)

# ---------------------------------------------------------------------------
# Page geometry (PDF points; origin at bottom-left of page)
# ---------------------------------------------------------------------------

PAGE_WIDTH = 612  # 8.5"
PAGE_HEIGHT = 792  # 11"

# Ink keeps this margin from every paper edge of the trimmed piece — the
# printer's non-printable allowance, shared with the scoresheets' convention
# (bridge-scoresheets repo, scoresheet_v4.html, `--hard-margin: 0.18in`).
HARD_MARGIN = 0.18 * 72

# The cut edge is interior paper — printable right up to the line — so ink
# beside it needs only room for the error of a hand-guided cut.
CUT_ALLOWANCE = 0.1 * 72

# Each face's content fits one square budget — the widest square the paper
# allows between the side margins. The cut sits just past the budget, making the
# trimmed piece the paper's full width by
# `HARD_MARGIN + CARD_BUDGET + CUT_ALLOWANCE` (8.5" x 8.42").
CARD_BUDGET = PAGE_WIDTH - 2 * HARD_MARGIN
CUT_Y = PAGE_HEIGHT - HARD_MARGIN - CARD_BUDGET - CUT_ALLOWANCE

# The ACBL card is 576 x 612 pt (8" x 8.5"): its taller side binds against the
# square budget, and the uniform scale keeps its proportions.
ACBL_CARD_WIDTH = 576
ACBL_CARD_HEIGHT = 612
ACBL_CARD_SCALE = CARD_BUDGET / max(ACBL_CARD_WIDTH, ACBL_CARD_HEIGHT)

_FONTS_DIRECTORY = discover_private_assets().fonts_directory

# ---------------------------------------------------------------------------
# HTML-to-PDF conversion
# ---------------------------------------------------------------------------

# The HTML's own font stack. The conversion keeps it intact: the card's suit
# symbols come from Source Sans 3 — the first stack family that carries them —
# so trimming the stack would change glyphs. (The card's open suit variants are
# the same filled glyphs stroked open by the HTML's own CSS, so no font outside
# the stack is involved.) The check that this exact declaration is still present
# guards the font table below: without it, a drifted stack would silently stop
# matching the table.
_FONT_STACK = (
  'font-family: "Roboto Condensed", "Source Sans 3", "IBM Plex Sans",'
  ' "Verdana", sans-serif;'
)

# Headless Chromium on macOS gives up on glyph fallback (suit symbols render as
# missing-glyph boxes) when a stack names a family that resolves to nothing, so
# every family in the stack must resolve. The conversion injects @font-face
# rules for each web family under its own name, backed by the private repo's
# font files: a roman and an italic variable file each, serving every weight the
# card asks for through one variable-range descriptor. Injected unconditionally
# — these are the same files the families install from, and a declared face
# shadowing an installed family keeps the conversion identical on every machine.
_WEB_FAMILY_FONT_FILES: Mapping[str, Mapping[str, str]] = {
  'Roboto Condensed': {
    'normal': 'RobotoCondensed-variable.ttf',
    'italic': 'RobotoCondensed-Italic-variable.ttf',
  },
  'Source Sans 3': {
    'normal': 'SourceSans3-variable.ttf',
    'italic': 'SourceSans3-Italic-variable.ttf',
  },
  'IBM Plex Sans': {
    'normal': 'IBMPlexSans-variable.ttf',
    'italic': 'IBMPlexSans-Italic-variable.ttf',
  },
}


def _stack_font_faces() -> str:
  """CSS `@font-face` rules serving the stack families from private-repo files.

  Each family gets a roman and an italic face carrying a full variable weight
  range — Chromium clamps a requested weight to the file's actual axis — with
  the font data inlined as a data URI, so the injected styles carry no file
  references.
  """
  rules = []
  for family, files in _WEB_FAMILY_FONT_FILES.items():
    for style, file_name in files.items():
      font = (_FONTS_DIRECTORY / file_name).read_bytes()
      encoded = base64.b64encode(font).decode('ascii')
      rules.append(
        '@font-face {\n'
        f"  font-family: '{family}';\n"
        f'  font-style: {style};\n'
        '  font-weight: 100 900;\n'
        f"  src: url('data:font/ttf;base64,{encoded}');\n"
        '}\n'
      )
  return ''.join(rules)


def convert_html_card(html: str) -> bytes:
  """Convert the maintained card HTML to a one-page letter PDF.

  The page renders in Playwright's bundled headless Chromium from the given
  string, so the maintained file is never modified: the font faces are added to
  the live page as a style tag, and `document.fonts.ready` holds the print until
  they finish applying. The PDF prints letter-size with zero margins, standing
  in for the margin-free print-dialog settings the card was proofed with.

  Raises:
    ValueError: if the HTML lacks the font-family declaration this script
      supplies faces for.
    RuntimeError: if the browser's PDF is anything but one letter-size page.
  """
  if _FONT_STACK not in html:
    raise ValueError(
      'the card HTML no longer contains the expected font-family'
      f' declaration:\n  {_FONT_STACK}\n'
      'Update _FONT_STACK and _WEB_FAMILY_FONT_FILES in'
      ' make_two_sided_card.py to match the HTML.'
    )
  with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    try:
      page = browser.new_page()
      page.set_content(html)
      page.add_style_tag(content=_stack_font_faces())
      page.evaluate('document.fonts.ready')
      pdf_bytes = page.pdf(
        format='Letter',
        margin={'top': '0', 'right': '0', 'bottom': '0', 'left': '0'},
        print_background=True,
      )
    finally:
      browser.close()

  pages = PdfReader(BytesIO(pdf_bytes)).pages
  if len(pages) != 1:
    raise RuntimeError(
      f'HTML conversion produced {len(pages)} pages instead of 1 — the'
      ' layout overflowed, which usually means a font failed to load'
    )
  size = (pages[0].mediabox.width, pages[0].mediabox.height)
  if size != (PAGE_WIDTH, PAGE_HEIGHT):
    raise RuntimeError(f'HTML conversion page size is {size}, expected letter')
  return pdf_bytes


# ---------------------------------------------------------------------------
# ACBL rendering
# ---------------------------------------------------------------------------


def render_acbl_card(json_path: pathlib.Path) -> RenderResult:
  """Render the Bridgodex JSON through the ACBL card renderer, in process."""
  fonts = register_entry_fonts()
  with (
    DEFAULT_BASE_PDF_PATH.open('rb') as base_pdf,
    json_path.open(encoding='utf-8') as card_json,
  ):
    return render_card(card_json, base_pdf, fonts)


# ---------------------------------------------------------------------------
# Sheet composition
# ---------------------------------------------------------------------------


def _cut_guide_overlay() -> BytesIO:
  """A dashed guide line just below the cut, ends held out of the margins."""
  buffer = BytesIO()
  guide = canvas.Canvas(buffer, pagesize=(PAGE_WIDTH, PAGE_HEIGHT))
  guide.setStrokeColorRGB(0.45, 0.45, 0.45)
  guide.setLineWidth(0.6)
  guide.setDash(5, 4)
  guide.line(HARD_MARGIN, CUT_Y - 0.5, PAGE_WIDTH - HARD_MARGIN, CUT_Y - 0.5)
  guide.save()
  buffer.seek(0)
  return buffer


def _warn_when_html_card_outgrows_the_piece(html_pdf: bytes) -> None:
  """Print a warning when the HTML card's ink runs past its height budget.

  The HTML card's top sits `HARD_MARGIN` in from the piece's edge, and its box
  is capped at the square `CARD_BUDGET` — so ink past the budget means the
  card's layout has overflowed its box, toward the cut line, which must stay off
  the card.
  """
  document = pypdfium2.PdfDocument(html_pdf)
  try:
    image = document[0].render(scale=1, may_draw_forms=False).to_pil()
  finally:
    document.close()
  ink_box = image.convert('L').point(lambda value: value < 240).getbbox()
  if not ink_box:
    return
  content_bottom = PAGE_HEIGHT - ink_box[3]
  content_height = (PAGE_HEIGHT - HARD_MARGIN) - content_bottom
  budget = CARD_BUDGET
  if content_height > budget:
    print(
      f'WARNING: the HTML card runs {content_height - budget:.0f}pt past'
      ' its height budget, toward and possibly across the cut line'
    )


def compose_sheet(acbl_pdf: bytes, html_pdf: bytes) -> bytes:
  """Lay both card renderings onto a two-page duplex letter sheet."""
  acbl_page = PdfReader(BytesIO(acbl_pdf)).pages[0]
  acbl_size = (acbl_page.mediabox.width, acbl_page.mediabox.height)
  if acbl_size != (ACBL_CARD_WIDTH, ACBL_CARD_HEIGHT):
    raise ValueError(f'ACBL render is {acbl_size}, expected 576 x 612')
  html_page = PdfReader(BytesIO(html_pdf)).pages[0]
  _warn_when_html_card_outgrows_the_piece(html_pdf)

  writer = PdfWriter()

  # Front: shrink the card to the square budget and lay it upright — the same
  # orientation as the back's HTML card, which is what makes the duplex flip
  # read like turning a book page. The translation centers the scaled width
  # across the paper and hangs the scaled height from the top hard margin; the
  # height spans the budget exactly, ending at the cut allowance.
  front = writer.add_blank_page(PAGE_WIDTH, PAGE_HEIGHT)
  scaled_width = ACBL_CARD_WIDTH * ACBL_CARD_SCALE
  scaled_height = ACBL_CARD_HEIGHT * ACBL_CARD_SCALE
  front.merge_transformed_page(
    acbl_page,
    Transformation()
    .scale(ACBL_CARD_SCALE)
    .translate(
      (PAGE_WIDTH - scaled_width) / 2,
      PAGE_HEIGHT - HARD_MARGIN - scaled_height,
    ),
  )
  front.merge_page(PdfReader(_cut_guide_overlay()).pages[0])

  # Back: long-edge duplex mirrors the sheet left-right, printing the two cards
  # back to back on the piece. The HTML page is portrait letter too, with its
  # card upright in the top 8.5" x 8.42" — exactly the piece's band on the sheet
  # — so the page overlays unmoved.
  back = writer.add_blank_page(PAGE_WIDTH, PAGE_HEIGHT)
  back.merge_page(html_page)

  output = BytesIO()
  writer.write(output)
  return output.getvalue()


# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
  """Parse the two card versions and the output path from the command line."""
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument(
    'html_card', type=pathlib.Path, help='hand-built HTML card'
  )
  parser.add_argument(
    'json_card', type=pathlib.Path, help='Bridgodex JSON export'
  )
  parser.add_argument('output', type=pathlib.Path, help='print-ready PDF path')
  return parser.parse_args()


def main() -> None:
  """Build the two-sided print sheet from the two card versions."""
  args = _parse_args()
  acbl_render = render_acbl_card(args.json_card)
  print_resized_entries(acbl_render.resized)
  html = args.html_card.read_text(encoding='utf-8')
  args.output.write_bytes(
    compose_sheet(acbl_render.pdf, convert_html_card(html))
  )
  print(f'Written: {args.output}')


if __name__ == '__main__':
  main()
