# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

"""Build the suit-tone specimen sheet for black-and-white print testing.

Each block shows one candidate palette: a card-style sample line at 8pt and 6pt
in full color and again with every suit color replaced by the gray a
black-and-white printer would produce (the color's relative-luminance gray).
Equal grays across the four suits mean no suit fades first; each suit's own
silhouette identifies it. Candidates keep each suit's exact hue
(chromaticity-preserving rescaling) and differ only in the target lightness.
"""

from fontTools.ttLib import TTFont as MetricsFont
from reportlab.lib.colors import HexColor
from reportlab.pdfbase.pdfmetrics import registerFont, stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from renderer.fonts import DEFAULT_TEXT_FONT_PATH
from renderer.private_paths import discover_private_assets

# The printed sheet embeds the entry font, so it stays in the bridge-private
# sibling repo like the font files themselves.
OUT_PATH = discover_private_assets().palette_directory / 'specimen.pdf'

SYMBOL_FONT = '/System/Library/Fonts/Apple Symbols.ttf'

SPADE, HEART, DIAMOND, CLUB = '♠', '♥', '♦', '♣'


def _symbol_size_factor() -> float:
  """How much to enlarge suit glyphs so they stand cap-height tall.

  Apple Symbols draws the suits only ~0.56 em tall — the entry font's x-height,
  which is why they read small beside the text.
  """
  symbols = MetricsFont(SYMBOL_FONT)
  units_per_em = symbols['head'].unitsPerEm
  cmap = symbols.getBestCmap()
  suit_height = max(
    symbols['glyf'][cmap[ord(glyph)]].yMax / units_per_em
    for glyph in (SPADE, HEART, DIAMOND, CLUB)
  )

  entry = MetricsFont(DEFAULT_TEXT_FONT_PATH)
  cap_height = entry['OS/2'].sCapHeight / entry['head'].unitsPerEm
  return cap_height / suit_height


SYMBOL_SIZE_FACTOR = _symbol_size_factor()

BASE = {
  'spades': 0x1230B0,
  'hearts': 0xC8102E,
  'diamonds': 0xE8871E,
  'clubs': 0x00843D,
}


def _to_linear(channel: int) -> float:
  """One sRGB channel byte to linear light."""
  scaled = channel / 255
  return (
    scaled / 12.92 if scaled <= 0.04045 else ((scaled + 0.055) / 1.055) ** 2.4
  )


def _to_byte(linear: float) -> int:
  """One linear-light channel back to an sRGB byte, clipped into gamut."""
  clipped = min(1.0, max(0.0, linear))
  encoded = (
    clipped * 12.92
    if clipped <= 0.0031308
    else 1.055 * clipped ** (1 / 2.4) - 0.055
  )
  return round(encoded * 255)


