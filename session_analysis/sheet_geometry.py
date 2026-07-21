# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Per-scan geometry: dewarp a scoresheet scan, then detect its printed grid.

A scan arrives with whatever perspective the capture left in it — on the live
sample the printed rules drift about 1.5 row pitches across the sheet's width,
which defeats any flat horizontal projection. Geometry therefore runs in two
passes (see spec.md, Extraction):

- **Dewarp** (`dewarp_sheet`): narrow column slices each locate the printed
  rules; the fitted top and bottom rule lines and the side border lines
  intersect into the grid's corner quad, and a perspective transform maps the
  quad — extended with margin for the footer and strip padding — to an upright
  rectangle at native scale.
- **Detect** (`detect_sheet_geometry`): in dewarped space the rules are near
  horizontal, so a projection profile finds them, and the row grid is identified
  structurally — the longest uniform-pitch chain of rules — with no positional
  template.

The resulting `SheetGeometry` holds tight rule-to-rule boxes in dewarped-image
coordinates; handwriting routinely bleeds past the printed rules, so each
consumer pads the tight boxes at cut time. Extraction cuts its strips from the
geometry and the review UI crops from it, so geometry and source quad persist
alongside the processed session — the dewarped frame stays reproducible from the
archived scan — rather than being recomputed per consumer.
"""

import collections
import dataclasses
import enum
import itertools
import math
import statistics
from collections.abc import Sequence
from typing import Annotated, NamedTuple

import pydantic
from PIL import Image

from session_analysis.frozen_model import FrozenModel

# A printed rule shows as a narrow dip in a darkness profile: at least this much
# darker than the local median luminance. The baseline is local, not global,
# because lighting varies across a phone scan by more than a rule's own depth.
_MINIMUM_RULE_DIP = 15

# The local-baseline window is the profile length divided by this. It must
# comfortably exceed a rule's thickness (so the median stays at paper level)
# while staying near the row pitch (so the baseline tracks lighting changes).
_BASELINE_WINDOW_DIVISOR = 50

# A gap between adjacent rules may deviate this much from the chain's reference
# gap and still count as part of the same uniform grid.
_GAP_TOLERANCE_FRACTION = 0.2

# When seeding candidate rule chains, how many of the following centers may
# serve as a chain's second point. Interlopers sit between rules, so the true
# next rule is never far down the candidate list.
_CHAIN_SEED_NEIGHBOR_LIMIT = 10

# A plausible row pitch is at least the profile length over this; smaller
# reference gaps (adjacent handwriting dips) are never the grid's. This bakes in
# the assumption that the grid spans a substantial fraction of the frame — a
# sheet photographed small in a tall frame pushes its real pitch under the
# floor, and detection then refuses the scan loudly.
_MINIMUM_PITCH_DIVISOR = 120

# After the first rule-line fit, slices missing the fit by more than this many
# row pitches are outliers — typically a chain that kept one dip too many at an
# end — and are dropped for the refit.
_FIT_RESIDUAL_TOLERANCE_IN_PITCHES = 0.5

# The footer is one handwritten line just below the grid; this many row pitches
# below the bottom rule covers it with margin.
_FOOTER_HEIGHT_IN_ROW_PITCHES = 2.5

# How many column slices the dewarp pass cuts the scan into, and how many must
# individually resolve the grid for the consensus to be trusted.
_SLICE_COUNT = 12
_MINIMUM_VALID_SLICES = 4

# A scoresheet grid has at least this many rows; a shorter chain is noise (a
# header box, a run of handwriting dips) and doesn't vote for the row count.
_MINIMUM_ROW_COUNT = 8

# How many horizontal bands sample the side borders, and how far (in row
# pitches) a band's border sample may sit from the per-side median before it is
# discarded — a band can miss a border entirely when the dark background beyond
# a cut-off sheet corner swallows the rule's dip.
_BORDER_BAND_COUNT = 8
_BORDER_OUTLIER_TOLERANCE_IN_PITCHES = 2

# Margins the dewarp adds around the grid quad, in row pitches: room above the
# top rule for strip padding, room below the bottom rule for the footer plus
# padding, and a little slack on the sides.
_DEWARP_TOP_MARGIN_IN_PITCHES = 0.5
_DEWARP_BOTTOM_MARGIN_IN_PITCHES = _FOOTER_HEIGHT_IN_ROW_PITCHES + 0.5
_DEWARP_SIDE_MARGIN_IN_PITCHES = 0.5


class SheetGeometryError(Exception):
  """Raised when a scan's row grid cannot be detected."""


