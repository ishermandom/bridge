# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""The section packer and the page rewrite, on hand-built inputs."""

import subprocess
import textwrap
from collections.abc import Sequence
from xml.etree.ElementTree import Element

import pytest

from system_notes import print_layout, render_notes
from system_notes.print_layout import (
  ColumnPage,
  PagedDocument,
  Points,
  ProbeHeights,
  WidePage,
)

# --- pack ---

# Heights are in points. Page one's columns run shorter than later pages'
# because the header block owns the top of that page.


def test_two_short_sections_share_page_one_side_by_side() -> None:
  pages = print_layout.pack([30, 30], first_column_height=40, column_height=100)
  assert pages == [ColumnPage(first_column=(0,), second_column=(1,))]


def test_overflowing_page_one_continues_on_a_full_page() -> None:
  pages = print_layout.pack(
    [30, 30, 30], first_column_height=40, column_height=100
  )
  assert pages == [
    ColumnPage(first_column=(0,), second_column=(1,)),
    ColumnPage(first_column=(2,), second_column=()),
  ]


def test_sections_stack_within_a_column_before_spilling_over() -> None:
  pages = print_layout.pack(
    [30, 50, 40, 70], first_column_height=100, column_height=100
  )
  assert pages == [
    ColumnPage(first_column=(0, 1), second_column=(2,)),
    ColumnPage(first_column=(3,), second_column=()),
  ]


def test_a_page_splits_its_sections_evenly_between_its_columns() -> None:
  # All three fit the first column, where filling alone would leave them.
  pages = print_layout.pack(
    [30, 30, 30], first_column_height=100, column_height=100
  )
  assert pages == [ColumnPage(first_column=(0, 1), second_column=(2,))]


def test_a_page_closed_early_balances_what_it_already_holds() -> None:
  # The 150-tall section claims a page of its own, so nothing more can join page
  # one; its two sections spread rather than leave a column bare.
  pages = print_layout.pack(
    [20, 20, 150], first_column_height=100, column_height=100
  )
  assert pages == [
    ColumnPage(first_column=(0,), second_column=(1,)),
    WidePage(section=2),
  ]


def test_a_section_taller_than_page_one_leaves_it_to_the_header() -> None:
  pages = print_layout.pack([90], first_column_height=40, column_height=100)
  assert pages == [
    ColumnPage(first_column=(), second_column=()),
    ColumnPage(first_column=(0,), second_column=()),
  ]


def test_a_section_taller_than_a_column_gets_a_wide_page() -> None:
  pages = print_layout.pack(
    [30, 150, 30], first_column_height=40, column_height=100
  )
  assert pages == [
    ColumnPage(first_column=(0,), second_column=()),
    WidePage(section=1),
    ColumnPage(first_column=(2,), second_column=()),
  ]


def test_a_section_exactly_a_column_tall_still_fits_it() -> None:
  pages = print_layout.pack([40], first_column_height=40, column_height=100)
  assert pages == [ColumnPage(first_column=(0,), second_column=())]


# --- paged_document ---

# These tests hand `paged_document` chosen heights in place of the measuring
# render, so no WeasyPrint render runs. With nothing measured above the
# sections, page one's columns are as tall as every other page's.
COLUMN = print_layout.PAGE_CONTENT_HEIGHT
# Short enough for a column, but too tall for two to share one.
ONE_PER_COLUMN = COLUMN * 0.6
TALLER_THAN_A_COLUMN = COLUMN * 1.5


def _one_line(markup: str) -> str:
  """`markup` laid out across lines for reading, joined back into one line.

  Tests lay nested markup out one element to a line, indented by depth, so its
  structure shows at a glance. The packer writes no whitespace between tags, so
  each line sheds its indentation and line break. Where whitespace matters to a
  test, the test writes it outside the laid-out markup.
  """
  return ''.join(line.strip() for line in markup.splitlines())


SECTION_A = '<section id="a"><h1>A</h1><p>x</p></section>'
# Nests the <section> pandoc writes for a subheading, which the packer unwraps
# into the top-level section around it.
SECTION_B = _one_line("""
  <section id="b">
    <h1>B</h1>
    <section id="b1"><h2>B1</h2><p>nested</p></section>
  </section>
""")
# The line breaks around the sections stand in for the ones pandoc writes, which
# the packer must not carry into its columns.
DOCUMENT = (
  f'<body><p>intro</p><main>\n{SECTION_A}\n{SECTION_B}\n</main>'
  '<p>after</p></body>'
)


def _paged(
  html: str,
  heights: Sequence[Points] = (),
  height_above_sections: Points = 0,
) -> PagedDocument:
  """`html` packed as though its sections measured `heights`.

  The stand-in measure insists on one height per section, so the heights also
  check how many sections `paged_document` found. A test of a refusal passes no
  heights, since the render fails before anything is measured.
  """

  def measure(_document: Element, section_count: int) -> ProbeHeights:
    assert section_count == len(heights)
    return ProbeHeights(height_above_sections, tuple(heights))

  return print_layout.paged_document(html, measure=measure)


