# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for sheet_dewarp."""

import statistics
from collections.abc import Sequence

import pytest
from PIL import Image, ImageDraw

from session_analysis.sheet_dewarp import dewarp_sheet
from session_analysis.testing.synthetic_scans import draw_sheet
from session_analysis.unreviewed.rule_grid import (
  SheetGeometryError,
  resolve_grid_consensus,
)
from session_analysis.unreviewed.sheet_geometry import (
  BoardPanel,
  Box,
  resolve_sheet_geometry,
)


def _draw_skewed_sheet(rule_ys: Sequence[int]) -> Image.Image:
  """A synthetic perspective-skewed scan, mimicking the reference scan.

  Rules sit at `rule_ys` down the sheet's left edge and slant down to the right
  — 40px at the grid's top, fading to flat at its bottom. Drawn between x=40 and
  x=560 on a 600x800 page.
  """
  image = Image.new('L', (600, 800), color=255)
  draw = ImageDraw.Draw(image)
  row_count = len(rule_ys) - 1
  for rule_index, left_y in enumerate(rule_ys):
    slant = round(40 * (row_count - rule_index) / row_count)
    draw.line([(40, left_y), (560, left_y + slant)], fill=0, width=2)
  draw.line([(40, rule_ys[0]), (40, rule_ys[-1])], fill=0, width=2)
  draw.line([(560, rule_ys[0] + 40), (560, rule_ys[-1])], fill=0, width=2)
  return image


def _panel_spanning(
  image: Image.Image, row_count: int, *, top: int, bottom: int
) -> BoardPanel:
  """A reading reporting one panel the full frame wide, as the model returns one
  for a sheet that carries nothing but its own board rows.
  """
  return BoardPanel(
    board_row_count=row_count,
    grid=Box(left=0, top=top, right=image.width, bottom=bottom),
  )


def test_dewarp_straightens_a_perspective_skewed_scan() -> None:
  # 29 rules at a 20px pitch bounding 28 board rows, running y=100 to y=660 at
  # the left edge and two pitches lower at the right.
  skewed = _draw_skewed_sheet(range(100, 661, 20))

  # As drawn, each column slice resolves its 29 rules a different distance down
  # the page, so no run of rules is the reported rows and the geometry is
  # refused. Straightening the frame is what makes the same panel resolvable,
  # and is the whole of what this asserts: the row box count is no evidence,
  # since `resolve_sheet_geometry` returns one box per row asked for or raises.
  with pytest.raises(SheetGeometryError, match='not reading the same rows'):
    resolve_sheet_geometry(
      skewed, [_panel_spanning(skewed, 28, top=100, bottom=660)]
    )

  dewarped = dewarp_sheet(skewed).image

  # Where the straightened grid sits, standing in for a reading of it — the
  # drawn sheet carries nothing but its own rules, so the slice consensus is the
  # grid, and the dewarp's margins have moved it off y=100..660.
  chains = resolve_grid_consensus(dewarped.convert('L')).chains
  geometry = resolve_sheet_geometry(
    dewarped,
    [
      _panel_spanning(
        dewarped,
        28,
        top=round(statistics.median(chain.rule_ys[0] for chain in chains)),
        bottom=round(statistics.median(chain.rule_ys[-1] for chain in chains)),
      )
    ],
  )

  # Rule-to-rule heights within a few pixels of each other on a ~19px pitch: the
  # straightened rules run parallel, where the drawn ones fan apart.
  heights = [box.bottom - box.top for box in geometry.row_boxes]
  assert max(heights) - min(heights) <= 3


def test_dewarp_recovers_the_slanted_corner_quad() -> None:
  quad = dewarp_sheet(_draw_skewed_sheet(range(100, 661, 20))).source_quad

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
  cropped = draw_sheet(height=700)

  dewarped = dewarp_sheet(cropped).image

  bottom_center = (dewarped.width // 2, dewarped.height - 1)
  fill_value = dewarped.getpixel(bottom_center)
  assert isinstance(fill_value, int)
  assert fill_value > 240
