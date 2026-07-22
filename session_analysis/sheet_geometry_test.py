# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for sheet_geometry.

Scans are synthesized with PIL — a white page with drawn grid rules — rather
than committed as image fixtures: real scans carry member handwriting, and a
drawn grid pins the expected geometry exactly. Consensus behaviors (row-count
voting, ghost rules, error cases) are `rule_grid`'s and are tested there; these
tests cover what detection adds on top: boxes, extent, and the footer.
"""

from collections.abc import Sequence

import pytest
from PIL import Image, ImageDraw

from session_analysis.rule_grid import SheetGeometryError
from session_analysis.sheet_geometry import (
  Box,
  SheetGeometry,
  detect_sheet_geometry,
)

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


def test_detects_tight_rule_to_rule_row_boxes() -> None:
  geometry = detect_sheet_geometry(_draw_sheet(_STANDARD_RULE_YS))

  assert len(geometry.row_boxes) == 28
  assert geometry.row_boxes[0] == Box(left=40, top=100, right=560, bottom=120)
  assert geometry.row_boxes[-1] == Box(left=40, top=640, right=560, bottom=660)
  assert geometry.image_width == 600
  assert geometry.image_height == 800


def test_a_grid_without_vertical_border_rules_raises() -> None:
  # Horizontal rules alone resolve a consensus, but the grid's horizontal extent
  # comes from the outermost vertical rules — with none drawn, there is nothing
  # to bound the row boxes.
  image = Image.new('L', (600, 800), color=255)
  draw = ImageDraw.Draw(image)
  for rule_y in _STANDARD_RULE_YS:
    draw.line([(_GRID_LEFT, rule_y), (_GRID_RIGHT, rule_y)], fill=0)

  with pytest.raises(SheetGeometryError, match='vertical border rules'):
    detect_sheet_geometry(image)


# --- SheetGeometry.footer_box ---


def test_footer_box_spans_below_the_bottom_rule() -> None:
  geometry = detect_sheet_geometry(_draw_sheet(_STANDARD_RULE_YS))

  # 2.5 row pitches (pitch 20) below the bottom rule at y=660.
  assert geometry.footer_box() == Box(left=40, top=660, right=560, bottom=710)


def test_footer_box_clamps_to_the_image_bottom() -> None:
  geometry = detect_sheet_geometry(_draw_sheet(_STANDARD_RULE_YS, height=700))

  assert geometry.footer_box().bottom == 700


# --- SheetGeometry.row_pitch ---


def test_row_pitch_is_the_median_tight_row_height() -> None:
  geometry = SheetGeometry(
    image_width=100,
    image_height=100,
    row_boxes=(
      Box(left=0, top=0, right=100, bottom=18),
      Box(left=0, top=18, right=100, bottom=38),
      Box(left=0, top=38, right=100, bottom=61),
    ),
  )

  assert geometry.row_pitch() == 20
