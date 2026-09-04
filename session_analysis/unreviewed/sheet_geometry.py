# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Turn a dewarped scan into per-row crop geometry: `SheetGeometry`.

The geometry is resolved from two readings of the same sheet, each supplying
what the other cannot. `sheet_structure` says what the printed table is made of
— how many ruled rows each panel has, and roughly where each panel sits — which
is a judgement about the form. This module says where every rule actually is, to
the pixel, which is measurement: the rules are read per column slice
(`rule_grid`) because gentle page curl leaves a rule drifting a fraction of a
row pitch across the sheet's width, and each rule's position is the median of
the slices' readings.

The row count is taken as exact and the reported coordinates as approximate, so
the count fixes how many rules to look for and the coordinates only say where to
look. Every row coordinate therefore comes from a rule found in the pixels. The
footer band is the exception — nothing measures it, so it is carried as read and
only clamped to the image, because what bounds it is handwriting rather than a
printed rule.

The resulting `SheetGeometry` holds tight rule-to-rule boxes in dewarped-image
coordinates; handwriting routinely bleeds past the printed rules, so each
consumer pads the tight boxes at cut time. Extraction cuts its strips from the
geometry and the review UI crops from it, so the geometry persists alongside the
processed session — with the source quad from `sheet_dewarp`, keeping the frame
reproducible from the archived scan — rather than being recomputed per consumer.

A form that prints its boards in side-by-side panels contributes each panel's
rows in turn, left to right, which is the order its printed board numbers run
in. `row_boxes` is flat, so every consumer below sees one box per board however
the sheet was laid out.
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
  rules_bounding_rows,
)

# How far `_panel_sides` may reach from a panel's reported border to find the
# printed line that is that border, as a fraction of the panel's own width.
# Sized between the two things it has to separate: a reported border sat at most
# 0.8% of the panel's width from the printed rule across the real pages, while
# the narrowest column on those single-panel forms is about 3% of it (65px of
# 2158). Reaching further than
# a column is wide would have a border that faded below detection snap to the
# first interior rule instead of falling back to where it was reported — losing
# the printed board number the transcription prompt relies on, and quietly.
_BORDER_SNAP_FRACTION = 0.015

# The least `_panel_sides` will reach, whatever the panel's width. The drift a
# reported border carries shrinks with the panel but not in proportion: measured
# at 0.8% of a 2158px single-panel form and 1.4% of a 351px one, so a fraction
# alone leaves the narrowest panels no room. Ten pixels covers the 6px of drift
# seen on the two-panel forms, and sits under the narrowest column measured on
# either of them — 26px on Baron Barclay's 351px panels, which are the tightest
# of the four.
_MINIMUM_BORDER_REACH = 10

# How far one panel may reach into the previous one, as a fraction of its own
# width, before the reading is taken to describe the same block of rows twice.
# Generous: adjacent panels share a printed divider and are reported either side
# of it, while a duplicated panel overlaps completely.
_PANEL_OVERLAP_FRACTION = 0.25


class Box(FrozenModel):
  """An axis-aligned pixel rectangle, in PIL crop order.

  `left`/`top` are inclusive, `right`/`bottom` exclusive, so a `Box` passes
  straight to `Image.crop`.
  """

  left: int
  top: int
  right: int
  bottom: int

  def width(self) -> int:
    """How wide the rectangle is, in pixels."""
    return self.right - self.left

  @pydantic.model_validator(mode='after')
  def _edges_are_ordered(self) -> 'Box':
    """Refuse a rectangle whose edges cross.

    Checked here because a `Box` also arrives from outside — a model reading of
    a sheet parses into these — and `Image.crop` answers an inverted one with a
    bare `ValueError` that no caller is catching. Raised at parse time instead,
    where it is one sheet's failure rather than the whole run's.
    """
    if self.right < self.left or self.bottom < self.top:
      raise ValueError(
        f'box edges cross: left={self.left} right={self.right} '
        f'top={self.top} bottom={self.bottom}'
      )
    return self


class BoardPanel(FrozenModel):
  """One block of board rows: how many rows it has, and roughly where it is.

  A plain single-column form has one panel. Vendor forms print two side by side,
  sometimes with different row counts — a chart printed beneath one column
  shortens it — so each panel carries its own count and extent rather than
  sharing the sheet's.
  """

  # Ruled rows in this panel, not boards on the sheet. Taken as exact: it is
  # what decides how many rules `rules_bounding_rows` looks for.
  board_row_count: Annotated[int, pydantic.Field(gt=0)]
  # This panel's board rows only — no header row, no printed chart, no footer.
  # Approximate: it places the row count rather than measuring anything.
  grid: Box


