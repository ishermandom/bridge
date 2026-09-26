# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Pack top-level sections onto explicit printed pages.

The print design treats a section as an atom: it renders whole on one page,
ideally within a single column, and two columns exist so that short sections can
sit side by side. WeasyPrint cannot be told this in CSS (spec.md
#section-packing carries the why), so the renderer packs sections itself. The
sections it packs are the `<section>` elements directly inside the template's
`<main>`: the table of contents, then one per top-level heading, as pandoc's
`--section-divs` writes them.

- **Flatten**: each section's nested `<section>` elements give way to their
  contents, leaving a flat run of blocks, which WeasyPrint's columns balance
  well.
- **Measure**: a probe render lays every section out at column width, one per
  very tall page, and the header block (the title lines) at full width;
  `pdftotext` reads back each page's used height.
- **Pack**: a greedy pass in document order fills page one's shortened columns,
  then full pages, column by column. A section taller than a full column gets a
  page of its own, its heading spanning the page and its body flowing in two
  columns beneath — and onto further pages when even that page cannot hold it.
  As each page closes, its sections are rebalanced between the two columns, so
  the two come out as near the same height as reading order allows.
- **Rewrite**: the flat run of sections becomes explicit page and column boxes
  that WeasyPrint lays out exactly as written. The screen rendering keeps the
  original flat HTML.

Rewriting moves elements around a parsed document rather than splicing markup:
`_parse_html` reads the HTML with WeasyPrint's own parser and `_document_html`
writes the tree back out, so the packer works on the document WeasyPrint will
lay out.

The page geometry mirrors the print rules in `notes.css`, which owns the values.
"""

import copy
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from xml.etree.ElementTree import Comment, Element, SubElement, tostring

import tinyhtml5
import weasyprint

from system_notes import pdf_inspection

# The letter page's content height under notes.css margins (0.6in top, 0.75in
# bottom), in points.
PAGE_CONTENT_HEIGHT = (11 - 0.6 - 0.75) * 72

# The id pandoc gives the endnotes it writes for footnotes.
FOOTNOTES_ID = 'footnotes'

# A parsed document carries no doctype, so `_document_html` puts one back: the
# packed copy is the same HTML5 document pandoc wrote, with only its sections
# moved.
DOCTYPE = '<!DOCTYPE html>\n'

# Overrides appended for the measuring render:
#
# - Pages tall enough that nothing fragments, vertical margins of zero so the
#   running margin boxes vanish, and the real horizontal margins so the header
#   keeps its true width.
# - Each section on a page of its own, at the print columns' width.
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
#   section measured short could overflow its column. A sentinel also opens
#   `<main>`, so the header above the sections measures to its true bottom too.
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
main > section {
  width: 3.5in;
  break-before: page;
}
main::before, main > section::after {
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
# on it by this index.
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
class ProbeHeights:
  """What the probe render measured.

  `height_above_sections` is the room on page one taken by the title block above
  the first section. Page one's columns get what remains. `section_heights`
  gives each section's own height, in document order.
  """

  height_above_sections: Points
  section_heights: tuple[Points, ...]


@dataclass(frozen=True)
class PagedDocument:
  """The print-ready HTML and the page plan behind it.

  `pages` is empty when the document has no sections and the HTML came back
  unchanged.
  """

  html: str
  pages: tuple[PrintPage, ...]


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


def _parse_html(html: str) -> Element:
  """Parse a whole HTML document, returning its `<html>` element.

  The parser prefixes every tag name with its namespace by default, which the
  HTML serializer does not recognize: it escapes an embedded stylesheet and
  writes `<br>` as a pair of tags. Plain names keep the round trip in HTML.
  """
  return tinyhtml5.parse(html, namespace_html_elements=False)


def _element_html(element: Element) -> str:
  """One element's own markup, without the text that follows it."""
  markup = tostring(element, encoding='unicode', method='html')
  return markup.removesuffix(element.tail or '')


def _document_html(document: Element) -> str:
  """A whole parsed document's markup, doctype and all."""
  return DOCTYPE + _element_html(document)


def _is_top_level_section(element: Element) -> bool:
  """Whether an element of `<main>` is a section to pack whole.

  A top-level section opens with an h2, whether it is the table of contents or a
  section of the notes. A `<section>` opening with anything else holds a
  subsection cut off from its top-level section.
  """
  return (
    element.tag == 'section' and len(element) > 0 and element[0].tag == 'h2'
  )


def _is_comment(element: Element) -> bool:
  """Whether `element` is an HTML comment.

  The parser keeps each comment as an element whose tag is ElementTree's
  `Comment` factory rather than a name.
  """
  # Widened to `object` to work around inaccurate upstream types. typeshed, the
  # standard library's type stubs, which mypy bundles and a project cannot
  # override, declares every element reached through a tree to have a string
  # tag, even though a comment's tag is the `Comment` factory. Compared as a
  # string, the tag would look like it could never be the factory, and mypy
  # would reject the check.
  tag: object = element.tag
  return tag is Comment


def _reject_stranded_content(main: Element) -> None:
  """Fail the render if anything in `<main>` stands outside every section.

  Print moves only the top-level sections onto pages, so anything else in
  `<main>` would print after them, out of reading order. Comments render as
  nothing, so they may stand anywhere. See print_layout_test.py's
  `test_a_heading_inside_a_fenced_div_strands_what_follows` and
  `test_a_stray_closing_tag_strands_what_follows` for the repro cases.
  """
  texts = (main.text, *(child.tail for child in main))
  strays = [text.strip() for text in texts if text and text.strip()]
  strays += [
    _element_html(child)
    for child in main
    if not _is_comment(child) and not _is_top_level_section(child)
  ]
  if strays:
    raise ValueError(
      'content in <main> stands outside every top-level section, where print '
      'would move it out of reading order; the usual causes are a top-level '
      'heading inside a fenced div and a stray closing tag in raw HTML. '
      f'Near: {strays[0][:80]!r}'
    )


def _unwrap(parent: Element, index: int) -> int:
  """Replace `parent[index]` with its own children, keeping every bit of text.

  Returns how many children took its place.
  """
  child = parent[index]
  # The elements inside the child, which take its place.
  grandchildren = list(child)
  # The child can border text in two places, and unwrapping keeps both in
  # reading order. This markup:
  #
  #     <p>a</p><section>b<h3>c</h3></section>d
  #
  # becomes:
  #
  #     <p>a</p>b<h3>c</h3>d
  #
  # `b` sits inside the child, ahead of its first element: ElementTree keeps it
  # as the child's `text`. It moves onto the tail of the element before the
  # child, or onto the parent's own `text` when the child comes first. `d`
  # follows the child: it is the child's `tail`. It moves onto the tail of the
  # child's last element, or, in a child with no elements, right after `b`.
  if grandchildren:
    last = grandchildren[-1]
    last.tail = (last.tail or '') + (child.tail or '')
    leading = child.text or ''
  else:
    leading = (child.text or '') + (child.tail or '')
  if index == 0:
    parent.text = (parent.text or '') + leading
  else:
    previous = parent[index - 1]
    previous.tail = (previous.tail or '') + leading
  del parent[index]
  parent[index:index] = grandchildren
  return len(grandchildren)


def _flatten_subsections(element: Element) -> None:
  """Replace every `<section>` inside `element` with its own children.

  pandoc nests a `<section>` for each subheading, and WeasyPrint balances a wide
  section's two columns badly when the body sits inside such a box: one column
  runs to the foot of the page while the other stays short. So the print copy
  keeps each top-level section a flat run of blocks. An unwrapped section's id
  moves onto the heading that opens it, where links and page references still
  find it.
  """
  # TODO: an author's fenced div that opens with a heading also arrives as a
  # <section>, so unwrapping it drops the div's classes from the print copy.
  # This Markdown, for example:
  #
  #     ::: note
  #     ## Aside
  #
  #     Text.
  #     :::
  #
  # arrives as `<section id="aside" class="level3 note">`, and the print copy
  # keeps only its contents: `note` is gone. Keep the classes if the stylesheet
  # ever styles one.
  index = 0
  while index < len(element):
    child = element[index]
    _flatten_subsections(child)
    if child.tag != 'section':
      index += 1
      continue
    section_id = child.get('id')
    if section_id and len(child):
      child[0].set('id', section_id)
    index += _unwrap(element, index)


def _widened(section: Element) -> Element:
  """A wide section: heading across the page, body in two columns beneath.

  Every top-level section opens with its h2 heading. The heading's later
  siblings move into a `wide-body` div inside the section.
  """
  body = Element('div', {'class': 'wide-body'})
  body.extend(section[1:])
  del section[1:]
  section.append(body)
  return section


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


def _rewrite_into_pages(
  main: Element, sections: Sequence[Element], pages: Sequence[PrintPage]
) -> None:
  """Put the packed pages where the top-level sections stood in `<main>`."""
  insertion_point = list(main).index(sections[0])
  for section in sections:
    main.remove(section)
    # _reject_stranded_content proved that nothing but whitespace stood between
    # the sections, and no column has any use for that whitespace.
    section.tail = None
  for offset, page in enumerate(pages):
    main.insert(
      insertion_point + offset,
      _page_element(page, sections, is_first=offset == 0),
    )


def _measure(document: Element, section_count: int) -> ProbeHeights:
  """Render the probe and read back the header and per-section heights."""
  probe = copy.deepcopy(document)
  head = probe.find('head')
  if head is None:
    raise ValueError('the document to measure has no <head> for the overrides')
  SubElement(head, 'style').text = PROBE_STYLESHEET
  with tempfile.TemporaryDirectory() as directory:
    pdf = Path(directory) / 'probe.pdf'
    weasyprint.HTML(string=_document_html(probe)).write_pdf(str(pdf))
    heights = pdf_inspection.page_text_heights(pdf)
  if len(heights) != section_count + 1:
    raise ValueError(
      f'the measuring render made {len(heights)} pages for '
      f'{section_count} sections; expected one per section plus the header. '
      'The likely cause is a section taller than the probe page, which '
      'fragments onto a second one'
    )
  return ProbeHeights(heights[0], tuple(heights[1:]))


def paged_document(
  html: str,
  measure: Callable[[Element, int], ProbeHeights] = _measure,
) -> PagedDocument:
  """Rewrite the HTML's sections into explicitly packed printed pages.

  A document with no sections comes back unchanged, with an empty plan; one
  without the template's `<main>` fails. `measure` reports the heights the
  packing works from, given the parsed document and its section count. It
  defaults to the probe render; the parameter exists so that tests can supply
  chosen heights and skip rendering.
  """
  document = _parse_html(html)
  if document.find(f'.//*[@id="{FOOTNOTES_ID}"]') is not None:
    raise NotImplementedError(
      'the document has footnotes, whose endnotes pandoc writes as a section '
      'after the notes; the packer does not place them yet (tasks.md '
      '#pack-footnotes)'
    )
  main = document.find('.//main')
  if main is None:
    raise ValueError(
      'the document has no <main>, where the template puts the notes, so the '
      'packer cannot find their sections'
    )
  sections = [child for child in main if _is_top_level_section(child)]
  if not sections:
    return PagedDocument(_document_html(document), ())
  _reject_stranded_content(main)
  for section in sections:
    _flatten_subsections(section)
  measured = measure(document, len(sections))
  pages = pack(
    section_heights=measured.section_heights,
    first_column_height=PAGE_CONTENT_HEIGHT - measured.height_above_sections,
    column_height=PAGE_CONTENT_HEIGHT,
  )
  _rewrite_into_pages(main, sections, pages)
  return PagedDocument(_document_html(document), tuple(pages))
