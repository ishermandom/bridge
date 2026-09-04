# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

"""Font registration and measurement for entry text.

Entry text renders in a swappable text font, supplied as a font file path and
never committed to the repo. Suit symbols always come from Apple Symbols
instead, which reliably covers ♠♥♦♣ where text faces often don't.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from renderer.markup import Suit, TextRun
from renderer.private_paths import discover_private_assets

# The pinned entry face: Google Sans Flex at 6pt optical size, SuperCondensed
# width, Regular weight graded up to Medium's stroke (GRAD 100). The cut lives
# in the bridge-private sibling repo, whose `fonts/README.md` records its
# provenance and measurements.
DEFAULT_TEXT_FONT_PATH = (
  discover_private_assets().fonts_directory
  / 'GoogleSansFlex-opsz6-SuperCondensed-Grad100.ttf'
)

# Which face within the font file to render: reportlab's "subfont" index. The
# pinned cut is a plain .ttf holding a single face, so the index is 0.
DEFAULT_TEXT_FONT_SUBFONT = 0

_SYMBOL_FONT_PATH = Path('/System/Library/Fonts/Apple Symbols.ttf')

# Suit glyphs drawn at the text's own point size look x-height-sized rather than
# cap-height tall: Apple Symbols draws the suits ~0.559 em tall, while the
# default entry face's cap height is 0.716 em. Suit runs are enlarged by this
# ratio so the symbols stand cap-height tall beside the text. Both numbers come
# from the pinned fonts' metrics; re-derive with `palette_specimen.py` if either
# font changes.
SUIT_SIZE_FACTOR = 0.716 / 0.559

# reportlab registry names; arbitrary, but stable across a process.
_TEXT_FONT_NAME = 'EntryText'
_SYMBOL_FONT_NAME = 'EntrySymbols'


@dataclass(frozen=True)
class EntryFonts:
  """The registered font pair entries render with."""

  text_font: str
  symbol_font: str

  # Every suit run occupies this shared advance (in points per point of text
  # size): the widest suit glyph's enlarged advance. Equal advances keep text
  # after a symbol aligned across suits — e.g. the stacked `2!d`/`2!h`/`2!s`
  # response rows.
  suit_unit_advance: float

  # Per-suit horizontal stretch filling the shared advance: narrower glyphs (the
  # spade and diamond run ~14% narrower than the heart) widen so their ink
  # matches the slot, rather than floating in extra side space.
  suit_stretches: Mapping[Suit, float]

  def font_for(self, run: TextRun) -> str:
    """Pick the registered font name a run renders in."""
    return self.symbol_font if run.suit else self.text_font

  def run_width(self, run: TextRun, font_size: float) -> float:
    """Measure a run's width in points at the given size.

    Suit runs all report the shared `suit_unit_advance`, so fitting sees the
    slot the overlay will actually reserve.
    """
    if run.suit:
      return self.suit_unit_advance * font_size
    return float(pdfmetrics.stringWidth(run.text, self.text_font, font_size))


def register_entry_fonts(
  text_font_path: Path = DEFAULT_TEXT_FONT_PATH,
  subfont_index: int = DEFAULT_TEXT_FONT_SUBFONT,
) -> EntryFonts:
  """Register the text and suit-symbol fonts with reportlab.

  `subfont_index` selects a face within a TrueType collection (.ttc); plain
  .ttf/.otf files use index 0.
  """
  for path in (text_font_path, _SYMBOL_FONT_PATH):
    if not path.exists():
      raise FileNotFoundError(f'font file not found: {path}')

  pdfmetrics.registerFont(
    TTFont(_TEXT_FONT_NAME, str(text_font_path), subfontIndex=subfont_index)
  )
  pdfmetrics.registerFont(TTFont(_SYMBOL_FONT_NAME, str(_SYMBOL_FONT_PATH)))

  # Measuring at font size = SUIT_SIZE_FACTOR yields each glyph's enlarged
  # advance per point of text size.
  natural_advances = {
    suit: float(
      pdfmetrics.stringWidth(suit.value, _SYMBOL_FONT_NAME, SUIT_SIZE_FACTOR)
    )
    for suit in Suit
  }
  suit_unit_advance = max(natural_advances.values())
  return EntryFonts(
    text_font=_TEXT_FONT_NAME,
    symbol_font=_SYMBOL_FONT_NAME,
    suit_unit_advance=suit_unit_advance,
    suit_stretches={
      suit: suit_unit_advance / advance
      for suit, advance in natural_advances.items()
    },
  )