class SheetGeometry(FrozenModel):
  """One scan's grid: tight per-row boxes, in dewarped-image space.

  Row boxes run rule-to-rule with no padding — consumers pad at cut time, each
  to its own needs (see the module docstring) — and are ordered as the sheet's
  board numbers run, across panels.
  """

  image_width: int
  image_height: int
  row_boxes: Annotated[tuple[Box, ...], pydantic.Field(min_length=1)]
  # Where the handwritten event, date and pair number sit, or None on a form
  # that prints no footer at all — several vendor forms put conversion charts
  # below the table instead. Carried rather than derived from the last row,
  # because "just below the bottom row" is the footer only on a form that has
  # one, and is a chart on a form that does not.
  footer: Box | None = None

  def row_pitch(self) -> float:
    """The median tight row height — the padding unit for consumers."""
    return statistics.median(box.bottom - box.top for box in self.row_boxes)


def resolve_sheet_geometry(
  image: Image.Image,
  panels: Sequence[BoardPanel],
  footer: Box | None = None,
) -> SheetGeometry:
  """Resolve a dewarped scan's printed rules against a reading of its layout.

  Args:
    image: the dewarped scan.
    panels: the sheet's blocks of board rows, left to right, each with its own
      exact row count and approximate extent.
    footer: where the handwritten footer sits, or None on a form without one.

  Returns:
    The geometry, its row boxes ordered panel by panel — the order the sheet's
    printed board numbers run in.

  Raises:
    SheetGeometryError: a panel's rules could not be resolved against the row
      count reported for it, so the two readings of the sheet disagree.
  """
  gray = image.convert('L')
  row_boxes: list[Box] = []
  previous: Box | None = None
  # Sorted rather than trusted: the order is what makes `row_boxes` run in the
  # sheet's board order, and only the prompt asks for it. A right-hand panel
  # reported first would have every strip labelled with the other panel's row
  # number, which the transcription prompt is told to go by.
  for reported in sorted(panels, key=lambda panel: panel.grid.left):
    # Clamped like the footer is: every coordinate here was reported rather than
    # measured, and PIL pads a crop reaching past the edge with black, which
    # each detector below reads as ink.
    panel = BoardPanel(
      board_row_count=reported.board_row_count,
      grid=_within(reported.grid, gray.width, gray.height),
    )
    if panel.grid.right <= panel.grid.left or (
      panel.grid.bottom <= panel.grid.top
    ):
      # Reported outside the frame, or as a line rather than a block. Said here
      # rather than left to the rule search, whose complaint would be about
      # column slices and row counts and would hide what actually went wrong.
      raise SheetGeometryError(
        f'the panel reported at {reported.grid} has no area inside the '
        f'{gray.width}x{gray.height} frame'
      )
    # What this guards is a reading that describes one block of rows twice:
    # both copies would resolve against the same printed rules and every board
    # would be transcribed twice — invisibly, since the strips double alongside
    # the boards and the counts still agree. Compared against the clamped box
    # and with room to spare, because panels sharing a printed divider are
    # reported a pixel or two either side of it, and refusing those would lose
    # the sheet to a rounding.
    if previous and previous.right - panel.grid.left > (
      _PANEL_OVERLAP_FRACTION * panel.grid.width()
    ):
      raise SheetGeometryError(
        f'the panel at {panel.grid} overlaps the one before it, which ended at '
        f'x={previous.right}; side-by-side panels do not'
      )
    previous = panel.grid

    rules = rules_bounding_rows(
      gray,
      row_count=panel.board_row_count,
      left=panel.grid.left,
      right=panel.grid.right,
      top=panel.grid.top,
      bottom=panel.grid.bottom,
    )
    left, right = _panel_sides(gray, panel, rules)
    row_boxes.extend(
      Box(left=left, top=top, right=right, bottom=bottom)
      for top, bottom in itertools.pairwise(rules)
    )

  return SheetGeometry(
    image_width=gray.width,
    image_height=gray.height,
    row_boxes=tuple(row_boxes),
    footer=_footer_within(footer, gray.width, gray.height),
  )