class Box(FrozenModel):
  """An axis-aligned pixel rectangle, in PIL crop order.

  `left`/`top` are inclusive, `right`/`bottom` exclusive, so a `Box` passes
  straight to `Image.crop`.
  """

  left: int
  top: int
  right: int
  bottom: int


class Point(FrozenModel):
  """A pixel position, in the coordinates of whichever image it came from."""

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
    `_FOOTER_HEIGHT_IN_ROW_PITCHES` pitches, clamped to the image — sized with
    margin already, so consumers cut it unpadded.
    """
    bottom_row = self.row_boxes[-1]
    footer_height = round(_FOOTER_HEIGHT_IN_ROW_PITCHES * self.row_pitch())
    return Box(
      left=bottom_row.left,
      top=bottom_row.bottom,
      right=bottom_row.right,
      bottom=min(self.image_height, bottom_row.bottom + footer_height),
    )


@dataclasses.dataclass(frozen=True)
class DewarpedSheet:
  """A scan mapped upright: the transformed image and how it was derived.

  `row_count` is the grid size the quad fit resolved — callers cross-check it
  against what detection later finds in the dewarped frame.
  """

  image: Image.Image
  source_quad: Quad
  row_count: int


class _SliceChain(NamedTuple):
  """One column slice's resolved rule chain, at the slice's center x."""

  center_x: float
  rule_ys: list[int]


@dataclasses.dataclass(frozen=True)
class _GridConsensus:
  """The slices' agreement: the voted row count and the chains matching it."""

  row_count: int
  chains: list[_SliceChain]


class _RuleLines(NamedTuple):
  """The grid's top and bottom rules, each as a `y(x)` line."""

  top: statistics.LinearRegression
  bottom: statistics.LinearRegression


class _BorderLines(NamedTuple):
  """The grid's side borders, each as an `x(y)` line."""

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
  consensus = _resolve_grid_consensus(gray)
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
  # is projective (measured ~30px of residual on the live scan); a homography
  # flattens every rule, not just the two anchoring ones.
  dewarped = image.transform(
    (width, height),
    Image.Transform.PERSPECTIVE,
    data=_perspective_coefficients(quad, width, height),
    resample=Image.Resampling.BICUBIC,
  )
  return DewarpedSheet(
    image=dewarped, source_quad=quad, row_count=consensus.row_count
  )


def detect_sheet_geometry(image: Image.Image) -> SheetGeometry:
  """Detect a dewarped scan's printed row grid.

  The row count comes from the scan itself — the column slices' consensus —
  so any form with at least `_MINIMUM_ROW_COUNT` rows resolves without
  configuration; the count surfaces as `len(row_boxes)`. Rule positions are
  per-rule medians across the slices' chains rather than one full-width
  profile: even after the dewarp, gentle page curl leaves a rule drifting a
  fraction of a pitch across the width — enough to smear a full-width dip
  below detectability, while each slice still sees it sharply. The strip
  padding absorbs the residual drift the median glosses over. (On the live
  form the printed header row is taller than a board row, so the pitch chain
  excludes it on its own; a form whose header row height falls within the
  pitch tolerance would count it as an extra row.)

  Raises:
    SheetGeometryError: the column slices couldn't agree on a grid.
  """
  gray = image.convert('L')
  consensus = _resolve_grid_consensus(gray)
  rules = [
    round(
      statistics.median(chain.rule_ys[index] for chain in consensus.chains)
    )
    for index in range(consensus.row_count + 1)
  ]

  # The grid's horizontal extent: the outermost dark columns of the grid band,
  # i.e. the table's vertical border rules.
  grid_band = gray.crop((0, rules[0], gray.width, rules[-1]))
  column_centers = _dip_centers(_mean_luminance_per_column(grid_band))
  if len(column_centers) < 2:
    raise SheetGeometryError(
      f'no vertical border rules found in the grid band '
      f'(rows {rules[0]}..{rules[-1]})'
    )
  grid_left, grid_right = column_centers[0], column_centers[-1]

  row_boxes = tuple(
    Box(left=grid_left, top=top, right=grid_right, bottom=bottom)
    for top, bottom in itertools.pairwise(rules)
  )
  return SheetGeometry(
    image_width=gray.width, image_height=gray.height, row_boxes=row_boxes
  )


