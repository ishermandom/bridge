# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

"""Build the font-comparison specimen sheet for printing.

One block per candidate font: the same dense card-style line at each size the
renderer actually uses, in the entry palette with four-color suit symbols, so
the printed sheet compares exactly what the card would show.
"""

from pathlib import Path

from reportlab.pdfbase.pdfmetrics import registerFont, stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from renderer.markup import parse_suit_markup
from renderer.overlay import DEFAULT_PALETTE
from renderer.private_paths import discover_private_assets

# The candidate collection and the printed sheet live in the bridge-private
# sibling repo, whose `fonts/README.md` records each file's provenance.
FONTS_DIR = discover_private_assets().fonts_directory
OUT_PATH = FONTS_DIR / 'specimen.pdf'

# (label, path, subfont index, extra letter spacing as a fraction of size)
#
# Ordered as pairs: each face's regular cut, then its stronger variant.
CANDIDATES = [
  ('Roboto Flex (8pt caption cut)', FONTS_DIR / 'RobotoFlex-opsz8.ttf', 0, 0.0),
  (
    'Roboto Flex 8pt GRADE+50 (weight, same width)',
    FONTS_DIR / 'RobotoFlex-opsz8-grad50.ttf',
    0,
    0.0,
  ),
  (
    'Google Sans Flex (6pt Condensed)',
    FONTS_DIR / 'GoogleSansFlex-opsz6-Condensed.ttf',
    0,
    0.0,
  ),
  (
    'Google Sans Flex 6pt Condensed MEDIUM',
    FONTS_DIR / 'GoogleSansFlex-opsz6-Condensed-Medium.ttf',
    0,
    0.0,
  ),
  (
    'Google Sans Flex 6pt SuperCondensed MEDIUM',
    FONTS_DIR / 'GoogleSansFlex-opsz6-SuperCondensed-Medium.ttf',
    0,
    0.0,
  ),
  (
    'Google Sans Flex 6pt SuperCondensed GRADE100 (Medium stroke, narrower)',
    FONTS_DIR / 'GoogleSansFlex-opsz6-SuperCondensed-Grad100.ttf',
    0,
    0.0,
  ),
  (
    'IBM Plex Sans Condensed',
    FONTS_DIR / 'IBMPlexSansCondensed-Regular.ttf',
    0,
    0.0,
  ),
  (
    'IBM Plex Condensed MEDIUM',
    FONTS_DIR / 'IBMPlexSansCondensed-Medium.ttf',
    0,
    0.0,
  ),
  ('PT Sans Narrow', FONTS_DIR / 'PTSansNarrow-Regular.ttf', 0, 0.0),
  (
    'PT Sans Narrow TRACKED +1.5% (opened spacing)',
    FONTS_DIR / 'PTSansNarrow-Regular.ttf',
    0,
    0.015,
  ),
  ('Roboto Condensed', FONTS_DIR / 'RobotoCondensed-Regular.ttf', 0, 0.0),
  (
    'Roboto Condensed MEDIUM',
    FONTS_DIR / 'RobotoCondensed-Medium.ttf',
    0,
    0.0,
  ),
  (
    'Avenir Next Condensed (current default)',
    Path('/System/Library/Fonts/Avenir Next Condensed.ttc'),
    7,
    0.0,
  ),
  (
    'Avenir Next Condensed MEDIUM',
    Path('/System/Library/Fonts/Avenir Next Condensed.ttc'),
    5,
    0.0,
  ),
]

SYMBOL_FONT = '/System/Library/Fonts/Apple Symbols.ttf'

# The renderer's default is 8pt and the user considers anything below 6pt not
# worth printing, so sample the usable band in half-point steps.
SIZES = [8.0, 7.5, 7.0, 6.5, 6.0]
# A dense card-style line; the tail packs confusable glyphs (Ill/1lb/0O) and
# card-number strings.
SAMPLE = (
  'Kokish 2!h; Parrish 2!s aft. bust — 3!c=Wolff signoff, 3!d=checkback;'
  ' Ill. 1lb 0O KQT9 1430'
)
PAGE_WIDTH, PAGE_HEIGHT = 612, 792
LEFT = 40

registerFont(TTFont('Symbols', SYMBOL_FONT))
canvas = Canvas(str(OUT_PATH), pagesize=(PAGE_WIDTH, PAGE_HEIGHT))

canvas.setFont('Helvetica-Bold', 13)
canvas.drawString(LEFT, PAGE_HEIGHT - 46, 'Convention card font specimen')
canvas.setFont('Helvetica', 8)
canvas.setFillGray(0.35)
canvas.drawString(
  LEFT,
  PAGE_HEIGHT - 60,
  'Same entry text from the 8pt default down to the 6pt legibility floor;'
  " width = the sample line's width at 6pt (smaller fits more).",
)

# `y` is annotated at its first assignment, which covers the page-break reset
# below: the per-size step is fractional, so the cursor is a float from the
# start even though the page height is whole.
y: float = PAGE_HEIGHT - 92
runs = parse_suit_markup(SAMPLE)
for index, (label, path, subfont, tracking) in enumerate(CANDIDATES):
  # Blocks come in regular/stronger pairs; break the page before a pair that
  # wouldn't fit whole (~88pt per block), and mid-pair as a backstop when even
  # one more block wouldn't fit.
  is_pair_start = index % 2 == 0
  if (is_pair_start and y < 218) or y < 130:
    canvas.showPage()
    y = PAGE_HEIGHT - 60

  font_name = f'Specimen-{label}'
  registerFont(TTFont(font_name, str(path), subfontIndex=subfont))
  plain = SAMPLE.replace('!h', 'H').replace('!s', 'S')
  plain = plain.replace('!c', 'C').replace('!d', 'D')
  metric = stringWidth(plain, font_name, 6.0)
  metric += tracking * 6.0 * len(plain)

  canvas.setFillGray(0.0)
  canvas.setFont('Helvetica-Bold', 9)
  canvas.drawString(LEFT, y, f'{label}   ({metric:.0f}pt wide at 6pt)')
  y -= 13

  for size in SIZES:
    canvas.setFillGray(0.45)
    canvas.setFont('Helvetica', 6)
    canvas.drawString(LEFT, y, f'{size:g}pt')
    # A cursor, not a page constant: each run advances it by a measured width
    # plus its share of the tracking, both fractional.
    x: float = LEFT + 24
    for run in runs:
      run_font = 'Symbols' if run.suit else font_name
      text = canvas.beginText(x, y)
      text.setFont(run_font, size)
      text.setCharSpace(tracking * size)
      text.setFillColor(DEFAULT_PALETTE.for_run(run))
      text.textOut(run.text)
      canvas.drawText(text)
      x += stringWidth(run.text, run_font, size)
      x += tracking * size * len(run.text)
    y -= size + 6.5

  y -= 14

canvas.showPage()
canvas.save()
print(f'Written: {OUT_PATH}')
