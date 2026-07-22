# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Turn a dewarped scan into per-row crop geometry: `SheetGeometry`.

In a dewarped frame (see `sheet_dewarp`) the printed rules are nearly
horizontal, but gentle page curl still leaves a rule drifting a fraction of a
row pitch across the sheet's width — enough to smear it out of a single
full-width profile. So the rules are read per column slice (`rule_grid`), and
each rule's position is the median of the slices' readings; the strip padding
downstream absorbs the residual drift the median glosses over.

The resulting `SheetGeometry` holds tight rule-to-rule boxes in dewarped-image
coordinates; handwriting routinely bleeds past the printed rules, so each
consumer pads the tight boxes at cut time. Extraction cuts its strips from the
geometry and the review UI crops from it, so the geometry persists alongside the
processed session — with the source quad from `sheet_dewarp`, keeping the frame
reproducible from the archived scan — rather than being recomputed per consumer.
"""

import itertools
import statistics
from collections.abc import Sequence
from typing import Annotated

import pydantic
from PIL import Image

from session_analysis.frozen_model import FrozenModel
from session_analysis.rule_grid import (
  SheetGeometryError,
  dip_centers,
  pixel_column_profile,
  resolve_grid_consensus,
)

# How far the footer region extends below the grid's bottom rule, in row
# pitches. The footer is one handwritten line (event, date, pair number) just
# below the grid; 2.5 pitches covers it with margin. Public because the dewarp's
# bottom margin must leave at least this much of the photo in frame.
FOOTER_HEIGHT_IN_ROW_PITCHES = 2.5

# Rows that aren't the grid's can chain in at nearly the grid's pitch — the
# scale charts printed above it, the footer's guide underlines below — but their
# lines carry ink across only part of the sheet's width, where every true grid
# rule spans it fully. An edge rule is kept only if its ink coverage reaches
# this fraction of the median rule's. Measured: the current form's chart rules
# cover about half of what its grid rules do, and the reference scan's grid
# rules all sit within 2% of one another.
_MINIMUM_COVERAGE_FRACTION = 0.8

# The coverage band extends this many row pitches above and below a rule's
# median position, absorbing the page curl that drifts the rule around it.
_COVERAGE_BAND_IN_PITCHES = 0.2

# Ink, for coverage purposes: at least this many luminance levels below the
# band's median (the paper level).
_COVERAGE_INK_CONTRAST = 60

# The most rows the coverage trim may remove in total: the charts and ghost
# underlines are each a few rows at most, so a larger removal means the grid was
# misread. Public because `extraction`'s dewarp-vs-detection cross-check must
# allow detection to run short by exactly this budget.
MAXIMUM_TRIMMED_ROWS = 6


class Box(FrozenModel):
  """An axis-aligned pixel rectangle, in PIL crop order.

  `left`/`top` are inclusive, `right`/`bottom` exclusive, so a `Box` passes
  straight to `Image.crop`.
  """

  left: int
  top: int
  right: int
  bottom: int


class SheetGeometry(FrozenModel):
  """One scan's detected grid: tight per-row boxes, in dewarped-image space.

  Row boxes run rule-to-rule with no padding — consumers pad at cut time, each
  to its own needs (see the module docstring). The footer region is derived from
  the grid (`footer_box`) rather than stored.
  """

  image_width: int
  image_height: int
  row_boxes: Annotated[tuple[Box, ...], pydantic.Field(min_length=1)]

  def row_pitch(self) -> float:
    """The median tight row height — the padding unit for consumers."""
    return statistics.median(box.bottom - box.top for box in self.row_boxes)

  def footer_box(self) -> Box:
    """The footer region: one handwritten line just below the grid.

    Spans the grid's width, from the bottom rule down
    `FOOTER_HEIGHT_IN_ROW_PITCHES` pitches, clamped to the image — sized with
    margin already, so consumers cut it unpadded.
    """
    bottom_row = self.row_boxes[-1]
    footer_height = round(FOOTER_HEIGHT_IN_ROW_PITCHES * self.row_pitch())
    return Box(
      left=bottom_row.left,
      top=bottom_row.bottom,
      right=bottom_row.right,
      bottom=min(self.image_height, bottom_row.bottom + footer_height),
    )


def detect_sheet_geometry(image: Image.Image) -> SheetGeometry:
  """Detect a dewarped scan's printed row grid.

  The row count comes from the scan itself — the column slices' consensus —
  so any form with a plausible row count (eight or more rows — see
  `rule_grid`) resolves without configuration; the count surfaces as
  `len(row_boxes)`. Chained rows that aren't board rows are handled two ways:
  partial-width lines at the ends (scale charts above the grid, footer guide
  underlines below it) are trimmed by ink coverage, while a printed header
  row at board pitch is full-width and stays — the transcription prompt
  treats its strip as a blank row. (A header row taller than a board row,
  like the reference scan's, never chains in the first place.)

  Raises:
    SheetGeometryError: the column slices couldn't agree on a grid, or the
      coverage trim removed implausibly many rows.
  """
  gray = image.convert('L')
  consensus = resolve_grid_consensus(gray)
  rules = _trim_to_grid_rules(
    gray,
    [
      round(
        statistics.median(chain.rule_ys[index] for chain in consensus.chains)
      )
      for index in range(consensus.row_count + 1)
    ],
  )

  # The grid's horizontal extent: within the band between the top and bottom
  # rules, the outermost dark column lines are the table's vertical border
  # rules.
  grid_band = gray.crop((0, rules[0], gray.width, rules[-1]))
  column_centers = dip_centers(pixel_column_profile(grid_band))
  if len(column_centers) < 2:
    raise SheetGeometryError(
      f'no vertical border rules found in the grid band '
      f'(pixel rows {rules[0]}..{rules[-1]})'
    )
  grid_left, grid_right = column_centers[0], column_centers[-1]

  row_boxes = tuple(
    Box(left=grid_left, top=top, right=grid_right, bottom=bottom)
    for top, bottom in itertools.pairwise(rules)
  )
  return SheetGeometry(
    image_width=gray.width, image_height=gray.height, row_boxes=row_boxes
  )


def _trim_to_grid_rules(
  gray: Image.Image, rules: Sequence[int]
) -> Sequence[int]:
  """Drop leading and trailing rules whose lines carry too little ink.

  The consensus can chain rows that sit at nearly the grid's pitch without
  being board rows: scale charts printed above the grid and the footer's
  guide underlines below it. Their lines are partial-width, so their coverage
  falls under `_MINIMUM_COVERAGE_FRACTION` of the median rule's and they are
  trimmed from the ends; interior rules are never touched. A printed header
  row at board pitch survives deliberately — its rules are full-width — and
  the transcription prompt handles its strip instead.

  Raises:
    SheetGeometryError: the trim would remove more than
      `MAXIMUM_TRIMMED_ROWS` rules, meaning the grid itself was misread.
  """
  pitch = statistics.median(
    bottom - top for top, bottom in itertools.pairwise(rules)
  )
  band_half_height = max(2, round(_COVERAGE_BAND_IN_PITCHES * pitch))
  coverages = [_rule_coverage(gray, y, band_half_height) for y in rules]
  cutoff = _MINIMUM_COVERAGE_FRACTION * statistics.median(coverages)

  start, end = 0, len(rules)
  while start < end - 1 and coverages[start] < cutoff:
    start += 1
  while end - 1 > start and coverages[end - 1] < cutoff:
    end -= 1

  trimmed = start + (len(rules) - end)
  if trimmed > MAXIMUM_TRIMMED_ROWS:
    raise SheetGeometryError(
      f'coverage trim would remove {trimmed} rules, more than the plausible '
      f'{MAXIMUM_TRIMMED_ROWS}; rule coverages: '
      f'{[round(coverage, 2) for coverage in coverages]}'
    )
  return rules[start:end]


def _rule_coverage(
  gray: Image.Image, rule_y: int, band_half_height: int
) -> float:
  """The fraction of pixel columns with ink near a rule line.

  A column counts when any pixel in the band around the rule's median position
  is ink, meaning well below the band's own paper level; the band absorbs the
  curl drift that moves a rule around its median.
  """
  band = gray.crop(
    (
      0,
      max(0, rule_y - band_half_height),
      gray.width,
      rule_y + band_half_height + 1,
    )
  )
  ink_cutoff = statistics.median(band.tobytes()) - _COVERAGE_INK_CONTRAST
  is_ink = band.point(lambda value: 255 if value < ink_cutoff else 0)
  # BOX-averaging the binary band down to one pixel row leaves a column nonzero
  # exactly when any of its band pixels was ink.
  column_ink = is_ink.resize((band.width, 1), Image.Resampling.BOX)
  ink_columns = band.width - column_ink.histogram()[0]
  return ink_columns / band.width
