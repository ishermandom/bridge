# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""The section packer and the page rewrite, on hand-built inputs."""

from collections.abc import Sequence
from xml.etree.ElementTree import Element

import pytest

from system_notes import print_layout
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

SECTION_A = '<div class="section"><h1 id="a">A</h1><p>x</p></div>'
# Nests an author div, and the <section> pandoc writes for any div that opens
# with a heading.
SECTION_B = (
  '<div class="section"><h1 id="b">B</h1>'
  '<div class="note"><section><p>nested</p></section></div></div>'
)
DOCUMENT = (
  '<body><p>intro</p>'
  f'<div class="sections">\n{SECTION_A}\n{SECTION_B}\n</div>'
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


def test_packed_columns_become_column_boxes() -> None:
  paged = _paged(DOCUMENT, [ONE_PER_COLUMN, ONE_PER_COLUMN])

  assert paged.pages == (ColumnPage(first_column=(0,), second_column=(1,)),)
  # Parsing supplies the <html> and <head> the fragment left implicit, and
  # serializing puts the doctype back.
  assert paged.html == (
    '<!DOCTYPE html>\n<html><head></head><body><p>intro</p>'
    '<div class="print-page">'
    f'<div class="print-column first">{SECTION_A}</div>'
    f'<div class="print-column second">{SECTION_B}</div>'
    '</div>'
    '<p>after</p></body></html>'
  )


def test_a_document_without_sections_comes_back_unchanged() -> None:
  paged = _paged('<body><p>prose</p></body>')

  assert paged.pages == ()
  assert paged.html == (
    '<!DOCTYPE html>\n<html><head></head><body><p>prose</p></body></html>'
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
    f'<div class="section"><h1 id="s{index}">S</h1></div>' for index in range(3)
  )
  paged = _paged(
    f'<div class="sections">{sections}</div>', [ONE_PER_COLUMN] * 3
  )

  assert len(paged.pages) == 2
  assert paged.html.count('<div class="print-page">') == 1
  assert paged.html.count('<div class="print-page fresh">') == 1


def test_a_wide_section_keeps_its_heading_above_its_columns() -> None:
  paged = _paged(
    f'<div class="sections">{SECTION_A}</div>', [TALLER_THAN_A_COLUMN]
  )

  # Page one stays with the header, empty, and the wide section follows it.
  assert paged.pages == (
    ColumnPage(first_column=(), second_column=()),
    WidePage(section=0),
  )
  assert (
    '<div class="print-page fresh">'
    '<div class="section"><h1 id="a">A</h1>'
    '<div class="wide-body"><p>x</p></div></div>'
    '</div>'
  ) in paged.html


TOC = '<section id="TOC"><h2 id="toc-title">Contents</h2><ul></ul></section>'
TABLE_OF_CONTENTS_DOCUMENT = (
  f'<body>{TOC}<blockquote>keep</blockquote>'
  f'<div class="sections">{SECTION_A}</div></body>'
)


def test_the_table_of_contents_becomes_the_first_atom() -> None:
  paged = _paged(TABLE_OF_CONTENTS_DOCUMENT, [ONE_PER_COLUMN, ONE_PER_COLUMN])

  assert (
    f'<div class="print-column first"><div class="section">{TOC}</div></div>'
    f'<div class="print-column second">{SECTION_A}</div>'
  ) in paged.html


def test_content_after_the_table_of_contents_stays_in_place() -> None:
  paged = _paged(TABLE_OF_CONTENTS_DOCUMENT, [ONE_PER_COLUMN, ONE_PER_COLUMN])

  assert paged.html.startswith(
    '<!DOCTYPE html>\n<html><head></head><body><blockquote>keep</blockquote>'
    '<div class="print-page">'
  )


def test_a_wide_atom_may_open_with_the_table_of_contents_title() -> None:
  paged = _paged(
    TABLE_OF_CONTENTS_DOCUMENT, [TALLER_THAN_A_COLUMN, ONE_PER_COLUMN]
  )

  # The wide body goes inside the heading's parent: here the table of contents'
  # own <section>, not the atom wrapper.
  assert (
    '<div class="section"><section id="TOC">'
    '<h2 id="toc-title">Contents</h2>'
    '<div class="wide-body"><ul></ul></div></section></div>'
  ) in paged.html


# --- refusals ---


def test_an_empty_wrapper_fails_the_render() -> None:
  # sections.lua writes `class="sections"` only around a run of at least one
  # section, so an empty wrapper means author markup used the same class.
  with pytest.raises(ValueError, match='holds no sections'):
    _paged('<div class="sections"></div>')


def test_content_outside_every_section_fails_the_render() -> None:
  # Author markdown can carry raw HTML, which pandoc passes through unchecked. A
  # stray </div> there closes its section early, so the paragraphs after it land
  # inside the wrapper but outside every section, as <p>stray</p> does here.
  # Print moves only sections onto pages, so those paragraphs would vanish.
  document = (
    '<div class="sections">'
    '<div class="section"><h1 id="a">A</h1></div><p>stray</p>'
    '</div>'
  )
  with pytest.raises(ValueError, match='outside every section'):
    _paged(document)


def test_stray_text_inside_the_wrapper_fails_the_render() -> None:
  # Content outside every section can be bare text rather than an element, and
  # it would vanish from print just as quietly.
  document = (
    '<div class="sections">'
    'stray<div class="section"><h1 id="a">A</h1></div>'
    '</div>'
  )
  with pytest.raises(ValueError, match='outside every section'):
    _paged(document)


def test_a_wide_section_without_a_heading_fails_the_render() -> None:
  with pytest.raises(ValueError, match='heading'):
    _paged(
      '<div class="sections"><div class="section"><p>x</p></div></div>',
      [TALLER_THAN_A_COLUMN],
    )


def test_a_document_with_footnotes_is_refused() -> None:
  # pandoc appends the endnotes after the sections wrapper, where the packer can
  # neither measure nor place them.
  document = (
    '<div class="sections"><div class="section"><h1 id="a">A</h1></div></div>'
    '<section id="footnotes"><ol><li>note</li></ol></section>'
  )
  with pytest.raises(NotImplementedError, match='footnotes'):
    _paged(document)
