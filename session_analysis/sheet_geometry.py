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
  `len(row_boxes)`. (On the club form digitized so far, the printed header
  row is taller than a board row, so the pitch chain excludes it on its own; a form whose header
  row height falls within the pitch tolerance would count it as an extra
  row.)

  Raises:
    SheetGeometryError: the column slices couldn't agree on a grid.
  """
  gray = image.convert('L')
  consensus = resolve_grid_consensus(gray)
  rules = [
    round(statistics.median(chain.rule_ys[index] for chain in consensus.chains))
    for index in range(consensus.row_count + 1)
  ]

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
