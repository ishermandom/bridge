# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for rule_grid.

Scans are synthesized with PIL — a white page with drawn grid rules — rather
than committed as image fixtures: real scans carry member handwriting, and a
drawn grid pins the expected rule positions exactly.
"""

from collections.abc import Sequence

import pytest
from PIL import Image, ImageDraw

from session_analysis.rule_grid import (
  SheetGeometryError,
  resolve_grid_consensus,
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


def test_every_slice_resolves_the_same_rule_chain() -> None:
  consensus = resolve_grid_consensus(_draw_sheet(_STANDARD_RULE_YS))

  assert consensus.row_count == 28
  assert len(consensus.chains) == 12
  for chain in consensus.chains:
    assert chain.rule_ys[0] == 100
    assert chain.rule_ys[-1] == 660


def test_row_count_is_inferred_from_the_grid() -> None:
  twenty_one_rules = _STANDARD_RULE_YS[:21]

  consensus = resolve_grid_consensus(_draw_sheet(twenty_one_rules))

  assert consensus.row_count == 20


def test_a_full_width_rule_at_the_grid_pitch_extends_the_grid() -> None:
  # A full-width rule one pitch above the grid is indistinguishable from a 29th
  # row, so it becomes one — the row count is read from the scan.
  rule_ys = [80, *_STANDARD_RULE_YS]

  consensus = resolve_grid_consensus(_draw_sheet(rule_ys))

  assert consensus.row_count == 29
  assert all(chain.rule_ys[0] == 80 for chain in consensus.chains)


def test_a_partial_width_ghost_rule_is_outvoted() -> None:
  # Footer handwriting can mimic one extra rule below the grid in a few column
  # slices; the other slices' row count wins and the ghost chains are dropped.
  image = _draw_sheet(_STANDARD_RULE_YS)
  ImageDraw.Draw(image).line([(40, 680), (140, 680)], fill=0)

  consensus = resolve_grid_consensus(image)

  assert consensus.row_count == 28
  assert all(chain.rule_ys[-1] == 660 for chain in consensus.chains)


def test_an_even_split_on_row_count_raises() -> None:
  # A ghost rule spanning exactly half the slices leaves no majority to trust.
  image = _draw_sheet(_STANDARD_RULE_YS)
  ImageDraw.Draw(image).line([(300, 680), (560, 680)], fill=0)

  with pytest.raises(SheetGeometryError, match='ambiguous row count'):
    resolve_grid_consensus(image)


def test_a_short_run_of_lines_is_not_a_grid() -> None:
  five_rules = _STANDARD_RULE_YS[:5]

  with pytest.raises(SheetGeometryError, match='plausible grid'):
    resolve_grid_consensus(_draw_sheet(five_rules))


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
    resolve_grid_consensus(image)


def test_dark_lines_off_the_grid_pitch_are_ignored() -> None:
  # A title underline far above the grid doesn't extend the uniform chain.
  rule_ys = [30, *_STANDARD_RULE_YS]

  consensus = resolve_grid_consensus(_draw_sheet(rule_ys))

  assert consensus.row_count == 28
  assert all(chain.rule_ys[0] == 100 for chain in consensus.chains)


def test_blank_image_raises() -> None:
  blank = Image.new('L', (600, 800), color=255)

  with pytest.raises(SheetGeometryError, match='column slices'):
    resolve_grid_consensus(blank)
