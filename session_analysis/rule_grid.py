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
  the grid repeats at one spacing, dozens of times — and the chain's length is
  also what counts the rows.
- **Slice consensus.** Profiles are taken over narrow vertical slices of the
  image, never its full width: a perspective-slanted rule stays sharp within a
  slice but smears to invisibility when averaged across the whole width. Each
  slice's chain votes on the grid's row count; the modal count wins, and the
  chains of slices that disagree are excluded from the returned consensus rather
  than guessed at.

`resolve_grid_consensus` is the entry point. `sheet_dewarp` fits the grid's
corner quad from the consensus; `sheet_geometry` turns a dewarped frame's
consensus into per-row boxes.
"""

import collections
import dataclasses
import statistics
from collections.abc import Sequence
from typing import NamedTuple

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
# within it — and how many must agree on the same grid before the consensus is
# trusted.
_SLICE_COUNT = 12
_MINIMUM_VALID_SLICES = 4

# A scoresheet grid has at least this many rows. A shorter uniform chain is some
# other structure (a printed header box's lines, a few aligned words) and
# doesn't get to vote for the row count.
_MINIMUM_ROW_COUNT = 8


class SheetGeometryError(Exception):
  """Raised when a scan's row grid cannot be resolved."""


class SliceChain(NamedTuple):
  """One column slice's resolved rule chain.

  `center_x` is the slice's horizontal center in image pixels; `rule_ys` are the
  detected rules' pixel rows, top to bottom.
  """

  center_x: float
  rule_ys: Sequence[int]


@dataclasses.dataclass(frozen=True)
class GridConsensus:
  """The slices' agreement: the voted row count, and the chains of the slices
  that agree with it.

  The chains are handed over unsummarized because the consumers need opposite
  statistics from them: `sheet_dewarp` fits lines through the per-slice rule
  positions to measure their slant, while `sheet_geometry` takes per-rule
  medians across slices to erase it.
  """

  row_count: int
  chains: list[SliceChain]


def resolve_grid_consensus(gray: Image.Image) -> GridConsensus:
  """Resolve the grid per column slice, inferring the row count by consensus.

  `gray` is the scan already converted to grayscale (PIL mode `'L'`).

  The grid's row count is not assumed: each slice's chain votes, and the
  modal count wins. A slice whose chain disagrees with the mode is
  untrustworthy — most often the footer's handwriting chained on as a ghost
  rule, or background at the sheet's edge hid part of the grid — so its chain
  is excluded from the returned consensus rather than guessed at.

  Raises:
    SheetGeometryError: no slice resolved a plausible grid, the slices split
      evenly between two row counts, or too few match the consensus.
  """
  slice_width = gray.width // _SLICE_COUNT
  chains: list[SliceChain] = []
  row_counts: list[int] = []
  for slice_index in range(_SLICE_COUNT):
    left = slice_index * slice_width
    band = gray.crop((left, 0, left + slice_width, gray.height))
    centers = dip_centers(pixel_row_profile(band))
    if len(centers) < 2:
      row_counts.append(0)
      continue
    chain = _longest_uniform_chain(
      centers, minimum_gap=gray.height // _MINIMUM_PITCH_DIVISOR
    )
    row_counts.append(len(chain) - 1)
    chains.append(SliceChain(center_x=left + slice_width / 2, rule_ys=chain))

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

  matching = [chain for chain in chains if len(chain.rule_ys) - 1 == row_count]
  if len(matching) < _MINIMUM_VALID_SLICES:
    raise SheetGeometryError(
      f'grid resolved in only {len(matching)} of {_SLICE_COUNT} column '
      f'slices (row counts per slice: {row_counts}); need at least '
      f'{_MINIMUM_VALID_SLICES}'
    )
  return GridConsensus(row_count=row_count, chains=matching)


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
