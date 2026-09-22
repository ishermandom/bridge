# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Pack top-level sections onto explicit printed pages.

The print design treats a section as an atom: it renders whole on one page,
ideally within a single column, and two columns exist so that short sections can
sit side by side. WeasyPrint cannot be told this in CSS (spec.md
#section-packing carries the why), so the renderer packs sections itself:

- **Pack**: a greedy pass in document order fills page one's shortened columns,
  then full pages, column by column. A section taller than a full column gets a
  page of its own, its heading spanning the page and its body flowing in two
  columns beneath — and onto further pages when even that page cannot hold it.
  As each page closes, its sections are rebalanced between the two columns, so
  the two come out as near the same height as reading order allows.
"""

from collections.abc import Sequence
from dataclasses import dataclass

# A top-level section's place in document order. A page plan names the sections
# on it by this index, and `SectionRun.sections` holds them in the same order.
type SectionIndex = int

# A vertical measurement in points, as the probe render reported it.
type Points = float


@dataclass(frozen=True)
class MeasuredSection:
  """One section awaiting placement: where it sits, and how tall it stands."""

  index: SectionIndex
  height: Points


@dataclass(frozen=True)
class ColumnFill:
  """How tall a page's two columns stand, for one choice of where to cut."""

  first: Points
  second: Points

  @property
  def tallest(self) -> Points:
    """The taller of the two, which is what has to fit the page."""
    return max(self.first, self.second)

  @property
  def imbalance(self) -> Points:
    """How far apart the two stand; zero is a perfect balance."""
    return abs(self.first - self.second)


@dataclass(frozen=True)
class ColumnPage:
  """A page of whole sections, named by index, packed into its two columns."""

  first_column: tuple[SectionIndex, ...]
  second_column: tuple[SectionIndex, ...]


@dataclass(frozen=True)
class WidePage:
  """A page given over to one section too tall for a single column.

  The section's heading spans the page and its body flows in two columns
  beneath, so the page reads like any other except that nothing sits beside the
  heading.
  """

  section: SectionIndex


type PrintPage = ColumnPage | WidePage


def _fill_at(heights: Sequence[Points], split: int) -> ColumnFill:
  """How the two columns stand when a page is cut after `split` sections."""
  return ColumnFill(sum(heights[:split]), sum(heights[split:]))


def _balanced_split(heights: Sequence[Points], column_height: Points) -> int:
  """How many of a page's sections belong in its first column.

  The reader takes the first column top to bottom and then the second, so the
  first column always holds a leading run of the page's sections; the only
  choice is how long that run is. Of the cuts that overflow neither column, the
  one leaving the two closest in height wins, and a tie keeps more in the first
  column. Greedy filling already put these sections on one page under such a
  cut, so at least one always fits.
  """
  fitting_splits = [
    split
    for split in range(len(heights) + 1)
    if _fill_at(heights, split).tallest <= column_height
  ]

  def imbalance(split: int) -> tuple[Points, int]:
    # The negative split breaks a tie toward the fuller first column.
    return _fill_at(heights, split).imbalance, -split

  return min(fitting_splits, key=imbalance)


class _OpenPage:
  """A column page being filled, column by column."""

  COLUMNS = 2

  def __init__(self, column_height: Points) -> None:
    self.column_height = column_height
    self.placed: list[MeasuredSection] = []
    self.filling_column = 0
    self.column_used_height = 0.0

  def try_place(self, section: MeasuredSection) -> bool:
    """Place the section in the first column with room, or report False."""
    while self.filling_column < self.COLUMNS:
      if self.column_used_height + section.height <= self.column_height:
        self.placed.append(section)
        self.column_used_height += section.height
        return True
      # Only how many columns remain matters: `close` re-splits the page, so
      # this running assignment is never read.
      self.filling_column += 1
      self.column_used_height = 0.0
    return False

  def is_empty(self) -> bool:
    """Whether nothing has been placed on the page."""
    return not self.placed

  def close(self) -> ColumnPage:
    """The page's final, immutable form, its two columns balanced.

    Greedy filling settles which sections share the page; where they sit on it
    is decided here, once the page can take no more.
    """
    indices = [section.index for section in self.placed]
    heights = [section.height for section in self.placed]
    split = _balanced_split(heights, self.column_height)
    return ColumnPage(tuple(indices[:split]), tuple(indices[split:]))


def pack(
  section_heights: Sequence[Points],
  first_column_height: Points,
  column_height: Points,
) -> Sequence[PrintPage]:
  """Pack sections, in order, onto pages.

  Page one's columns are `first_column_height` tall — what the header block left
  free — and every later page's are `column_height`. The first returned page is
  always page one, and is empty when nothing fit beside the header; a
  document with no sections gets no pages at all.
  """
  pages: list[PrintPage] = []
  page = _OpenPage(first_column_height)

  def close_page() -> None:
    nonlocal page
    # An empty page is kept only as page one: the header still owns it.
    if not page.is_empty() or not pages:
      pages.append(page.close())
    page = _OpenPage(column_height)

  for index, height in enumerate(section_heights):
    section = MeasuredSection(index, height)
    if section.height > column_height:
      close_page()
      pages.append(WidePage(section.index))
      continue
    if not page.try_place(section):
      close_page()
      if not page.try_place(section):
        raise ValueError(
          f'section {section.index} is {section.height}pt, no taller than a '
          f'{column_height}pt column, yet does not fit an empty page'
        )
  if not page.is_empty():
    close_page()
  return pages
