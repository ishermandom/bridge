# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for laying a transcript's blocks out as plain text and a web page."""

from session_analysis.unreviewed.transcript_layout import (
  Alignment,
  Block,
  FullWidthRow,
  Paragraph,
  Placeholder,
  Table,
  as_plain_text,
  as_web_page,
)

# --- plain text ---


def test_a_table_row_separates_its_cells_with_tabs() -> None:
  table = Table(
    alignments=(Alignment.LEFT, Alignment.RIGHT),
    rows=(('#5', 'MP=6'),),
  )

  assert list(as_plain_text([table])) == ['#5\tMP=6']


def test_empty_cells_at_the_end_of_a_row_are_dropped() -> None:
  table = Table(
    alignments=(Alignment.LEFT, Alignment.LEFT, Alignment.LEFT),
    rows=(('#5', '', ''),),
  )

  assert list(as_plain_text([table])) == ['#5']


def test_an_empty_cell_inside_a_row_keeps_its_place() -> None:
  table = Table(
    alignments=(Alignment.LEFT, Alignment.LEFT, Alignment.LEFT),
    rows=(('#5', '', 'DD+1'),),
  )

  # Dropping it would shift every later value into the wrong spreadsheet column.
  assert list(as_plain_text([table])) == ['#5\t\tDD+1']


def test_a_full_width_row_is_its_text_alone() -> None:
  table = Table(
    alignments=(Alignment.LEFT, Alignment.LEFT),
    rows=(('#5', 'MP=6'), FullWidthRow('-')),
  )

  assert list(as_plain_text([table])) == ['#5\tMP=6', '-']


def test_blocks_are_separated_by_a_blank_line() -> None:
  blocks = [Paragraph(('first', 'second')), Paragraph(('third',))]

  assert list(as_plain_text(blocks)) == ['first', 'second', '', 'third']


# --- the web page ---


def test_the_page_aligns_each_cell_as_its_column_says() -> None:
  table = Table(
    alignments=(Alignment.LEFT, Alignment.RIGHT),
    rows=(('1', '7.50'),),
  )

  page = as_web_page('Monday Pairs', [[table]])

  assert 'text-align: left">1</td>' in page
  assert 'text-align: right">7.50</td>' in page


def test_a_full_width_row_spans_every_column() -> None:
  table = Table(
    alignments=(Alignment.LEFT, Alignment.LEFT, Alignment.LEFT),
    rows=(FullWidthRow('-'),),
  )

  assert 'colspan="3"' in as_web_page('Monday Pairs', [[table]])


def test_a_paragraph_keeps_its_lines_apart() -> None:
  page = as_web_page('Monday Pairs', [[Paragraph(('E error =', 'W error ='))]])

  assert '>E error =<br>\nW error =</p>' in page


def test_the_page_escapes_what_it_is_given() -> None:
  page = as_web_page('A & B', [[Paragraph(('1C <2D>',))]])

  assert '<title>A &amp; B</title>' in page
  assert '1C &lt;2D&gt;' in page


def test_the_page_separates_one_document_from_the_next_with_a_rule() -> None:
  page = as_web_page(
    'Transcripts', [[Paragraph(('first',))], [Paragraph(('second',))]]
  )

  assert page.index('first') < page.index('<hr>') < page.index('second')


# --- placeholders ---


def test_a_placeholder_is_bracketed_in_plain_text() -> None:
  paragraph = Paragraph(
    ((Placeholder('place'), ' earning ', Placeholder('points')),)
  )

  assert list(as_plain_text([paragraph])) == ['[place] earning [points]']


def test_a_placeholder_is_drawn_in_red_on_the_page() -> None:
  paragraph = Paragraph((('earning ', Placeholder('points')),))

  page = as_web_page('Monday Pairs', [[paragraph]])

  assert '>earning <span style="color: red">[points]</span></p>' in page


# --- the font ---


def test_the_font_travels_with_every_paragraph_and_cell() -> None:
  blocks: list[Block] = [
    Paragraph(('TOP=8',)),
    Table(alignments=(Alignment.LEFT,), rows=(('#5',),)),
  ]

  page = as_web_page('Monday Pairs', [blocks])

  # Set on each element rather than once for the page, so that a copy of any
  # part of it carries the font into an email.
  font = 'font-family: Calibri, Carlito, Arial, Helvetica, sans-serif'
  assert f'{font}">TOP=8</p>' in page
  assert f'{font}; text-align: left">#5</td>' in page
