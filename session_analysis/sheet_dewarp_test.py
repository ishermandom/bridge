# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for sheet_dewarp.

Scans are synthesized with PIL — a white page with drawn grid rules — rather
than committed as image fixtures: real scans carry member handwriting, and a
drawn grid pins the expected geometry exactly.
"""

from collections.abc import Sequence

import pytest
from PIL import Image, ImageDraw

from session_analysis.rule_grid import SheetGeometryError
from session_analysis.sheet_dewarp import dewarp_sheet
from session_analysis.sheet_geometry import detect_sheet_geometry

_GRID_LEFT = 40
_GRID_RIGHT = 560

# 29 rules bounding 28 rows, pitch 20, on a 600x800 page.
_STANDARD_RULE_YS = list(range(100, 661, 20))


def _draw_sheet(
  rule_ys: Sequence[int],
  *,
  width: int = 600,
  height: int = 800,
) -> Image.Image:
  """A synthetic scan: horizontal rules at `rule_ys` between vertical borders.
  """
  image = Image.new('L', (width, height), color=255)
  draw = ImageDraw.Draw(image)
  for rule_y in rule_ys:
    draw.line([(_GRID_LEFT, rule_y), (_GRID_RIGHT, rule_y)], fill=0)
  for border_x in (_GRID_LEFT, _GRID_RIGHT):
    draw.line([(border_x, rule_ys[0]), (border_x, rule_ys[-1])], fill=0)
  return image


def _draw_skewed_sheet() -> Image.Image:
  """A synthetic perspective-skewed scan, mimicking the live sample: each rule
  slants down to the right, two row pitches at the grid's top fading to flat at
  its bottom.
  """
  image = Image.new('L', (600, 800), color=255)
  draw = ImageDraw.Draw(image)
  left_rule_ys = list(range(100, 661, 20))
  for rule_index, left_y in enumerate(left_rule_ys):
    slant = round(40 * (28 - rule_index) / 28)
    draw.line(
      [(_GRID_LEFT, left_y), (_GRID_RIGHT, left_y + slant)], fill=0, width=2
    )
  draw.line([(_GRID_LEFT, 100), (_GRID_LEFT, 660)], fill=0, width=2)
  draw.line([(_GRID_RIGHT, 140), (_GRID_RIGHT, 660)], fill=0, width=2)
  return image


def test_dewarp_straightens_a_perspective_skewed_scan() -> None:
  # The skewed grid is undetectable as drawn — rules drift two row pitches — but
  # detection succeeds in the dewarped frame.
  dewarped = dewarp_sheet(_draw_skewed_sheet())

  geometry = detect_sheet_geometry(dewarped.image)

  assert len(geometry.row_boxes) == 28


def test_dewarp_recovers_the_slanted_corner_quad() -> None:
  quad = dewarp_sheet(_draw_skewed_sheet()).source_quad

  # The top edge slants 40px down to the right; the bottom edge is flat. The
  # dewarp margins shift both corners of an edge alike, so the recovered slant
  # survives in the corner deltas (loose bounds: line fits interpolate the drawn
  # staircase).
  assert 30 < quad.top_right.y - quad.top_left.y < 50
  assert abs(quad.bottom_right.y - quad.bottom_left.y) < 8


def test_dewarp_of_a_blank_image_raises() -> None:
  blank = Image.new('L', (600, 800), color=255)

  with pytest.raises(SheetGeometryError, match='column slices'):
    dewarp_sheet(blank)


def test_missing_margin_is_filled_with_paper_white() -> None:
  # A photo cropped just below the grid lacks the footer margin the quad extends
  # into; the filler must read as blank paper, not as dark marks the detectors
  # would mistake for rules.
  cropped = _draw_sheet(_STANDARD_RULE_YS, height=700)

  dewarped = dewarp_sheet(cropped).image

  bottom_center = (dewarped.width // 2, dewarped.height - 1)
  fill_value = dewarped.getpixel(bottom_center)
  assert isinstance(fill_value, int)
  assert fill_value > 240