def _channels(color: int) -> tuple[int, int, int]:
  return (color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF


def luminance(color: int) -> float:
  """Relative luminance Y of an sRGB color — what a grayscale print keeps."""
  red, green, blue = (_to_linear(channel) for channel in _channels(color))
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def lightness(color: int) -> float:
  """CIE L* of an sRGB color: perceived brightness, 0 black to 100 white."""
  y = luminance(color)
  f = y ** (1 / 3) if y > 216 / 24389 else (24389 / 27 * y + 16) / 116
  return 116 * f - 16


def scaled_to_luminance(color: int, y_target: float) -> int:
  """The same chromaticity (hue and saturation) rescaled to a luminance."""
  factor = y_target / luminance(color)
  red, green, blue = (
    _to_byte(_to_linear(channel) * factor) for channel in _channels(color)
  )
  return (red << 16) | (green << 8) | blue


def gray_of(color: int) -> int:
  """The gray a black-and-white printer makes of a color: equal-Y neutral."""
  byte = _to_byte(luminance(color))
  return (byte << 16) | (byte << 8) | byte


EQUAL_42_PALETTE = {
  suit: scaled_to_luminance(color, 0.125) for suit, color in BASE.items()
}
BANDED_FURTHER_PALETTE = {
  suit: scaled_to_luminance(
    color, {'clubs': 0.132, 'diamonds': 0.160}.get(suit, 0.1125)
  )
  for suit, color in BASE.items()
}
GENTLE_PALETTE = {
  suit: scaled_to_luminance(
    color, {'clubs': 0.168, 'diamonds': 0.210}.get(suit, 0.125)
  )
  for suit, color in BASE.items()
}

# (label, palette): each palette maps suit name -> hex color.
CANDIDATES = [
  ('Current palette', dict(BASE)),
  ('Equal lightness L*42 (matches the current heart red)', EQUAL_42_PALETTE),
  (
    'Equal lightness L*38 (darker across the board)',
    {suit: scaled_to_luminance(color, 0.10) for suit, color in BASE.items()},
  ),
  (
    'Banded: three at L*40, diamond eases to L*46',
    {
      suit: scaled_to_luminance(color, 0.155 if suit == 'diamonds' else 0.1125)
      for suit, color in BASE.items()
    },
  ),
  (
    'Banded further: spade/heart L*40, club L*43, diamond L*47',
    BANDED_FURTHER_PALETTE,
  ),
  (
    'Gentle: spade/heart L*42, club stays L*48, diamond L*53',
    GENTLE_PALETTE,
  ),
]

# Page two attacks the spade/heart confusion directly: those two are the
# near-identical blob shapes, so the work of telling suits apart concentrates on
# them — either an open heart against a filled spade, or a deliberate lightness
# split. This palette does the latter: spade well darker than heart, the minors
# between them.
SPLIT_PALETTE = {
  suit: scaled_to_luminance(
    color,
    {'spades': 0.080, 'hearts': 0.153, 'clubs': 0.138, 'diamonds': 0.184}[suit],
  )
  for suit, color in BASE.items()
}

# Open forms of the red suits, and per-suit drawing forms: suit -> (glyph,
# outline boost as a fraction of symbol size; 0 draws the glyph as designed).
OPEN_HEART, OPEN_DIAMOND = '♡', '♢'
SuitForms = dict[str, tuple[str, float]]
FILLED_FORMS = {
  'spades': (SPADE, 0.0),
  'hearts': (HEART, 0.0),
  'diamonds': (DIAMOND, 0.0),
  'clubs': (CLUB, 0.0),
}


# The chosen forms: heart outline +8%, diamond +9%. The diamond's simpler shape
# holds the extra weight better, and its shorter perimeter deposits less total
# ink, so an extra percentage point of stroke evens the two suits' visual
# weight.
CHOSEN_FORMS = FILLED_FORMS | {
  'hearts': (OPEN_HEART, 0.08),
  'diamonds': (OPEN_DIAMOND, 0.09),
}

# (label, palette, forms) blocks for page two: the chosen forms across the live
# palette candidates.
SHAPE_BLOCKS = [
  ('Chosen forms — gentle palette', GENTLE_PALETTE, CHOSEN_FORMS),
  ('Chosen forms — banded further', BANDED_FURTHER_PALETTE, CHOSEN_FORMS),
  ('Chosen forms — equal L*42', EQUAL_42_PALETTE, CHOSEN_FORMS),
]

# (label, palette, forms) blocks for page three.
ALTERNATIVE_BLOCKS = [
  (
    'All filled, lightness split: spade L*34, heart L*46, club L*44, diamond L*50',
    SPLIT_PALETTE,
    FILLED_FORMS,
  ),
]

# A card-style sample as (text, suit or None) runs; a suit run's glyph comes
# from the active forms map.
SAMPLE_RUNS = [
  ('4', None),
  ('', 'spades'),
  (': RKC 1430; 2', None),
  ('', 'hearts'),
  (' Flannery; 3', None),
  ('', 'diamonds'),
  ('=mixed; 5', None),
  ('', 'clubs'),
  (' Exclusion KB', None),
]

PAGE_WIDTH, PAGE_HEIGHT = 612, 792
LEFT = 40

registerFont(TTFont('Entry', str(DEFAULT_TEXT_FONT_PATH)))
registerFont(TTFont('Symbols', SYMBOL_FONT))
canvas = Canvas(str(OUT_PATH), pagesize=(PAGE_WIDTH, PAGE_HEIGHT))

canvas.setFont('Helvetica-Bold', 13)
canvas.drawString(LEFT, PAGE_HEIGHT - 46, 'Suit-tone specimen for B/W printing')
canvas.setFont('Helvetica', 8)
canvas.setFillGray(0.35)
canvas.drawString(
  LEFT,
  PAGE_HEIGHT - 60,
  'Each pair: the colored line, then the gray a B/W printer makes of it.',
)


def draw_suit_glyph(
  x: float, y: float, glyph: str, size: float, color: int, stroke_ratio: float
) -> None:
  """Draw one suit glyph, optionally boosting its outline with a stroke."""
  canvas.setFillColor(HexColor(color))
  if not stroke_ratio:
    canvas.setFont('Symbols', size)
    canvas.drawString(x, y, glyph)
    return

  canvas.setStrokeColor(HexColor(color))
  canvas.setLineWidth(stroke_ratio * size)
  canvas.setLineJoin(1)
  text = canvas.beginText(x, y)
  text.setFont('Symbols', size)
  text.setTextRenderMode(2)
  text.textOut(glyph)
  # Reset inside the text object: reportlab elides a set-to-default on a fresh
  # object, so the stroke mode would otherwise leak into later text.
  text.setTextRenderMode(0)
  canvas.drawText(text)


def draw_sample(
  y: float,
  size: float,
  palette: dict[str, int],
  forms: SuitForms,
  as_gray: bool,
) -> None:
  """One sample line at `y`, colored or as its grayscale-print simulation."""
  # A cursor, not a page constant: each run advances it by a measured string
  # width, which is fractional.
  x: float = LEFT + 24
  for text, suit in SAMPLE_RUNS:
    if suit is None:
      canvas.setFont('Entry', size)
      canvas.setFillColor(HexColor(0x000000))
      canvas.drawString(x, y, text)
      x += stringWidth(text, 'Entry', size)
    else:
      symbol_size = size * SYMBOL_SIZE_FACTOR
      glyph, stroke_ratio = forms[suit]
      color = palette[suit]
      shown = gray_of(color) if as_gray else color
      draw_suit_glyph(x, y, glyph, symbol_size, shown, stroke_ratio)
      x += stringWidth(glyph, 'Symbols', symbol_size)


def draw_block(
  y: float, label: str, palette: dict[str, int], forms: SuitForms
) -> float:
  """One labeled block: swatch rows, then sample lines; returns the next y."""
  canvas.setFillGray(0.0)
  canvas.setFont('Helvetica-Bold', 9)
  canvas.drawString(LEFT, y, label)
  y -= 15

  # Large swatches: each suit at 14pt, color row then gray row.
  for as_gray in (False, True):
    x = LEFT + 24
    for suit in ('spades', 'hearts', 'diamonds', 'clubs'):
      glyph, stroke_ratio = forms[suit]
      color = palette[suit]
      shown = gray_of(color) if as_gray else color
      draw_suit_glyph(x, y, glyph, 14 * SYMBOL_SIZE_FACTOR, shown, stroke_ratio)
      x += 24
    y -= 17

  for size in (8.0, 6.0):
    draw_sample(y, size, palette, forms, as_gray=False)
    y -= size + 4
    draw_sample(y, size, palette, forms, as_gray=True)
    y -= size + 7

  return y - 16


# Annotated here, at the first of the three page setups: `draw_block` returns a
# fractional y, so the cursor is a float even though the page height is whole.
y: float = PAGE_HEIGHT - 92
for label, palette in CANDIDATES:
  y = draw_block(y, label, palette, FILLED_FORMS)
canvas.showPage()

canvas.setFont('Helvetica-Bold', 13)
canvas.drawString(
  LEFT, PAGE_HEIGHT - 46, 'Page 2: chosen open forms across palettes'
)
canvas.setFont('Helvetica', 8)
canvas.setFillGray(0.35)
canvas.drawString(
  LEFT,
  PAGE_HEIGHT - 60,
  'Heart outline +8%, diamond +9%; each block pairs the chosen forms with one'
  ' palette candidate.',
)
y = PAGE_HEIGHT - 92
for label, palette, forms in SHAPE_BLOCKS:
  y = draw_block(y, label, palette, forms)
canvas.showPage()

canvas.setFont('Helvetica-Bold', 13)
canvas.drawString(
  LEFT, PAGE_HEIGHT - 46, 'Page 3: spade/heart lightness split, all filled'
)
canvas.setFont('Helvetica', 8)
canvas.setFillGray(0.35)
canvas.drawString(
  LEFT,
  PAGE_HEIGHT - 60,
  'The alternative discrimination mechanism: tone instead of shape.',
)
y = PAGE_HEIGHT - 92
for label, palette, forms in ALTERNATIVE_BLOCKS:
  y = draw_block(y, label, palette, forms)
canvas.showPage()

canvas.save()
print(f'Written: {OUT_PATH}\n')

print(f'{"palette":52} {"suit":9} {"hex":>8} {"L*":>5}')
table_rows = [*CANDIDATES, ('Lightness split (page 3)', SPLIT_PALETTE)]
for label, palette in table_rows:
  for suit, color in palette.items():
    print(f'{label:52} {suit:9} #{color:06X} {lightness(color):5.1f}')
