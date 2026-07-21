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
  """A synthetic scan: horizontal rules at `rule_ys` between vertical borders.
  """
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
  assert geometry.footer_box() == Box(left=40, top=660, right=560, bottom=710)


def test_footer_box_clamps_to_the_image_bottom() -> None:
  geometry = detect_sheet_geometry(_draw_sheet(_STANDARD_RULE_YS, height=700))

  assert geometry.footer_box().bottom == 700


def test_row_count_is_inferred_from_the_grid() -> None:
  twenty_one_rules = _STANDARD_RULE_YS[:21]

  geometry = detect_sheet_geometry(_draw_sheet(twenty_one_rules))

  assert len(geometry.row_boxes) == 20


def test_a_full_width_rule_at_the_grid_pitch_extends_the_grid() -> None:
  # A full-width rule one pitch above the grid is indistinguishable from a 29th
  # row, so it becomes one — the row count is read from the scan.
  rule_ys = [80, *_STANDARD_RULE_YS]

  geometry = detect_sheet_geometry(_draw_sheet(rule_ys))

  assert len(geometry.row_boxes) == 29
  assert geometry.row_boxes[0] == Box(left=40, top=80, right=560, bottom=100)


def test_a_partial_width_ghost_rule_is_outvoted() -> None:
  # Footer handwriting can mimic one extra rule below the grid in a few column
  # slices; the other slices' row count wins and the ghost is ignored.
  image = _draw_sheet(_STANDARD_RULE_YS)
  ImageDraw.Draw(image).line([(40, 680), (140, 680)], fill=0)

  geometry = detect_sheet_geometry(image)

  assert len(geometry.row_boxes) == 28
  assert geometry.row_boxes[-1].bottom == 660


def test_an_even_split_on_row_count_raises() -> None:
  # A ghost rule spanning exactly half the slices leaves no majority to trust.
  image = _draw_sheet(_STANDARD_RULE_YS)
  ImageDraw.Draw(image).line([(300, 680), (560, 680)], fill=0)

  with pytest.raises(SheetGeometryError, match='ambiguous row count'):
    detect_sheet_geometry(image)


def test_a_short_run_of_lines_is_not_a_grid() -> None:
  five_rules = _STANDARD_RULE_YS[:5]

  with pytest.raises(SheetGeometryError, match='plausible grid'):
    detect_sheet_geometry(_draw_sheet(five_rules))


def test_a_grid_spanning_too_few_slices_raises() -> None:
  # A grid confined to the sheet's left quarter resolves in only ~3 of the 12
  # column slices — a consensus, but without enough independent slices to trust
  # it.
  image = Image.new('L', (600, 800), color=255)
  draw = ImageDraw.Draw(image)
  for rule_y in _STANDARD_RULE_YS:
    draw.line([(40, rule_y), (140, rule_y)], fill=0)
  for border_x in (40, 140):
    draw.line([(border_x, 100), (border_x, 660)], fill=0)

  with pytest.raises(SheetGeometryError, match='only 3 of 12'):
    detect_sheet_geometry(image)


def test_dark_lines_off_the_grid_pitch_are_ignored() -> None:
  # A title underline far above the grid doesn't extend the uniform run.
  rule_ys = [30, *_STANDARD_RULE_YS]

  geometry = detect_sheet_geometry(_draw_sheet(rule_ys))

  assert len(geometry.row_boxes) == 28
  assert geometry.row_boxes[0].top == 100


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
  )

  assert geometry.row_pitch() == 20
