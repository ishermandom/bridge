# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Find a scoresheet's printed rules — the grid's horizontal lines.

Everything here reads one simple signal. Averaging a band of pixels down to a
single list of brightness values — one value per pixel row, together a "profile"
— makes a printed rule spanning the band show up as a sharp dark dip a few
entries wide. A dip's depth scales with the fraction of the band's width the
dark feature crosses: a rule crosses all of it, handwriting usually a sliver.
The concrete numbers in this file come from a reference scan, a 3000x4000-pixel
phone photo of a filled-in club scoresheet: its paper averages ~200 luminance (0
is black, 255 white), its rules repeat every ~73px (the "pitch"), and a rule's
~3px-thick line dips its profile entries by 20-90 luminance levels depending on
the band's width.

Three refinements make that signal trustworthy on a real photo:

- **Local baselines.** A dip is judged against the rolling median around it, not
  a global threshold: lighting varies across a phone photo by more than a rule's
  whole dip depth, and wide dark regions (the table surface beyond the sheet's
  edge) darken their own baseline instead of reading as giant dips.
- **Pitch chains.** The dip threshold alone cannot finish the job. Handwriting
  dents the profile too — any ink in the band lowers its pixel row's average —
  and while most such dips are shallow, in a ~250px-wide slice a bold horizontal
  stroke can rival a rule's depth (the reference scan's densely written slices
  show dozens of above-threshold non-rule dips). And printed lines that aren't
  grid rules at all — a header box's lines, a title underline — are exactly as
  dark as rules. The grid is therefore identified structurally: the longest
  chain of dips spaced one near-uniform pitch apart, skipping interlopers. Only
  the grid repeats at one spacing, dozens of times.
- **Column slices.** Profiles are taken over narrow vertical slices of the
  image, never its full width. Page curl or a slight tilt makes a rule drift
  across the sheet, and a drifting rule stays sharp within a slice but smears
  when averaged across the whole width. Each slice reads the rules on its own,
  and only the slices that agree on one run of rules are combined; the rest are
  excluded rather than guessed at.

`rules_bounding_rows` is the entry point: `sheet_geometry` calls it once per
panel, with the row count the sheet's layout reading reports.
"""

import dataclasses
import itertools
import statistics
from collections.abc import Sequence

from PIL import Image

# How much darker than its surroundings a profile entry must be to count as part
# of a luminance dip, where "surroundings" is the rolling median over the window
# sized by `_BASELINE_WINDOW_DIVISOR`. This is a coarse pre-filter, not a
# complete separator: on the reference scan every rule dips 20+ luminance levels
# and most handwriting dips stay under 10, but a bold stroke crossing much of a
# narrow slice passes any threshold that faint rules can also pass — removing
# those survivors is the pitch chain's job. 15 keeps every rule while pruning
# the shallow majority of handwriting; faint printing or a washed-out photo
# narrows that headroom, and when it collapses the failure is the loud no-grid
# error, not wrong geometry.
_MINIMUM_RULE_DIP = 15

# Sizes the rolling-median window as the profile's length divided by this: a
# 4000-pixel-tall photo yields a 4000-entry profile and so an ~80-entry window.
# The window must span far more entries than a rule's dip does (so the median
# inside it reflects paper, not the rule itself) yet few enough that it tracks
# gradual lighting change across the photo.
_BASELINE_WINDOW_DIVISOR = 50

# How far the spacing between two chained rules may deviate from the chain's
# reference gap, as a fraction. With rules ~73px apart, the next rule may sit
# 58..88px beyond the previous one: loose enough for perspective compressing the
# pitch across the sheet plus detection jitter, tight enough to reject
# handwriting dips that land mid-row.
_GAP_TOLERANCE_FRACTION = 0.2

# A chain is seeded by a candidate dip pair; this caps how many of the dips
# following the first may serve as the pair's second member. Between two rules
# there are only ever a handful of handwriting dips, so the true next rule is
# never far down the list — and without the cap, seeding would try every pair
# quadratically.
_CHAIN_SEED_NEIGHBOR_LIMIT = 10

# No real grid's pitch is smaller than the image height divided by this (33px
# for a 4000-pixel-tall photo). Dense handwriting can produce dips every few
# pixels, and without this floor a chain of those could outscore the real grid.
# This bakes in the assumption that the grid spans a substantial fraction of the
# frame; a sheet photographed small in a tall frame pushes its real pitch under
# the floor, and the scan is then refused loudly rather than misread.
_MINIMUM_PITCH_DIVISOR = 120

# How many vertical slices the image is read in — each ~250px wide on the
# reference scan, narrow enough that a slanted rule drifts only a few pixels
# within it — and how many must agree on the same run of rules before it is
# trusted.
_SLICE_COUNT = 12
_MINIMUM_VALID_SLICES = 4

# How much better the run of rules chosen by `rules_bounding_rows` must fit the
# reported bounds than the next-best run, in row pitches. Runs sit a pitch
# apart, so a sound reading wins by about one; anything much closer means the
# bounds fall between two runs and the answer is a coin toss. Measured on the
# three real scan pages, the median slice preferred its window by 1.55 to 1.82
# pitches, so half a pitch leaves roughly threefold headroom — and the check
# reads the median rather than the minimum because individual slices do come
# down to a pixel or two.
_AMBIGUOUS_WINDOW_MARGIN_IN_PITCHES = 0.5

# How far two column slices' chosen runs may start apart, in row pitches, and
# still count as reading the same rows. Measured on the real scan pages, the
# slices that agree spread at most 0.24 of a pitch while a stray sits a whole
# pitch off, so this sits between the two.
_AGREEING_WINDOW_SPREAD_IN_PITCHES = 0.35

# What share of the slices that read at all may disagree with the rest before
# the sheet is refused. A third: shading or a run of round-break rules can shift
# a few contiguous slices by a rule and should not lose the sheet, while a
# genuine split between two runs leaves neither side this far ahead.
_DISSENTING_SLICE_FRACTION = 1 / 3

# How far the chosen run's ends may sit from the reported bounds, in row
# pitches, before it is taken to be a different structure altogether rather than
# the reported rows read imprecisely. The reported bounds drift under a pitch on
# the real pages; a run found inside a chart printed elsewhere on the sheet is
# many pitches away.
_STRAYED_WINDOW_IN_PITCHES = 2.0


class SheetGeometryError(Exception):
  """Raised when a scan's row grid cannot be resolved."""