def _html_from_markdown(markdown: str) -> str:
  """`markdown` as pandoc writes it into the notes' template, sections and all.

  The Markdown is dedented first, so a test can write it indented in a
  triple-quoted string. No filters run, so the packer sees exactly the structure
  pandoc gives the Markdown.

  Each call starts a pandoc process, far slower than handing the packer HTML
  directly. Reserve it for tests whose point is what pandoc writes, such as
  reproducing an authoring slip; where hand-built HTML shows the behavior just
  as well, write the HTML instead.
  """
  return subprocess.run(
    [
      'pandoc',
      '--standalone',
      '--template',
      str(render_notes.TEMPLATE),
      '--section-divs',
      '--metadata',
      'title=Notes',
    ],
    input=textwrap.dedent(markdown),
    capture_output=True,
    text=True,
    encoding='utf-8',
    check=True,
  ).stdout


def test_packed_columns_become_column_boxes() -> None:
  paged = _paged(DOCUMENT, [ONE_PER_COLUMN, ONE_PER_COLUMN])

  assert paged.pages == (ColumnPage(first_column=(0,), second_column=(1,)),)
  # Parsing supplies the <html> and <head> the fragment left implicit, and
  # serializing puts the doctype back. The line break opening <main> stays; the
  # ones between the sections are gone.
  page = _one_line(f"""
    <div class="print-page">
      <div class="print-column first">{SECTION_A}</div>
      <div class="print-column second">
        <section id="b">
          <h1>B</h1>
          <h2 id="b1">B1</h2>
          <p>nested</p>
        </section>
      </div>
    </div>
  """)
  assert paged.html == (
    '<!DOCTYPE html>\n<html><head></head><body><p>intro</p><main>\n'
    f'{page}</main><p>after</p></body></html>'
  )


def test_subsections_unwrap_into_their_top_level_section() -> None:
  # WeasyPrint balances a wide section's columns badly around a nested box, so
  # print keeps each section flat. Each subsection's id moves onto its heading.
  section = _one_line("""
    <section id="a">
      <h1>A</h1>
      <section id="a1">
        <h2>A1</h2>
        <p>x</p>
        <section id="a1i"><h3>A1i</h3><p>y</p></section>
      </section>
    </section>
  """)
  paged = _paged(f'<main>{section}</main>', [ONE_PER_COLUMN])

  flattened = _one_line("""
    <section id="a">
      <h1>A</h1>
      <h2 id="a1">A1</h2>
      <p>x</p>
      <h3 id="a1i">A1i</h3>
      <p>y</p>
    </section>
  """)
  assert flattened in paged.html


# pandoc writes only whitespace in these places, but raw HTML in the notes could
# put text there, and print must neither drop nor reorder it.
@pytest.mark.parametrize(
  ('section', 'flattened'),
  [
    pytest.param(
      """
        <section id="a">
          <h1>A</h1>
          <section id="a1">
            lead
            <h2>A1</h2>
          </section>
        </section>
      """,
      """
        <section id="a">
          <h1>A</h1>
          lead
          <h2 id="a1">A1</h2>
        </section>
      """,
      id='before-its-first-element',
    ),
    pytest.param(
      """
        <section id="a">
          <h1>A</h1>
          <section id="a1">
            <h2>A1</h2>
          </section>
          trail
        </section>
      """,
      """
        <section id="a">
          <h1>A</h1>
          <h2 id="a1">A1</h2>
          trail
        </section>
      """,
      id='after-it',
    ),
    pytest.param(
      """
        <section id="a">
          <h1>A</h1>
          <section>only</section>
          after
        </section>
      """,
      """
        <section id="a">
          <h1>A</h1>
          only
          after
        </section>
      """,
      id='with-no-elements',
    ),
    pytest.param(
      """
        <section id="a">
          <h1>A</h1>
          <div>
            before
            <section id="a1">
              inside
              <h2>A1</h2>
            </section>
          </div>
        </section>
      """,
      """
        <section id="a">
          <h1>A</h1>
          <div>
            before
            inside
            <h2 id="a1">A1</h2>
          </div>
        </section>
      """,
      id='first-in-its-parent',
    ),
  ],
)
def test_text_around_an_unwrapped_subsection_keeps_its_place(
  section: str, flattened: str
) -> None:
  paged = _paged(f'<main>{_one_line(section)}</main>', [ONE_PER_COLUMN])

  assert _one_line(flattened) in paged.html


def test_a_document_without_sections_comes_back_unchanged() -> None:
  paged = _paged('<body><main><p>prose</p></main></body>')

  assert paged.pages == ()
  assert paged.html == (
    '<!DOCTYPE html>\n<html><head></head><body><main><p>prose</p></main>'
    '</body></html>'
  )


