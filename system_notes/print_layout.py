# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Pack top-level sections onto explicit printed pages.

The print design treats a section as an atom: it renders whole on one page,
ideally within a single column, and two columns exist so that short sections can
sit side by side. WeasyPrint cannot be told this in CSS (spec.md
#section-packing carries the why), so the renderer packs sections itself:

- **Atomize**: the table of contents moves into the run of sections as its first
  atom, so it packs like a section instead of reflowing across the page.
- **Measure**: a probe render lays every atom out at column width, one per very
  tall page, and the header block (the title lines) at full width; `pdftotext`
  reads back each page's used height.
- **Pack**: a greedy pass in document order fills page one's shortened columns,
  then full pages, column by column. A section taller than a full column gets a
  page of its own, its heading spanning the page and its body flowing in two
  columns beneath — and onto further pages when even that page cannot hold it.
  As each page closes, its sections are rebalanced between the two columns, so
  the two come out as near the same height as reading order allows.
- **Rewrite**: the flat run of section divs becomes explicit page and column
  boxes that WeasyPrint lays out exactly as written. The screen rendering keeps
  the original flat HTML.

Atomizing and rewriting move elements around a parsed document rather than
splice markup: `parse_html` reads the HTML with WeasyPrint's own parser and
`document_html` writes the tree back out, so the packer works on the document
WeasyPrint will lay out.

The page geometry mirrors the print rules in `notes.css`, which owns the values.
"""

import copy
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring

import tinyhtml5
import weasyprint

from system_notes import pdf_inspection

# The letter page's content height under notes.css margins (0.6in top, 0.75in
# bottom), in points.
PAGE_CONTENT_HEIGHT = (11 - 0.6 - 0.75) * 72

# The classes sections.lua writes around the run of sections and around each
# section in it, and the path that finds the run in a parsed document.
SECTIONS_CLASS = 'sections'
SECTION_CLASS = 'section'
SECTIONS_WRAPPER_PATH = f'.//div[@class="{SECTIONS_CLASS}"]'

# The id the HTML template gives the table of contents pandoc's `--toc` fills.
TABLE_OF_CONTENTS_ID = 'TOC'

# A parsed document carries no doctype, so `document_html` puts one back: the
# packed copy is the same HTML5 document pandoc wrote, with only its sections
# moved.
DOCTYPE = '<!DOCTYPE html>\n'

# Overrides appended for the measuring render:
#
# - Pages tall enough that nothing fragments, vertical margins of zero so the
#   running margin boxes vanish, and the real horizontal margins so the header
#   keeps its true width.
# - Each section on a page of its own, at the print columns' width. The rules
#   scope to the wrapper's own children, so an author element that happens to
#   carry the class `section` gets no probe page.
# - A sentinel line after each section, so that a section's height includes the
#   bottom margin of its last block. The probe reads a page's height off its
#   lowest text, and a margin holds no text, but in a real column the next
#   section still starts below that margin:
#
#       …the section's last line of text   <- the probe's lowest text
#       (the last block's bottom margin)   <- room the section still takes
#       x                                  <- the sentinel's line
#
#   With the sentinel, the lowest text sits below the margin. Its own line makes
#   every section measure one line too tall, which is the safe direction: a
#   section measured short could overflow its column. A sentinel also opens the
#   wrapper, so the header and any preamble above the sections measure to their
#   true bottom too.
# - Every page number replaced by `88`, a stand-in at least as wide as any real
#   one. Left alone, a number would show its page in the probe, which has
#   nothing to do with its page on paper. IBM Plex Serif gives every digit the
#   same width, so `88` is exactly as wide as any two-digit page number and
#   wider than any one-digit one. Too wide is the safe direction here too: a
#   stand-in too wide can only wrap a line in the probe that stays whole on
#   paper, so its section measures tall rather than short.
#   `test_no_digit_is_wider_than_the_page_number_stand_in` fails if a new body
#   face makes any digit wider than `8`.
PROBE_STYLESHEET = """
@page {
  size: 8.5in 100in;
  margin: 0 0.6in;
}
.sections > .section {
  width: 3.5in;
  break-before: page;
}
.sections::before, .sections > .section::after {
  content: 'x';
  display: block;
}
#TOC a::after {
  content: '88';
}
a.xref::after {
  content: ' (p. 88)';
}
"""


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


@dataclass(frozen=True)
class SectionRun:
  """The run of top-level sections, and where it sits in the document.

  `wrapper` is the div sections.lua wrote around the whole run, and `parent` the
  element holding that div: the packed pages take the wrapper's place inside
  `parent`. `sections` are the wrapper's own children, in document order.
  """

  parent: Element
  wrapper: Element
  sections: tuple[Element, ...]


@dataclass(frozen=True)
class ProbeHeights:
  """What the probe render measured.

  `height_above_sections` is the room on page one taken by everything above the
  first section: the title block, and any preamble the author wrote. Page one's
  columns get what remains. `section_heights` gives each section's own height,
  in document order.
  """

  height_above_sections: Points
  section_heights: tuple[Points, ...]


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
  always page one, and is empty when nothing fit beside the header; a document
  with no sections gets no pages at all.
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


def parse_html(html: str) -> Element:
  """Parse a whole HTML document, returning its `<html>` element.

  The parser prefixes every tag name with its namespace by default, which the
  HTML serializer does not recognize: it escapes an embedded stylesheet and
  writes `<br>` as a pair of tags. Plain names keep the round trip in HTML.
  """
  return tinyhtml5.parse(html, namespace_html_elements=False)


def element_html(element: Element) -> str:
  """One element's own markup, without the text that follows it."""
  markup = tostring(element, encoding='unicode', method='html')
  return markup.removesuffix(element.tail or '')