@dataclasses.dataclass(frozen=True)
class _SliceReading:
  """One column slice's answer about where a known number of rows sit."""

  rules: Sequence[int]
  # How much better this run fitted the reported bounds than the next one down,
  # or None when the slice's chain held only one run of the right length and
  # there was nothing to choose between.
  margin: float | None


def rules_bounding_rows(
  gray: Image.Image,
  *,
  row_count: int,
  left: int,
  right: int,
  top: float,
  bottom: float,
) -> Sequence[int]:
  """The `row_count + 1` printed rules bounding a known number of rows.

  The sheet's layout reading supplies the row count, so the only job is to find
  which of the detected rules bound that many rows. A slice's chain routinely
  runs past the grid at either end — a scale chart above, the footer's guide
  underline below — and the window of the chain that is the right length and
  best fits `top`..`bottom` is the grid. Since the count is exact and those
  bounds are approximate, the count decides the window's size and the bounds
  only its position.

  The bounds must be good to better than half a row pitch, and nothing here can
  check that they were. Drifting both ends the same way by more than half a
  pitch makes the neighbouring run the nearer one, and it is then chosen as
  decisively as the right one would have been: at 0.3 and 0.7 of a pitch the
  chosen run sits the same distance from the reported bounds and beats its rival
  by the same margin, so neither the distance nor the margin separates them.
  Swept on the v4 fixture, drift beyond about a third of a pitch either way is
  refused, and beyond about three quarters it resolves one row off with nothing
  raised.

  What saves a real reading is that its drift is one-ended — measured at a few
  pixels on the top edge against up to 0.7 of a pitch on the bottom — so the
  accurate end anchors the score. A reading that shifts bodily is the case this
  cannot see, and tasks.md `#board-number-continuity` carries the check that
  can: a grid taken one row high makes the first strip the printed header and
  drops the last board row, so the transcribed board numbers stop running
  consecutively.

  Args:
    gray: the sheet in grayscale (PIL mode `'L'`).
    row_count: how many ruled rows the window must bound, taken as exact.
    left: the panel's left edge; slicing is confined between this and `right`,
      so a panel reads only its own rules and not a neighbouring panel's.
    right: the panel's right edge.
    top: roughly where the panel's first rule sits.
    bottom: roughly where its last rule sits.

  Returns:
    Each rule's pixel row, top to bottom, as the median across the slices that
    agreed on one window, so page curl is averaged out rather than followed.

  Raises:
    SheetGeometryError: too few slices resolved a chain long enough to hold
      `row_count + 1` rules, so the count and the pixels disagree — or the
      bounds sat between two runs of that length, so which rows were meant
      cannot be told.
  """
  wanted = row_count + 1
  readings = _slice_readings(gray, wanted, left, right, top, bottom)
  if len(readings) < _MINIMUM_VALID_SLICES:
    raise SheetGeometryError(
      f'only {len(readings)} of {_SLICE_COUNT} column slices between x={left} '
      f'and x={right} resolved a run of {wanted} rules for the {row_count} '
      f'rows expected; need at least {_MINIMUM_VALID_SLICES}'
    )

  pitch = statistics.median(
    statistics.median(
      second - first for first, second in itertools.pairwise(reading.rules)
    )
    for reading in readings
  )
  agreeing = _agreeing_on_one_run(readings, pitch, wanted)
  rules = [
    round(statistics.median(reading.rules[index] for reading in agreeing))
    for index in range(wanted)
  ]

  # Where the chosen run actually sits. The scoring inside a slice is relative —
  # runs are only ranked against each other — so if some other uniform structure
  # on the page chains longer than the grid does, a run inside *it* can win
  # without ever being near the rows that were reported. A conversion chart
  # printed above a short panel is the realistic shape of that.
  strayed = max(abs(rules[0] - top), abs(rules[-1] - bottom))
  if strayed > _STRAYED_WINDOW_IN_PITCHES * pitch:
    raise SheetGeometryError(
      f'the closest run of {wanted} rules sits {strayed:.0f}px from the '
      f'reported bounds {top:.0f}..{bottom:.0f}, against a pitch of '
      f'{pitch:.0f}; the rules found are not the rows that were reported'
    )

  # Whether the run was chosen decisively or by rounding. Read from the slices
  # that agreed on it, since a stray slice is precisely one whose two best runs
  # scored alike — it would otherwise drag the median down and refuse a sheet
  # the rest of the slices were sure of. Judged only when enough of them had a
  # rival to judge from — a median over a single margin is just that margin, and
  # says nothing about whether the slices agreed.
  margins = [
    reading.margin for reading in agreeing if reading.margin is not None
  ]
  if len(margins) >= _MINIMUM_VALID_SLICES:
    margin = statistics.median(margins)
    if margin < _AMBIGUOUS_WINDOW_MARGIN_IN_PITCHES * pitch:
      raise SheetGeometryError(
        f'the reported bounds {top:.0f}..{bottom:.0f} sit between two runs of '
        f'{wanted} rules, preferring one by {margin:.0f}px against a pitch of '
        f'{pitch:.0f}; which rows were meant cannot be told'
      )
  return rules


