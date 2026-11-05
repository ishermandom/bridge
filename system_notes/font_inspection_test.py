# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Font lookup and glyph measurement, checked against a font built in place."""

import io
from collections.abc import Mapping

import pytest
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

from system_notes import font_inspection

# A rectangle's corners in font units: left, bottom, right, top.
type Rectangle = tuple[int, int, int, int]


def _make_font(
  units_per_em: int, outlines: Mapping[str, Rectangle | None]
) -> TTFont:
  """A font drawing each character as its rectangle, or blank for None.

  The font is saved and read back, so it reaches the code under test in the same
  compiled form an installed font does.
  """
  glyph_names = {
    character: f'glyph{index}' for index, character in enumerate(outlines)
  }
  glyphs = {'.notdef': TTGlyphPen(None).glyph()}
  # Each glyph's advance and left side bearing. fontTools sets a TrueType
  # outline's left edge on the bearing, so the bearing must be the outline's own
  # left edge, as a font compiler writes it.
  metrics = {'.notdef': (units_per_em, 0)}
  for character, rectangle in outlines.items():
    pen = TTGlyphPen(None)
    left_side_bearing = 0
    if rectangle:
      left, bottom, right, top = rectangle
      pen.moveTo((left, bottom))
      pen.lineTo((left, top))
      pen.lineTo((right, top))
      pen.lineTo((right, bottom))
      pen.closePath()
      left_side_bearing = left
    glyphs[glyph_names[character]] = pen.glyph()
    metrics[glyph_names[character]] = (units_per_em, left_side_bearing)

  builder = FontBuilder(units_per_em, isTTF=True)
  builder.setupGlyphOrder(list(glyphs))
  builder.setupCharacterMap(
    {ord(character): name for character, name in glyph_names.items()}
  )
  builder.setupGlyf(glyphs)
  builder.setupHorizontalMetrics(metrics)
  builder.setupHorizontalHeader()
  builder.setupPost()
  stream = io.BytesIO()
  builder.save(stream)
  stream.seek(0)
  return TTFont(stream)


# --- ink_bounds ---


def test_ink_bounds_measure_the_outline_in_em() -> None:
  face = _make_font(2000, {'■': (100, -200, 700, 1300)})

  bounds = font_inspection.ink_bounds(face, '■')

  # Each bound is its font-unit coordinate divided by the 2000-unit em.
  assert bounds == font_inspection.InkBounds(
    left=0.05, right=0.35, bottom=-0.1, top=0.65
  )


def test_ink_bounds_derive_width_height_and_center() -> None:
  bounds = font_inspection.InkBounds(
    left=0.05, right=0.35, bottom=-0.1, top=0.65
  )

  assert (bounds.width, bounds.height, bounds.center_height) == pytest.approx(
    (0.3, 0.75, 0.275)
  )


def test_ink_bounds_reject_a_character_the_font_lacks() -> None:
  face = _make_font(2000, {'■': (100, -200, 700, 1300)})

  with pytest.raises(LookupError, match='no glyph'):
    font_inspection.ink_bounds(face, '○')


def test_ink_bounds_reject_a_glyph_without_ink() -> None:
  face = _make_font(2000, {' ': None})

  with pytest.raises(ValueError, match='no ink'):
    font_inspection.ink_bounds(face, ' ')


# --- installed_font ---


def test_installed_font_rejects_a_fallback_to_another_family() -> None:
  # fontconfig answers with some other family when it has none of this one.
  with pytest.raises(LookupError, match='fontconfig'):
    font_inspection.installed_font('No Such Family For Testing', 'roman')