def document_html(document: Element) -> str:
  """A whole parsed document's markup, doctype and all."""
  return DOCTYPE + element_html(document)


def _parents(document: Element) -> Mapping[Element, Element]:
  """Every element in the document, mapped to the element holding it.

  A parsed element carries no link back to its parent, so finding one takes this
  map.
  """
  return {child: parent for parent in document.iter() for child in parent}


def _reject_content_outside_sections(wrapper: Element) -> None:
  """Fail the render if anything in the wrapper sits outside every section.

  Only the wrapper's own children count as sections, so an author div classed
  `section` nested inside a section stays part of that section.
  """
  texts = (wrapper.text, *(child.tail for child in wrapper))
  strays = [text.strip() for text in texts if text and text.strip()]
  strays += [
    element_html(child)
    for child in wrapper
    if child.tag != 'div' or child.get('class') != SECTION_CLASS
  ]
  if strays:
    raise ValueError(
      'content inside the sections wrapper sits outside every section, where '
      'print would drop it; the usual cause is a stray closing tag in author '
      f'HTML. Near: {strays[0][:80]!r}'
    )


def find_section_run(document: Element) -> SectionRun | None:
  """Locate the sections wrapper and the sections it holds.

  Returns None when the document has no sections wrapper. Whatever the wrapper
  holds besides sections fails the render: a stray closing tag in author HTML
  leaves content there, which print would otherwise drop without a word.
  """
  wrapper = document.find(SECTIONS_WRAPPER_PATH)
  if wrapper is None:
    return None
  _reject_content_outside_sections(wrapper)
  if not len(wrapper):
    raise ValueError(
      f'a div classed {SECTIONS_CLASS!r} holds no sections; sections.lua '
      'writes that class only around a run of sections, so this div came from '
      'author markup'
    )
  return SectionRun(_parents(document)[wrapper], wrapper, tuple(wrapper))


def _heading_parent(atom: Element) -> Element:
  """The element whose first child is the atom's heading.

  An atom takes one of two shapes. A section of the notes opens with its own h1,
  so the atom itself is the heading's parent. The table of contents atom holds
  the `<section>` pandoc writes for the table, which opens with the h2 title one
  level in:

      <div class="section"><h1>…</h1>…</div>
      <div class="section"><section id="TOC"><h2>…</h2>…</section></div>
  """
  if len(atom) and atom[0].tag == 'h1':
    return atom
  if len(atom) and atom[0].get('id') == TABLE_OF_CONTENTS_ID:
    table_of_contents = atom[0]
    if len(table_of_contents) and table_of_contents[0].tag == 'h2':
      return table_of_contents
  raise ValueError(
    f'wide section does not open with a heading: {element_html(atom)[:100]!r}'
  )