def _slice_readings(
  gray: Image.Image,
  wanted: int,
  left: int,
  right: int,
  top: float,
  bottom: float,
) -> Sequence[_SliceReading]:
  """Each column slice's best run of `wanted` rules, where it resolved one.

  The span between `left` and `right` is cut into slices, and each slice is read
  for its own rule chain. A slice whose chain is too short to hold `wanted`
  rules is simply absent.
  """
  slice_width = max(1, (right - left) // _SLICE_COUNT)
  readings: list[_SliceReading] = []
  for slice_index in range(_SLICE_COUNT):
    slice_left = left + slice_index * slice_width
    band = gray.crop((slice_left, 0, slice_left + slice_width, gray.height))
    centers = dip_centers(pixel_row_profile(band))
    if len(centers) < 2:
      continue
    chain = _longest_uniform_chain(
      centers, minimum_gap=gray.height // _MINIMUM_PITCH_DIVISOR
    )
    if len(chain) < wanted:
      continue
    # Scored on both ends, so a chain overhanging at the top and the bottom
    # alike is centred rather than pinned to whichever end the bounds drifted
    # toward.
    scored = sorted(
      (
        (abs(run[0] - top) + abs(run[-1] - bottom), run)
        for run in (
          chain[start : start + wanted]
          for start in range(len(chain) - wanted + 1)
        )
      ),
      key=lambda pair: pair[0],
    )
    readings.append(
      _SliceReading(
        rules=scored[0][1],
        margin=scored[1][0] - scored[0][0] if len(scored) > 1 else None,
      )
    )
  return readings


def _agreeing_on_one_run(
  readings: Sequence[_SliceReading], pitch: float, wanted: int
) -> Sequence[_SliceReading]:
  """The largest group of slices that resolved the same run of rules.

  The largest group rather than the median of what every slice chose: a slice
  that picked up a doubled dip beside a rule lands a whole rule off, and
  averaging it in drags every position toward it — while a half-and-half split
  between two runs puts the median *between* them, equidistant from both, so
  every slice appears to agree with it. The answer would then be rules sitting
  mid-row, every strip cut across a printed rule, and the row count agreeing all
  the while, so nothing downstream would notice.

  Slices are compared on their first rule alone, which is what separates runs a
  whole pitch apart. Comparing every rule would not: on the real pages, slices
  that agree on the first diverge by up to half a pitch further down, because
  the page curls — and absorbing exactly that is what the per-rule median across
  these slices is for. A check over the whole run would refuse a curled page for
  being curled.

  Raises:
    SheetGeometryError: too few slices agree, or too many dissent — either way
      the slices are not reading the same rows.
  """
  tolerance = _AGREEING_WINDOW_SPREAD_IN_PITCHES * pitch
  agreeing: Sequence[_SliceReading] = ()
  for candidate in readings:
    group = [
      reading
      for reading in readings
      if abs(reading.rules[0] - candidate.rules[0]) <= tolerance
    ]
    if len(group) > len(agreeing):
      agreeing = group

  # Dissent is weighed against the slices that read at all, not against a fixed
  # count: a fixed one inverts, refusing eight slices agreeing out of twelve
  # while accepting four out of four. A band of shading or a run of round-break
  # rules can shift a few contiguous slices by a rule; a genuine split cannot
  # leave two thirds of them on one answer.
  dissenting = len(readings) - len(agreeing)
  if len(agreeing) < _MINIMUM_VALID_SLICES or (
    dissenting > _DISSENTING_SLICE_FRACTION * len(readings)
  ):
    raise SheetGeometryError(
      f'{len(agreeing)} of {len(readings)} column slices resolved one run of '
      f'{wanted} rules and {dissenting} resolved another, against a pitch of '
      f'{pitch:.0f}; they are not reading the same rows'
    )
  return agreeing


def pixel_row_profile(gray: Image.Image) -> Sequence[int]:
  """Average each pixel row to one luminance value — the profile in which a
  horizontal rule shows up as a dip.
  """
  return list(gray.resize((1, gray.height), Image.Resampling.BOX).tobytes())


def pixel_column_profile(gray: Image.Image) -> Sequence[int]:
  """Average each pixel column to one luminance value — the profile in which a
  vertical rule shows up as a dip.
  """
  return list(gray.resize((gray.width, 1), Image.Resampling.BOX).tobytes())


def dip_centers(profile: Sequence[int]) -> Sequence[int]:
  """Return the center index of each narrow dark dip in a luminance profile.

  A dip is a run of adjacent values at least `_MINIMUM_RULE_DIP` below the
  rolling median around them. Wide dark regions (the background beyond the
  sheet's edge, a shadow band) darken their own baseline and so do not register
  — only rule-like narrow features do.
  """
  # The floor of 4 (a nine-entry window) keeps any rule's dip a minority of its
  # own window even on small images: were the window allowed to shrink toward
  # the dip's own width, the median would follow the dip down and the dip would
  # erase itself.
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
) -> Sequence[int]:
  """Return the longest chain of dip centers spaced by one near-uniform gap.

  `centers` are dip positions as profile-entry indices in ascending order;
  `minimum_gap` is in the same units.

  Each pair of nearby centers seeds a candidate chain and its reference gap; the
  chain then extends step by step, each time taking the center closest to one
  reference gap beyond the last, within `_GAP_TOLERANCE_FRACTION`. Centers
  between steps are skipped — handwriting cuts dips of its own between rules,
  and a chain that broke on those would never span the grid. What separates the
  grid's rules from every other dark line on the page (a title underline, the
  sheet's edges, that same handwriting) is that only the grid repeats at one
  pitch, dozens of times; `minimum_gap` keeps dense noise from posing as a
  tiny-pitch grid of its own.

  Raises:
    SheetGeometryError: fewer than two centers, so no chain exists at all.
  """
  if len(centers) < 2:
    raise SheetGeometryError(
      f'too few rule candidates to form a grid: centers {list(centers)}'
    )

  best: Sequence[int] = []
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
) -> Sequence[int]:
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
