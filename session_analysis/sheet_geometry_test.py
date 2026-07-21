# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for sheet_geometry.

Scans are synthesized with PIL — a white page with drawn grid rules — rather
than committed as image fixtures: real scans carry member handwriting, and a
drawn grid pins the expected geometry exactly.
"""

from collections.abc import Sequence

import pytest
from PIL import Image, ImageDraw

from session_analysis.sheet_geometry import (
  Box,
  SheetGeometry,
  SheetGeometryError,
  detect_sheet_geometry,
  dewarp_sheet,
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
  """A synthetic scan: horizontal rules at `rule_ys` between vertical borders."""
  image = Image.new('L', (width, height), color=255)
  draw = ImageDraw.Draw(image)
  for rule_y in rule_ys:
    draw.line([(_GRID_LEFT, rule_y), (_GRID_RIGHT, rule_y)], fill=0)
  for border_x in (_GRID_LEFT, _GRID_RIGHT):
    draw.line([(border_x, rule_ys[0]), (border_x, rule_ys[-1])], fill=0)
  return image


# --- grid detection ---


def test_detects_tight_rule_to_rule_row_boxes() -> None:
  geometry = detect_sheet_geometry(_draw_sheet(_STANDARD_RULE_YS))

  assert len(geometry.row_boxes) == 28
  assert geometry.row_boxes[0] == Box(left=40, top=100, right=560, bottom=120)
  assert geometry.row_boxes[-1] == Box(left=40, top=640, right=560, bottom=660)
  assert geometry.image_width == 600
  assert geometry.image_height == 800


def test_footer_box_spans_below_the_bottom_rule() -> None:
  geometry = detect_sheet_geometry(_draw_sheet(_STANDARD_RULE_YS))

  # 2.5 row pitches (pitch 20) below the bottom rule at y=660.
  assert geometry.footer_box == Box(left=40, top=660, right=560, bottom=710)


def test_footer_box_clamps_to_the_image_bottom() -> None:
  geometry = detect_sheet_geometry(_draw_sheet(_STANDARD_RULE_YS, height=700))

  assert geometry.footer_box.bottom == 700


def test_an_extra_rule_at_the_grid_pitch_raises() -> None:
  # Which end an extra at-pitch rule belongs to is unknowable from the run
  # alone, so detection refuses to guess. (The form's printed header row never
  # triggers this: it is taller than a board row, so the chain excludes it.)
  rule_ys = [80, *_STANDARD_RULE_YS]

  with pytest.raises(
    SheetGeometryError, match=r'row counts per slice.*29.*expected 28'
  ):
    detect_sheet_geometry(_draw_sheet(rule_ys))


def test_dark_lines_off_the_grid_pitch_are_ignored() -> None:
  # A title underline far above the grid doesn't extend the uniform run.
  rule_ys = [30, *_STANDARD_RULE_YS]

  geometry = detect_sheet_geometry(_draw_sheet(rule_ys))

  assert len(geometry.row_boxes) == 28
  assert geometry.row_boxes[0].top == 100


def test_wrong_row_count_raises_with_both_counts() -> None:
  twenty_one_rules = _STANDARD_RULE_YS[:21]

  with pytest.raises(
    SheetGeometryError, match=r'row counts per slice.*20.*expected 28'
  ):
    detect_sheet_geometry(_draw_sheet(twenty_one_rules))


def test_blank_image_raises() -> None:
  blank = Image.new('L', (600, 800), color=255)

  with pytest.raises(SheetGeometryError, match='column slices'):
    detect_sheet_geometry(blank)


# --- dewarp_sheet ---


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
    footer_box=Box(left=0, top=61, right=100, bottom=100),
  )

  assert geometry.row_pitch() == 20