def _widened(atom: Element) -> Element:
  """A wide atom: heading across the page, body in two columns beneath.

  The heading's later siblings move into a `wide-body` div, so the heading's
  parent still closes around them.
  """
  heading_parent = _heading_parent(atom)
  body = Element('div', {'class': 'wide-body'})
  body.extend(heading_parent[1:])
  del heading_parent[1:]
  heading_parent.append(body)
  return atom


def _page_element(
  page: PrintPage, sections: Sequence[Element], is_first: bool
) -> Element:
  """One printed page, as a `print-page` box.

  Every page after the first also carries `fresh`, which breaks to a new sheet
  ahead of the box.
  """
  box = Element(
    'div', {'class': 'print-page' if is_first else 'print-page fresh'}
  )
  if isinstance(page, WidePage):
    box.append(_widened(sections[page.section]))
    return box
  for name, section_indices in (
    ('first', page.first_column),
    ('second', page.second_column),
  ):
    if section_indices:
      column = SubElement(box, 'div', {'class': f'print-column {name}'})
      column.extend(sections[index] for index in section_indices)
  return box


def rewrite_into_pages(
  section_run: SectionRun, pages: Sequence[PrintPage]
) -> None:
  """Put the packed pages where the sections wrapper stood."""
  for section in section_run.sections:
    # find_section_run proved that nothing but whitespace stood between the
    # sections, and no column has any use for that whitespace.
    section.tail = None
  insertion_point = list(section_run.parent).index(section_run.wrapper)
  section_run.parent.remove(section_run.wrapper)
  for offset, page in enumerate(pages):
    section_run.parent.insert(
      insertion_point + offset,
      _page_element(page, section_run.sections, is_first=offset == 0),
    )


def atomize_table_of_contents(document: Element) -> None:
  """Move the table of contents into the sections run as its first atom.

  Packed like a section, the table of contents keeps to a single column instead
  of reflowing across the page. A document without a table of contents, or
  without sections, is left as it stands.
  """
  table_of_contents = document.find(f'.//*[@id="{TABLE_OF_CONTENTS_ID}"]')
  wrapper = document.find(SECTIONS_WRAPPER_PATH)
  if table_of_contents is None or wrapper is None:
    return
  if wrapper in table_of_contents.iter():
    raise ValueError(
      'the sections wrapper sits inside the table of contents, so the table '
      'of contents cannot be moved in beside the sections'
    )
  _parents(document)[table_of_contents].remove(table_of_contents)
  table_of_contents.tail = None
  atom = Element('div', {'class': SECTION_CLASS})
  atom.append(table_of_contents)
  wrapper.insert(0, atom)


def _measure(document: Element, section_count: int) -> ProbeHeights:
  """Render the probe and read back the header and per-section heights."""
  probe = copy.deepcopy(document)
  head = probe.find('head')
  if head is None:
    raise ValueError('the document to measure has no <head> for the overrides')
  SubElement(head, 'style').text = PROBE_STYLESHEET
  with tempfile.TemporaryDirectory() as directory:
    pdf = Path(directory) / 'probe.pdf'
    weasyprint.HTML(string=document_html(probe)).write_pdf(str(pdf))
    heights = pdf_inspection.page_text_heights(pdf)
  if len(heights) != section_count + 1:
    raise ValueError(
      f'the measuring render made {len(heights)} pages for '
      f'{section_count} sections; expected one per section plus the header. '
      'The likely cause is a section taller than the probe page, which '
      'fragments onto a second one'
    )
  return ProbeHeights(heights[0], tuple(heights[1:]))


def paged_document(html: str) -> str:
  """Rewrite the HTML's sections into explicitly packed printed pages.

  A document with no sections comes back unchanged.
  """
  document = parse_html(html)
  atomize_table_of_contents(document)
  section_run = find_section_run(document)
  if section_run is None:
    return document_html(document)
  measured = _measure(document, len(section_run.sections))
  pages = pack(
    section_heights=measured.section_heights,
    first_column_height=PAGE_CONTENT_HEIGHT - measured.height_above_sections,
    column_height=PAGE_CONTENT_HEIGHT,
  )
  rewrite_into_pages(section_run, pages)
  return document_html(document)
