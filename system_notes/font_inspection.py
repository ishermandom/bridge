# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Read the installed fonts: the file serving a family, and a glyph's ink.

The stylesheet tunes some of its values to the fonts: the list markers' sizes
and offsets to their outlines, and the suit skew to the body font's italic
angle. Checking those values means asking the same fonts a render would use.
fontconfig picks the font file, as it does for WeasyPrint, and fontTools reads
the outline from it.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont

# fontconfig's names for a face's slant, as a pattern like `Family:italic` asks.
type Slant = Literal['roman', 'italic']


def installed_font(family: str, slant: Slant) -> Path:
  """The font file fontconfig serves for `family` in the given slant.

  fontconfig answers every request with some font, falling back to another
  family when it has none of the one asked for. A fallback raises LookupError
  here, since measuring it would check the wrong face.
  """
  matched_font = subprocess.run(
    ['fc-match', '-f', '%{family}\t%{file}', f'{family}:{slant}'],
    capture_output=True,
    text=True,
    encoding='utf-8',
    check=True,
  ).stdout
  matched_family, _, font_file = matched_font.partition('\t')
  # A font can carry several family names; fc-match then reports them
  # comma-joined.
  if family not in matched_family.split(','):
    raise LookupError(
      f'no installed {slant} face for {family}: fontconfig offered '
      f'{matched_family!r}'
    )
  return Path(font_file)


@dataclass(frozen=True)
class InkBounds:
  """The extent of a glyph's ink, in em.

  `left` and `right` are measured rightward from the glyph's origin, and
  `bottom` and `top` upward from the baseline.
  """

  left: float
  right: float
  bottom: float
  top: float

  @property
  def width(self) -> float:
    """How far the ink spans across."""
    return self.right - self.left

  @property
  def height(self) -> float:
    """How far the ink spans up."""
    return self.top - self.bottom

  @property
  def center_height(self) -> float:
    """The height of the ink's vertical midpoint above the baseline."""
    return (self.bottom + self.top) / 2


def ink_bounds(face: TTFont, character: str) -> InkBounds:
  """Where `face` draws its glyph for `character`, in em.

  The bounds come from the glyph's outline as fontTools' BoundsPen traces it, so
  they hug the curves themselves rather than the control points that shape them.
  """
  glyph_name = face.getBestCmap().get(ord(character))
  if not glyph_name:
    raise LookupError(f'the font has no glyph for {character!r}')
  glyph_set = face.getGlyphSet()
  pen = BoundsPen(glyph_set)
  glyph_set[glyph_name].draw(pen)
  if not pen.bounds:
    raise ValueError(f'the glyph for {character!r} draws no ink')

  units_per_em = face['head'].unitsPerEm
  left, bottom, right, top = pen.bounds
  return InkBounds(
    left=left / units_per_em,
    right=right / units_per_em,
    bottom=bottom / units_per_em,
    top=top / units_per_em,
  )
