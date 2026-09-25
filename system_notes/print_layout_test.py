# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""The section packer and the page rewrite, on hand-built inputs."""

from collections.abc import Sequence

import pytest

from system_notes import print_layout
from system_notes.print_layout import ColumnPage, PrintPage, WidePage

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


# --- finding the section run ---

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


def _find_run(html: str) -> print_layout.SectionRun | None:
  """The run of sections `html` holds, once parsed."""
  return print_layout.find_section_run(print_layout.parse_html(html))


def test_the_section_run_holds_the_wrapper_and_its_sections() -> None:
  run = _find_run(DOCUMENT)

  assert run is not None
  assert [print_layout.element_html(section) for section in run.sections] == [
    SECTION_A,
    SECTION_B,
  ]
  assert run.wrapper.get('class') == 'sections'
  assert run.parent.tag == 'body'


def test_a_document_without_sections_has_no_run() -> None:
  assert _find_run('<body><p>prose</p></body>') is None


def test_an_empty_wrapper_fails_the_render() -> None:
  # sections.lua writes `class="sections"` only around a run of at least one
  # section, so an empty wrapper means author markup used the same class.
  with pytest.raises(ValueError, match='holds no sections'):
    _find_run('<div class="sections"></div>')


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
    _find_run(document)


def test_stray_text_inside_the_wrapper_fails_the_render() -> None:
  # Content outside every section can be bare text rather than an element, and
  # it would vanish from print just as quietly.
  document = (
    '<div class="sections">'
    'stray<div class="section"><h1 id="a">A</h1></div>'
    '</div>'
  )
  with pytest.raises(ValueError, match='outside every section'):
    _find_run(document)


# --- the page rewrite ---


def _packed_html(html: str, pages: Sequence[PrintPage]) -> str:
  """`html` with its run of sections rewritten onto `pages`."""
  document = print_layout.parse_html(html)
  run = print_layout.find_section_run(document)
  assert run is not None
  print_layout.rewrite_into_pages(run, pages)
  return print_layout.document_html(document)


def test_packed_columns_become_column_boxes() -> None:
  html = _packed_html(
    DOCUMENT, [ColumnPage(first_column=(0,), second_column=(1,))]
  )

  # Parsing supplies the <html> and <head> the fragment left implicit, and
  # serializing puts the doctype back.
  assert html == (
    '<!DOCTYPE html>\n<html><head></head><body><p>intro</p>'
    '<div class="print-page">'
    f'<div class="print-column first">{SECTION_A}</div>'
    f'<div class="print-column second">{SECTION_B}</div>'
    '</div>'
    '<p>after</p></body></html>'
  )


def test_every_page_after_the_first_breaks_to_a_fresh_sheet() -> None:
  html = _packed_html(
    DOCUMENT,
    [
      ColumnPage(first_column=(0,), second_column=()),
      ColumnPage(first_column=(1,), second_column=()),
    ],
  )
  assert html.count('<div class="print-page">') == 1
  assert html.count('<div class="print-page fresh">') == 1


def test_a_wide_section_keeps_its_heading_above_its_columns() -> None:
  html = _packed_html(
    '<div class="sections">'
    '<div class="section"><h1 id="a">A</h1><p>x</p></div>'
    '</div>',
    [WidePage(section=0)],
  )
  assert (
    '<div class="print-page">'
    '<div class="section"><h1 id="a">A</h1>'
    '<div class="wide-body"><p>x</p></div></div>'
    '</div>'
  ) in html


def test_a_wide_section_without_a_heading_fails_the_render() -> None:
  with pytest.raises(ValueError, match='heading'):
    _packed_html(
      '<div class="sections"><div class="section"><p>x</p></div></div>',
      [WidePage(section=0)],
    )