def test_what_stands_above_the_sections_shortens_page_one() -> None:
  # Below the header, page one keeps too little column for either section.
  paged = _paged(
    DOCUMENT,
    [ONE_PER_COLUMN, ONE_PER_COLUMN],
    height_above_sections=COLUMN - 10,
  )

  assert paged.pages == (
    ColumnPage(first_column=(), second_column=()),
    ColumnPage(first_column=(0,), second_column=(1,)),
  )


def test_every_page_after_the_first_breaks_to_a_fresh_sheet() -> None:
  sections = ''.join(
    f'<section id="s{index}"><h1>S</h1></section>' for index in range(3)
  )
  paged = _paged(f'<main>{sections}</main>', [ONE_PER_COLUMN] * 3)

  assert len(paged.pages) == 2
  assert paged.html.count('<div class="print-page">') == 1
  assert paged.html.count('<div class="print-page fresh">') == 1


def test_a_wide_section_keeps_its_heading_above_its_columns() -> None:
  paged = _paged(f'<main>{SECTION_A}</main>', [TALLER_THAN_A_COLUMN])

  # Page one stays with the header, empty, and the wide section follows it.
  assert paged.pages == (
    ColumnPage(first_column=(), second_column=()),
    WidePage(section=0),
  )
  wide_page = _one_line("""
    <div class="print-page fresh">
      <section id="a">
        <h1>A</h1>
        <div class="wide-body"><p>x</p></div>
      </section>
    </div>
  """)
  assert wide_page in paged.html


TOC = _one_line("""
  <section id="TOC">
    <h2 id="toc-title">Contents</h2>
    <ul></ul>
  </section>
""")
TABLE_OF_CONTENTS_DOCUMENT = f'<main>{TOC}{SECTION_A}</main>'


def test_the_table_of_contents_packs_as_the_first_section() -> None:
  paged = _paged(TABLE_OF_CONTENTS_DOCUMENT, [ONE_PER_COLUMN, ONE_PER_COLUMN])

  columns = _one_line(f"""
    <div class="print-column first">{TOC}</div>
    <div class="print-column second">{SECTION_A}</div>
  """)
  assert columns in paged.html


def test_a_wide_table_of_contents_keeps_its_title_above_its_columns() -> None:
  paged = _paged(
    TABLE_OF_CONTENTS_DOCUMENT, [TALLER_THAN_A_COLUMN, ONE_PER_COLUMN]
  )

  wide_table_of_contents = _one_line("""
    <section id="TOC">
      <h2 id="toc-title">Contents</h2>
      <div class="wide-body"><ul></ul></div>
    </section>
  """)
  assert wide_table_of_contents in paged.html


def test_a_comment_in_main_stays_and_packs_nothing() -> None:
  # Notes may open with a comment of maintainer notes, ahead of every section.
  paged = _paged(f'<main><!-- notes -->{SECTION_A}</main>', [ONE_PER_COLUMN])

  assert paged.pages == (ColumnPage(first_column=(0,), second_column=()),)
  assert '<!-- notes -->' in paged.html


# --- refusals ---


def test_a_heading_inside_a_fenced_div_strands_what_follows() -> None:
  # pandoc ends the heading's section where the div ends, so the subsection
  # after the div lands in <main> as a section of its own, cut off from the
  # top-level section it belongs to.
  html = _html_from_markdown("""
    # Openings

    ::: note
    # Defense
    :::

    ## Stayman

    Relay.
  """)
  with pytest.raises(ValueError, match='outside every top-level section'):
    _paged(html)


def test_a_stray_closing_tag_strands_what_follows() -> None:
  # pandoc passes raw HTML through untouched, so a stray </section> closes the
  # section around it early, and the paragraph after it lands in <main>.
  html = _html_from_markdown("""
    # Openings

    Text.

    </section>

    More.
  """)
  with pytest.raises(ValueError, match='outside every top-level section'):
    _paged(html)


def test_a_document_without_main_fails_the_render() -> None:
  # The template always writes a <main>, so a document without one means the
  # template changed underneath the packer.
  with pytest.raises(ValueError, match='no <main>'):
    _paged('<body><p>prose</p></body>')


def test_stray_text_in_main_fails_the_render() -> None:
  # Content outside every section can be bare text rather than an element, and
  # it would print out of order just as quietly.
  with pytest.raises(ValueError, match='outside every top-level section'):
    _paged(f'<main>stray{SECTION_A}</main>')


def test_a_document_with_footnotes_is_refused() -> None:
  # pandoc writes the endnotes as one more section after the notes, which the
  # packer does not place yet.
  document = _one_line(f"""
    <main>
      {SECTION_A}
      <section id="footnotes"><ol><li>note</li></ol></section>
    </main>
  """)
  with pytest.raises(NotImplementedError, match='footnotes'):
    _paged(document)
