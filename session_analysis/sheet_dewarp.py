# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Flatten a scoresheet photo so its printed grid sits upright and straight.

A raw photo carries perspective and no capture-side correction is assumed: on
the reference scan (`rule_grid` describes it) the top rules slant ~112px across
the sheet's width while the bottom rule is level, which no straight horizontal
crop survives. The fix maps the grid region onto an upright rectangle:

- The per-slice rule chains from `rule_grid` give each slice's top and bottom
  rule position; straight lines fitted through those anchor the grid's top and
  bottom edges.
- The side borders are found the way rules are, rotated 90 degrees: horizontal
  bands are averaged into per-pixel-column profiles, and the outermost dips mark
  the outermost printed vertical lines.
- The four fitted lines intersect into the grid's corner quad. The quad is
  pushed outward by margins (see the margin constants) and a true perspective
  transform maps it onto a rectangle sized to the quad's own edge lengths, so
  content keeps its native resolution.

The dewarped frame deliberately contains more than the grid: content the next
stages need lives outside the printed lines — the handwritten footer below the
grid, handwriting overshooting a border — so the margins keep it in frame.
`sheet_geometry` then reads per-row boxes out of the dewarped frame.
"""

import dataclasses
import enum
import math
import statistics
from collections.abc import Sequence
from typing import NamedTuple

from PIL import Image

from session_analysis.frozen_model import FrozenModel
from session_analysis.rule_grid import (
  GridConsensus,
  SheetGeometryError,
  dip_centers,
  pixel_column_profile,
  resolve_grid_consensus,
)
from session_analysis.sheet_geometry import FOOTER_HEIGHT_IN_ROW_PITCHES

# When fitting a straight line through the slices' top (or bottom) rule
# positions, a slice whose position misses the first fit by more than this many
# row pitches is discarded and the line refit without it. The typical outlier
# sits a whole pitch off: a chain that started or ended one rule wrong (footer
# handwriting chained on as a ghost bottom rule, say).
_FIT_RESIDUAL_TOLERANCE_IN_PITCHES = 0.5

# The side borders are sampled band by band: the grid's height is cut into this
# many horizontal bands, each reporting the leftmost and rightmost dark column
# line it sees. A band can miss a border outright — on the reference scan, the
# dark background beyond the cut-off top-right sheet corner swallowed the right
# border in the top bands, which reported an interior column line instead — so
# per side, samples more than the tolerance (in row pitches) from that side's
# median are discarded before the line fit.
_BORDER_BAND_COUNT = 8
_BORDER_OUTLIER_TOLERANCE_IN_PITCHES = 2

# The margins, in row pitches, by which the corner quad is pushed outward past
# the printed grid lines before the transform. They keep content that lives
# outside the grid inside the dewarped frame: 0.5 above the top rule so the
# first row's strip padding has room; the footer height plus 0.5 below the
# bottom rule, because the handwritten footer line lives down there; and 0.5 to
# each side for handwriting overshooting a border. Larger margins would pull the
# dark table background into frame, which the dip detectors would read as marks.
_DEWARP_TOP_MARGIN_IN_PITCHES = 0.5
_DEWARP_BOTTOM_MARGIN_IN_PITCHES = FOOTER_HEIGHT_IN_ROW_PITCHES + 0.5
_DEWARP_SIDE_MARGIN_IN_PITCHES = 0.5


class Point(FrozenModel):
  """A pixel position: `x` grows rightward, `y` downward."""

  x: float
  y: float


class Quad(FrozenModel):
  """The grid's corner quad in original-scan pixels.

  Corner order matches `Image.transform`'s convention: top-left, bottom-left,
  bottom-right, top-right.
  """

  top_left: Point
  bottom_left: Point
  bottom_right: Point
  top_right: Point


@dataclasses.dataclass(frozen=True)
class DewarpedSheet:
  """A scan mapped upright: the transformed image and how it was derived.

  `row_count` is the grid size the quad fit resolved — callers cross-check it
  against what detection later finds in the dewarped frame.
  """

  image: Image.Image
  source_quad: Quad
  row_count: int


class _RuleLines(NamedTuple):
  """The grid's top and bottom rules, each fitted as a line giving y as a
  function of x.
  """

  top: statistics.LinearRegression
  bottom: statistics.LinearRegression


class _BorderLines(NamedTuple):
  """The grid's side borders, each fitted as a line giving x as a function of y
  — the sideways form, because a near-vertical line has no workable slope the
  other way around.
  """

  left: statistics.LinearRegression
  right: statistics.LinearRegression


class _SheetSide(enum.Enum):
  """Which side border a fit concerns — names the side in error messages."""

  LEFT = 'left'
  RIGHT = 'right'


def dewarp_sheet(image: Image.Image) -> DewarpedSheet:
  """Map the scan's grid region to an upright rectangle at native scale.

  The perspective is estimated from the printed grid itself — no capture-side
  correction is assumed, and the grid's row count is inferred from the scan
  rather than fixed. The output size matches the quad's own edge lengths, so
  content keeps its native resolution through the transform.

  Raises:
    SheetGeometryError: the column slices couldn't agree on a grid to fit the
      corner quad from.
  """
  gray = image.convert('L')
  consensus = resolve_grid_consensus(gray)
  rule_lines = _fit_rule_lines(consensus)

  # The rules' vertical span at mid-image gives the row pitch, which sizes the
  # dewarp margins and the border-sampling bands below.
  x_middle = gray.width / 2
  top_y = _line_value(rule_lines.top, x_middle)
  bottom_y = _line_value(rule_lines.bottom, x_middle)
  pitch = (bottom_y - top_y) / consensus.row_count

  borders = _fit_border_lines(gray, top_y, bottom_y, pitch)
  quad = _extended_quad(rule_lines, borders, pitch)

  width = _mean_edge_length(
    quad.top_left, quad.top_right, quad.bottom_left, quad.bottom_right
  )
  height = _mean_edge_length(
    quad.top_left, quad.bottom_left, quad.top_right, quad.bottom_right
  )
  # A true perspective transform, not `Image.Transform.QUAD`: QUAD interpolates
  # bilinearly, which leaves mid-grid rules visibly slanted when the distortion
  # is projective (~30px of residual measured on the reference scan); a
  # homography flattens every rule, not just the two anchoring ones. Quad
  # regions the photo didn't capture (a tightly cropped scan) are filled with
  # paper-white, not PIL's default black: every detector here hunts for dark
  # marks, and a black seam at the fill boundary would read as a rule.
  dewarped = image.transform(
    (width, height),
    Image.Transform.PERSPECTIVE,
    data=_perspective_coefficients(quad, width, height),
    resample=Image.Resampling.BICUBIC,
    fillcolor='white',
  )
  return DewarpedSheet(
    image=dewarped, source_quad=quad, row_count=consensus.row_count
  )


def _fit_rule_lines(consensus: GridConsensus) -> _RuleLines:
  """Fit the grid's top and bottom edges as straight lines.

  Each agreeing slice contributes one observation: its center x paired with its
  chain's first and last rule pixel rows. A least-squares line through the
  first-rule observations is the grid's top edge, and likewise the bottom; each
  fit drops gross outliers once (see `_fit_line_without_outliers`).
  """
  observations = [
    (chain.center_x, chain.rule_ys[0], chain.rule_ys[-1])
    for chain in consensus.chains
  ]

  pitch_estimate = statistics.median(
    (bottom - top) / consensus.row_count for _, top, bottom in observations
  )
  residual_tolerance = _FIT_RESIDUAL_TOLERANCE_IN_PITCHES * pitch_estimate
  return _RuleLines(
    top=_fit_line_without_outliers(
      [(x, top) for x, top, _ in observations], residual_tolerance
    ),
    bottom=_fit_line_without_outliers(
      [(x, bottom) for x, _, bottom in observations], residual_tolerance
    ),
  )


def _fit_border_lines(
  gray: Image.Image, grid_top_y: float, grid_bottom_y: float, pitch: float
) -> _BorderLines:
  """Fit the grid's side borders as straight lines.

  The grid's height is cut into horizontal bands, and each band is averaged
  into a per-pixel-column profile — `rule_grid`'s dip machinery rotated 90
  degrees — whose outermost dips mark the outermost printed vertical lines.
  A band can miss a border (background swallowing the dip, dense writing),
  reporting some interior column line instead, so each side keeps only the
  samples near its median before fitting.

  Raises:
    SheetGeometryError: a border was located in too few bands to fit a line.
  """
  band_height = (grid_bottom_y - grid_top_y) / _BORDER_BAND_COUNT
  # (band-center y, leftmost dip x, rightmost dip x) per band with any dips.
  samples: list[tuple[float, int, int]] = []
  for band_index in range(_BORDER_BAND_COUNT):
    band_top = grid_top_y + band_index * band_height
    band = gray.crop(
      (0, round(band_top), gray.width, round(band_top + band_height))
    )
    centers = dip_centers(pixel_column_profile(band))
    if len(centers) < 2:
      continue
    samples.append((band_top + band_height / 2, centers[0], centers[-1]))

  return _BorderLines(
    left=_fit_border(
      [(y, left) for y, left, _ in samples], pitch, _SheetSide.LEFT
    ),
    right=_fit_border(
      [(y, right) for y, _, right in samples], pitch, _SheetSide.RIGHT
    ),
  )


def _fit_border(
  samples: Sequence[tuple[float, float]], pitch: float, side: _SheetSide
) -> statistics.LinearRegression:
  """Fit one border line from per-band samples, discarding bands that missed.

  Raises:
    SheetGeometryError: fewer than two bands agree on the border's position.
  """
  if not samples:
    raise SheetGeometryError(
      f'no vertical rules found anywhere for the {side.value} border'
    )
  median_x = statistics.median(x for _, x in samples)
  tolerance = _BORDER_OUTLIER_TOLERANCE_IN_PITCHES * pitch
  kept = [(y, x) for y, x in samples if abs(x - median_x) <= tolerance]
  if len(kept) < 2:
    raise SheetGeometryError(
      f'only {len(kept)} band(s) located the {side.value} border near '
      f'x={median_x:.0f}; samples: {[round(x) for _, x in samples]}'
    )
  return _fit_line(kept)


def _extended_quad(
  rule_lines: _RuleLines, borders: _BorderLines, pitch: float
) -> Quad:
  """The grid's corner quad, pushed outward by the dewarp margins.

  Each corner starts at the intersection of a rule line and a border line. The
  vertical margin moves the corner up or down along its border line, so the
  corner stays on the border; the side margin then shifts plain x. Strictly that
  x shift should also nudge y by the rule line's slope, but at half a pitch of
  shift and rule slopes under ~0.05 the nudge is a pixel or two, so it is
  skipped.
  """
  top_margin = _DEWARP_TOP_MARGIN_IN_PITCHES * pitch
  bottom_margin = _DEWARP_BOTTOM_MARGIN_IN_PITCHES * pitch
  side_margin = _DEWARP_SIDE_MARGIN_IN_PITCHES * pitch

  def corner(
    rule_line: statistics.LinearRegression,
    border: statistics.LinearRegression,
    y_shift: float,
    x_shift: float,
  ) -> Point:
    y = _intersect(rule_line, border).y + y_shift
    return Point(x=_line_value(border, y) + x_shift, y=y)

  return Quad(
    top_left=corner(rule_lines.top, borders.left, -top_margin, -side_margin),
    bottom_left=corner(
      rule_lines.bottom, borders.left, bottom_margin, -side_margin
    ),
    bottom_right=corner(
      rule_lines.bottom, borders.right, bottom_margin, side_margin
    ),
    top_right=corner(rule_lines.top, borders.right, -top_margin, side_margin),
  )


def _fit_line_without_outliers(
  points: Sequence[tuple[float, float]], residual_tolerance: float
) -> statistics.LinearRegression:
  """Least-squares fit, refit once without gross outliers.

  A slice whose chain is shifted by a rule (a missed top rule plus a chained
  footer stroke, say) sits a whole row pitch off the true line; one rejection
  pass keeps such slices from bending the fit. Two inliers — a line's minimum
  — suffice for the refit; fewer means the observations are mutually
  inconsistent, which is an error rather than something to fit through.

  Raises:
    SheetGeometryError: fewer than two points survive the rejection pass.
  """
  line = _fit_line(points)
  kept = [
    point
    for point in points
    if abs(_line_value(line, point[0]) - point[1]) <= residual_tolerance
  ]
  if len(kept) < 2:
    raise SheetGeometryError(
      f'no consistent rule line: all but {len(kept)} of {len(points)} slice '
      f'observations sit more than {residual_tolerance:.0f}px from the fit'
    )
  if len(kept) < len(points):
    line = _fit_line(kept)
  return line


def _fit_line(
  points: Sequence[tuple[float, float]],
) -> statistics.LinearRegression:
  """Least-squares line for `(independent, dependent)` points."""
  return statistics.linear_regression(
    [independent for independent, _ in points],
    [dependent for _, dependent in points],
  )


def _line_value(line: statistics.LinearRegression, at: float) -> float:
  """Evaluate a fitted line at a point."""
  return line.intercept + line.slope * at


def _intersect(
  rule_line: statistics.LinearRegression,
  border_line: statistics.LinearRegression,
) -> Point:
  """Intersect a rule line (y as a function of x) with a border line (x as a
  function of y).
  """
  x = (border_line.intercept + border_line.slope * rule_line.intercept) / (
    1 - rule_line.slope * border_line.slope
  )
  return Point(x=x, y=rule_line.intercept + rule_line.slope * x)


def _distance(a: Point, b: Point) -> float:
  """Euclidean distance between two points."""
  return math.hypot(a.x - b.x, a.y - b.y)


def _mean_edge_length(
  edge_start: Point, edge_end: Point, other_start: Point, other_end: Point
) -> int:
  """Average length of two opposite quad edges, rounded to whole pixels."""
  return round(
    (_distance(edge_start, edge_end) + _distance(other_start, other_end)) / 2
  )


def _perspective_coefficients(
  quad: Quad, width: int, height: int
) -> tuple[float, ...]:
  """PIL `PERSPECTIVE` data mapping the output rectangle onto `quad`.

  PIL samples each output pixel `(x, y)` from the source at `((a x + b y + c) /
  (g x + h y + 1), (d x + e y + f) / (g x + h y + 1))`; the eight coefficients
  follow from requiring the four output corners to land on the quad's corners.
  """
  corners = [
    ((0.0, 0.0), quad.top_left),
    ((0.0, float(height)), quad.bottom_left),
    ((float(width), float(height)), quad.bottom_right),
    ((float(width), 0.0), quad.top_right),
  ]
  matrix: list[list[float]] = []
  right_hand_side: list[float] = []
  for (out_x, out_y), source in corners:
    matrix.append(
      [out_x, out_y, 1, 0, 0, 0, -out_x * source.x, -out_y * source.x]
    )
    right_hand_side.append(source.x)
    matrix.append(
      [0, 0, 0, out_x, out_y, 1, -out_x * source.y, -out_y * source.y]
    )
    right_hand_side.append(source.y)
  return tuple(_solve_linear_system(matrix, right_hand_side))


def _solve_linear_system(
  matrix: Sequence[Sequence[float]], right_hand_side: Sequence[float]
) -> list[float]:
  """Solve `matrix @ solution = right_hand_side` by Gaussian elimination.

  Partial pivoting keeps the 8x8 homography solve stable. A zero pivot means
  the quad was degenerate (collinear corners) — no detected grid should
  produce one, and raising keeps the failure loud if one ever does.

  Raises:
    SheetGeometryError: the system is singular.
  """
  size = len(right_hand_side)
  rows = [
    [*row, value] for row, value in zip(matrix, right_hand_side, strict=True)
  ]
  for column in range(size):
    pivot_row = max(
      range(column, size), key=lambda row_index: abs(rows[row_index][column])
    )
    rows[column], rows[pivot_row] = rows[pivot_row], rows[column]
    pivot = rows[column][column]
    if pivot == 0:
      raise SheetGeometryError(
        'degenerate corner quad: the homography solve hit a zero pivot'
      )
    for row_index in range(column + 1, size):
      factor = rows[row_index][column] / pivot
      for other_column in range(column, size + 1):
        rows[row_index][other_column] -= factor * rows[column][other_column]

  solution = [0.0] * size
  for column in reversed(range(size)):
    accumulated = sum(
      rows[column][later] * solution[later] for later in range(column + 1, size)
    )
    solution[column] = (rows[column][size] - accumulated) / rows[column][column]
  return solution