def _footer_within(footer: Box | None, width: int, height: int) -> Box | None:
  """The footer clamped to the image, or None if nothing of it is left.

  A footer reported below the page clamps to no height at all, and cutting a
  strip from it fails inside PIL's JPEG writer — an error nothing on the ingest
  path catches, which would cost every sheet of the run. A band with no area is
  no footer, so it is answered the way a form printing none is: no footer strip,
  no event or date, and a record filed unnamed and carrying `unnamed_session`.
  That is the right shape of answer but not a precise one — it does not
  distinguish a form with no footer from a reading that placed one outside the
  frame the dewarp kept.
  """
  if not footer:
    return None
  clamped = _within(footer, width, height)
  if clamped.right <= clamped.left or clamped.bottom <= clamped.top:
    return None
  return clamped


def _within(box: Box, width: int, height: int) -> Box:
  """One box clamped to an image's bounds."""
  return Box(
    left=min(max(box.left, 0), width),
    top=min(max(box.top, 0), height),
    right=min(max(box.right, 0), width),
    bottom=min(max(box.bottom, 0), height),
  )


def _panel_sides(
  gray: Image.Image, panel: BoardPanel, rules: Sequence[int]
) -> tuple[int, int]:
  """One panel's left and right border rules.

  A border is the printed vertical line within `reach` of where it was reported.
  Sized under the panel's narrowest column, `reach` rules out the interior rule
  beside the border and the punched margin outside the table. It does not always
  rule out a neighbouring panel's border: on the Bridge Buddy proportions the
  gutter and the reach are both about 8px, so both borders can be candidates,
  and the nearest of them is taken. That holds while the reported edge is the
  more accurate of the two, which the measured drift says it is — but it is a
  margin, not a guarantee, and a wider gutter is what would make it one.

  Where a border has faded below detection nothing is within reach at all, and
  the reported border stands, because approximate and whole beats precise and
  truncated — a truncated panel silently drops every column past it. A form
  printing no vertical rules is the same case with nothing detected anywhere,
  and is answered the same way rather than refused: it is strictly less
  information, not a different kind of failure.

  Raises:
    SheetGeometryError: the two borders resolve to the same pixel or cross, so
      the panel has no width to cut strips from.
  """
  # Reach is a fraction of the *panel's* width, not the page's: what it has to
  # stay under is the panel's narrowest column, and a two-panel form's columns
  # are half the page fraction a single-panel form's are. Searched outside the
  # reported span as well as inside it, since a border reported a few pixels in
  # from where it is printed is the ordinary case and cropping at the reported
  # edge would put it out of reach entirely.
  reach = max(
    _MINIMUM_BORDER_REACH, round(_BORDER_SNAP_FRACTION * panel.grid.width())
  )
  searched_from = max(0, panel.grid.left - reach)
  band = gray.crop(
    (
      searched_from,
      rules[0],
      min(gray.width, panel.grid.right + reach),
      rules[-1],
    )
  )
  detected = [
    x + searched_from for x in dip_centers(pixel_column_profile(band))
  ]

  left = _border(detected, panel.grid.left, reach, gray.width)
  right = _border(detected, panel.grid.right, reach, gray.width)
  if left >= right:
    # One detected line sat within reach of both reported borders, or the
    # reported span itself is empty. Either way there is no panel to cut.
    raise SheetGeometryError(
      f'the panel reported between x={panel.grid.left} and '
      f'x={panel.grid.right} resolved to x={left}..{right}, which has no width'
    )
  return left, right


def _border(
  detected: Sequence[int], reported: int, reach: int, width: int
) -> int:
  """The panel's border: the detected column line nearest where it was reported.

  `reach` is what separates the border from everything near it — see
  `_BORDER_SNAP_FRACTION` for how it is sized — so by the time a line is a
  candidate here it is almost always the only one. Nearest is the tiebreak for
  when it is not, and is the right one: across the six panel edges of the three
  real scan pages a reported border sat 0 to 17px from the printed rule, while
  the columns and margins it must not be confused with sit further out.

  The fallback is the reported border, clamped to the image: nothing constrains
  a reported border to lie inside one, and a box reaching past the edge would be
  padded rather than refused.
  """
  within = [x for x in detected if abs(x - reported) <= reach]
  if not within:
    return min(max(reported, 0), width)
  return min(within, key=lambda x: abs(x - reported))