def _resolve_grid_consensus(gray: Image.Image) -> _GridConsensus:
  """Resolve the grid per column slice, inferring the row count by consensus.

  Each slice is narrow enough that a slanted or curled rule stays sharp in its
  profile. The grid's row count is not assumed: each slice's chain votes, and
  the modal count wins. A slice whose chain disagrees with the mode is
  untrustworthy — most often the footer's handwriting chained on as a ghost
  rule, or background at the sheet's edge hid part of the grid — and is
  skipped rather than guessed at.

  Raises:
    SheetGeometryError: no slice resolved a plausible grid, the slices split
      evenly between two row counts, or too few match the consensus.
  """
  slice_width = gray.width // _SLICE_COUNT
  chains: list[_SliceChain] = []
  row_counts: list[int] = []
  for slice_index in range(_SLICE_COUNT):
    left = slice_index * slice_width
    band = gray.crop((left, 0, left + slice_width, gray.height))
    centers = _dip_centers(_mean_luminance_per_row(band))
    if len(centers) < 2:
      row_counts.append(0)
      continue
    chain = _longest_uniform_chain(
      centers, minimum_gap=gray.height // _MINIMUM_PITCH_DIVISOR
    )
    row_counts.append(len(chain) - 1)
    chains.append(_SliceChain(center_x=left + slice_width / 2, rule_ys=chain))

  votes = collections.Counter(
    len(chain.rule_ys) - 1
    for chain in chains
    if len(chain.rule_ys) - 1 >= _MINIMUM_ROW_COUNT
  )
  if not votes:
    raise SheetGeometryError(
      f'none of the {_SLICE_COUNT} column slices resolved a plausible grid '
      f'(row counts per slice: {row_counts}, minimum {_MINIMUM_ROW_COUNT})'
    )
  ranked = votes.most_common()
  if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
    raise SheetGeometryError(
      f'ambiguous row count: {ranked[0][1]} slice(s) found {ranked[0][0]} '
      f'rows and as many found {ranked[1][0]} (row counts per slice: '
      f'{row_counts})'
    )
  row_count = ranked[0][0]

  matching = [
    chain for chain in chains if len(chain.rule_ys) - 1 == row_count
  ]
  if len(matching) < _MINIMUM_VALID_SLICES:
    raise SheetGeometryError(
      f'grid resolved in only {len(matching)} of {_SLICE_COUNT} column '
      f'slices (row counts per slice: {row_counts}); need at least '
      f'{_MINIMUM_VALID_SLICES}'
    )
  return _GridConsensus(row_count=row_count, chains=matching)


def _fit_rule_lines(consensus: _GridConsensus) -> _RuleLines:
  """Fit the grid's top and bottom rules as `y = intercept + slope * x` lines.

  The slices' top and bottom rule positions anchor the fits.
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
  """Fit the grid's side borders as `x = intercept + slope * y` lines.

  The outermost vertical rules are sampled per horizontal band across the
  grid's height. A band can miss a border (background swallowing the dip,
  dense writing), reporting some interior rule instead, so each side keeps
  only the samples near its median before fitting.

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
    centers = _dip_centers(_mean_luminance_per_column(band))
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

  Vertical margins slide each corner along its border line; the small side
  margin then shifts x directly — at these margins the rule slope would move y
  by at most a pixel or two, so that correction is skipped.
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
    top_right=corner(
      rule_lines.top, borders.right, -top_margin, side_margin
    ),
  )


