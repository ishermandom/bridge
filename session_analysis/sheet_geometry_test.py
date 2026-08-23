# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for sheet_geometry.

Consensus behaviors (row-count voting, ghost rules, error cases) are
`rule_grid`'s and are tested there; these tests cover what detection adds on
top: boxes, extent, and the footer.
"""

import pytest
from PIL import Image, ImageDraw

from session_analysis.rule_grid import SheetGeometryError
from session_analysis.sheet_geometry import (
  Box,
  SheetGeometry,
  detect_sheet_geometry,
)
from session_analysis.testing.synthetic_scans import (
  GRID_LEFT,
  GRID_RIGHT,
  draw_sheet,
)

# 29 rules bounding 28 board rows at a 20px pitch, on a 600x800-pixel page.
_STANDARD_RULE_YS = list(range(100, 661, 20))


def test_detects_tight_rule_to_rule_row_boxes() -> None:
  geometry = detect_sheet_geometry(draw_sheet(_STANDARD_RULE_YS))

  assert len(geometry.row_boxes) == 28
  assert geometry.row_boxes[0] == Box(left=40, top=100, right=560, bottom=120)
  assert geometry.row_boxes[-1] == Box(left=40, top=640, right=560, bottom=660)
  assert geometry.image_width == 600
  assert geometry.image_height == 800


def test_partial_width_chart_rows_above_the_grid_are_trimmed() -> None:
  # Chart-like rules spanning most (but not all) slices chain into the consensus
  # at the grid's pitch; their partial-width lines fail the ink coverage cut and
  # the rows are trimmed from the top.
  image = draw_sheet(_STANDARD_RULE_YS)
  draw = ImageDraw.Draw(image)
  for chart_y in (60, 80):
    draw.line([(40, chart_y), (360, chart_y)], fill=0)

  geometry = detect_sheet_geometry(image)

  assert len(geometry.row_boxes) == 28
  assert geometry.row_boxes[0].top == 100


def test_a_wide_footer_underline_is_trimmed() -> None:
  # A guide underline one pitch below the grid, wide enough to win the vote, is
  # still narrower than the grid's rules and gets trimmed from the bottom.
  image = draw_sheet(_STANDARD_RULE_YS)
  ImageDraw.Draw(image).line([(40, 680), (360, 680)], fill=0)

  geometry = detect_sheet_geometry(image)

  assert len(geometry.row_boxes) == 28
  assert geometry.row_boxes[-1].bottom == 660


def test_a_grid_without_vertical_border_rules_raises() -> None:
  # Horizontal rules alone resolve a consensus, but the grid's horizontal extent
  # comes from the outermost vertical rules — with none drawn, there is nothing
  # to bound the row boxes.
  image = Image.new('L', (600, 800), color=255)
  draw = ImageDraw.Draw(image)
  for rule_y in _STANDARD_RULE_YS:
    draw.line([(GRID_LEFT, rule_y), (GRID_RIGHT, rule_y)], fill=0)

  with pytest.raises(SheetGeometryError, match='vertical border rules'):
    detect_sheet_geometry(image)


# --- SheetGeometry.footer_box ---


def test_footer_box_spans_below_the_bottom_rule() -> None:
  geometry = detect_sheet_geometry(draw_sheet(_STANDARD_RULE_YS))

  # 2.5 row pitches (pitch 20) below the bottom rule at y=660.
  assert geometry.footer_box() == Box(left=40, top=660, right=560, bottom=710)


def test_footer_box_clamps_to_the_image_bottom() -> None:
  geometry = detect_sheet_geometry(draw_sheet(height=700))

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