def _mean_luminance_per_row(gray: Image.Image) -> Sequence[int]:
  """Average each pixel row to one value — horizontal rules show up dark."""
  return list(gray.resize((1, gray.height), Image.Resampling.BOX).tobytes())


def _mean_luminance_per_column(gray: Image.Image) -> Sequence[int]:
  """Average each pixel column to one value — vertical rules show up dark."""
  return list(gray.resize((gray.width, 1), Image.Resampling.BOX).tobytes())


def _dip_centers(profile: Sequence[int]) -> list[int]:
  """Return the center index of each narrow dark dip in a luminance profile.

  A dip is a run of adjacent values at least `_MINIMUM_RULE_DIP` below the
  rolling median around them. Wide dark regions (the background beyond the
  sheet's edge, a shadow band) darken their own baseline and so do not register
  — only rule-like narrow features do.
  """
  half_window = max(4, len(profile) // (2 * _BASELINE_WINDOW_DIVISOR))

  centers: list[int] = []
  dip_start: int | None = None
  for index, value in enumerate(profile):
    window = profile[max(0, index - half_window) : index + half_window + 1]
    if statistics.median(window) - value >= _MINIMUM_RULE_DIP:
      if dip_start is None:
        dip_start = index
    elif dip_start is not None:
      centers.append((dip_start + index - 1) // 2)
      dip_start = None
  if dip_start is not None:
    centers.append((dip_start + len(profile) - 1) // 2)
  return centers


def _longest_uniform_chain(
  centers: Sequence[int], *, minimum_gap: int
) -> list[int]:
  """Return the longest chain of centers spaced by one near-uniform gap.

  Each pair of nearby centers seeds a candidate chain and its reference gap;
  the chain then extends step by step, each time taking the center closest to
  one reference gap beyond the last, within `_GAP_TOLERANCE_FRACTION`. Centers
  between steps are skipped — handwriting cuts dips of its own between rules,
  and a chain that broke on those would never span the grid. What separates
  the grid's rules from every other dark line on the page (a title underline,
  the sheet's edges, that same handwriting) is that only the grid repeats at
  one pitch, dozens of times; `minimum_gap` keeps dense noise from posing as a
  tiny-pitch grid of its own.

  Raises:
    SheetGeometryError: fewer than two centers, so no chain exists at all.
  """
  if len(centers) < 2:
    raise SheetGeometryError(
      f'too few rule candidates to form a grid: centers {list(centers)}'
    )

  best: list[int] = []
  for start in range(len(centers) - 1):
    seed_limit = min(start + 1 + _CHAIN_SEED_NEIGHBOR_LIMIT, len(centers))
    for second in range(start + 1, seed_limit):
      reference_gap = centers[second] - centers[start]
      if reference_gap < minimum_gap:
        continue
      chain = _extend_chain(centers, start, second, reference_gap)
      if len(chain) > len(best):
        best = chain
  return best


def _extend_chain(
  centers: Sequence[int], start: int, second: int, reference_gap: int
) -> list[int]:
  """Grow a two-center seed by near-one-gap steps, skipping interlopers."""
  tolerance = _GAP_TOLERANCE_FRACTION * reference_gap
  chain = [centers[start], centers[second]]
  position = second
  while True:
    target = chain[-1] + reference_gap
    # The candidate closest to the target, among centers within tolerance.
    step_index: int | None = None
    for index in range(position + 1, len(centers)):
      if centers[index] > target + tolerance:
        break
      if abs(centers[index] - target) <= tolerance and (
        step_index is None
        or abs(centers[index] - target) < abs(centers[step_index] - target)
      ):
        step_index = index
    if step_index is None:
      return chain
    chain.append(centers[step_index])
    position = step_index


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
  """Intersect a rule line `y(x)` with a border line `x(y)`."""
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

  Partial pivoting keeps the 8x8 homography solve stable; a zero pivot means
  the quad was degenerate (collinear corners), which real detection never
  produces.

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
