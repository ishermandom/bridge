# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for laying a transcript's blocks out as plain text and a web page."""

import pytest

from session_analysis.unreviewed.transcript_layout import (
  Alignment,
  Block,
  Emphasis,
  Emphasized,
  FullWidthRow,
  Link,
  LinkList,
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


def test_plain_text_keeps_the_cells_of_a_table_allowing_notes() -> None:
  table = Table(
    alignments=(Alignment.LEFT, Alignment.LEFT, Alignment.LEFT),
    rows=(('#5', '', 'MP=6'), ('#6', '1H', 'MP=2')),
    allows_notes_between_rows=True,
  )

  assert list(as_plain_text([table])) == ['#5\t\tMP=6', '#6\t1H\tMP=2']


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


def test_the_page_keeps_a_cell_s_indent() -> None:
  table = Table(alignments=(Alignment.LEFT,), rows=(('  75.00%',),))

  page = as_web_page('Monday Pairs', [[table]])

  # Non-breaking, since the cells' style drops ordinary spaces at their start.
  indent = '\N{NO-BREAK SPACE}' * 2
  assert f'>{indent}75.00%</td>' in page


def test_cells_fold_a_line_break_in_their_markup_into_a_space() -> None:
  table = Table(alignments=(Alignment.LEFT,), rows=(('1C 1H 1NT',),))

  page = as_web_page('Monday Pairs', [[table]])

  # A mail program quoting the page in a reply may break the markup's lines
  # inside a cell. `nowrap` reads such a break as a space; `pre` would show it.
  assert 'white-space: nowrap' in page
  assert 'white-space: pre' not in page


def test_a_table_allowing_notes_is_set_as_lines_on_the_page() -> None:
  table = Table(
    alignments=(Alignment.LEFT, Alignment.LEFT),
    rows=(('#5', '1C'), ('#6', '1H')),
    allows_notes_between_rows=True,
  )

  page = as_web_page('Monday Pairs', [[table]])

  # A line apiece, so that an email editor can open a new line between two.
  assert '>1C</span>\N{HAIR SPACE}</div>' in page
  assert '>1H</span>\N{HAIR SPACE}</div>' in page
  assert '<table' not in page


def test_a_line_separates_the_values_after_its_first_cell() -> None:
  table = Table(
    alignments=(Alignment.LEFT, Alignment.LEFT, Alignment.LEFT),
    rows=(('#5', '1C', 'MP=4'),),
    allows_notes_between_rows=True,
  )

  page = as_web_page('Monday Pairs', [[table]])

  # The first cell names the line, so only a gap follows it.
  gap = '\N{NO-BREAK SPACE}' * 3 + ' '
  separator = (
    '\N{NO-BREAK SPACE}' * 2
    + '<span style="color: #767676">\N{MIDDLE DOT}</span>\N{NO-BREAK SPACE} '
  )
  assert f'>#5</span>{gap}<span' in page
  assert '>1C</span>' in page
  assert f'>{separator}MP=4</span>' in page


def test_each_column_on_a_line_is_as_wide_as_arial_draws_its_widest() -> None:
  table = Table(
    alignments=(Alignment.LEFT, Alignment.LEFT),
    rows=(('#9', '1C'), ('#10', '1H')),
    allows_notes_between_rows=True,
  )

  page = as_web_page('Monday Pairs', [[table]])

  # Each character of `#10` is 0.556 em wide in Arial, and the estimate runs 3%
  # over, rounded up: 1.72 em, so that `1C` starts where `1H` does.
  assert 'min-width: 1.72em">#9</span>' in page
  assert 'min-width: 1.72em">#10</span>' in page


def test_a_character_of_unknown_width_counts_as_an_em() -> None:
  table = Table(
    alignments=(Alignment.LEFT, Alignment.LEFT),
    rows=(('\N{BLACK SPADE SUIT}', '1C'),),
    allows_notes_between_rows=True,
  )

  page = as_web_page('Monday Pairs', [[table]])

  # Wider than any character with a known width, and 3% over.
  assert 'min-width: 1.03em">\N{BLACK SPADE SUIT}</span>' in page


def test_a_cell_on_a_line_never_wraps() -> None:
  table = Table(
    alignments=(Alignment.LEFT, Alignment.LEFT),
    rows=(('#5', '3.5 mps'),),
    allows_notes_between_rows=True,
  )

  page = as_web_page('Monday Pairs', [[table]])

  # A cell drawn wider than estimated widens its line, where Gmail would break
  # it mid-word.
  assert 'white-space: nowrap; min-width: ' in page


def test_lines_set_on_the_page_are_spaced_apart() -> None:
  table = Table(
    alignments=(Alignment.LEFT,),
    rows=(('#5',), ('#6',)),
    allows_notes_between_rows=True,
  )

  page = as_web_page('Monday Pairs', [[table]])

  # Set on each line, so that a line copied alone keeps its spacing.
  assert page.count('line-height: 1.4">') == 2


def test_an_empty_cell_keeps_its_column_s_width_on_a_line() -> None:
  table = Table(
    alignments=(Alignment.LEFT, Alignment.LEFT, Alignment.LEFT),
    rows=(('#5', '1C', 'MP=4'), ('#6', '', 'MP=4.5')),
    allows_notes_between_rows=True,
  )

  page = as_web_page('Monday Pairs', [[table]])

  # As wide as `1C`, so that `MP=4.5` starts where `MP=4` does.
  assert 'min-width: 1.32em"></span>' in page


def test_a_cell_with_no_text_opens_with_no_separator() -> None:
  table = Table(
    alignments=(Alignment.LEFT,) * 4,
    rows=(('#6', '1C', Emphasized('', Emphasis.MUTED), 'MP=4.5'),),
    allows_notes_between_rows=True,
  )

  page = as_web_page('Monday Pairs', [[table]])

  # The third cell holds a piece, but no text, so only `MP=4.5` is set off.
  assert page.count('\N{MIDDLE DOT}') == 1


def test_a_held_second_column_keeps_its_width_and_leads_on_with_dots() -> None:
  table = Table(
    alignments=(Alignment.LEFT,) * 3,
    rows=(('#5', '1C', 'lead 2oS'),),
    allows_notes_between_rows=True,
    second_column_width=12,
  )

  page = as_web_page('Monday Pairs', [[table]])

  assert 'width: 12em">' in page
  assert 'border-bottom: 1.5px dotted' in page


def test_a_held_cell_s_pieces_share_a_styled_wrapper() -> None:
  table = Table(
    alignments=(Alignment.LEFT,) * 2,
    rows=(('#5', ('1C ', Emphasized('3NS+3', Emphasis.STRONG))),),
    allows_notes_between_rows=True,
    second_column_width=12,
  )

  page = as_web_page('Monday Pairs', [[table]])

  # One flex item, so that the space before the contract stays, and styled, so
  # that a copy pasted into Gmail keeps it.
  assert '<span style="flex: 0 1 auto">1C <span' in page


def test_the_column_after_a_held_one_opens_with_no_separator() -> None:
  table = Table(
    alignments=(Alignment.LEFT,) * 4,
    rows=(('#5', '1C', 'lead 2oS', 'MP=4'),),
    allows_notes_between_rows=True,
    second_column_width=12,
  )

  page = as_web_page('Monday Pairs', [[table]])

  # The dots and a gap set the lead off; a separator sets off what follows it.
  gap = '\N{NO-BREAK SPACE}' * 3 + ' '
  assert f'</span></span>{gap}<span' in page
  assert '>lead 2oS</span>' in page
  assert page.count('\N{MIDDLE DOT}') == 1


def test_a_line_ends_on_a_character_with_no_emphasis() -> None:
  table = Table(
    alignments=(Alignment.LEFT, Alignment.LEFT),
    rows=(('#5', Emphasized('DD+1', Emphasis.GOOD)),),
    allows_notes_between_rows=True,
  )

  page = as_web_page('Monday Pairs', [[table]])

  # An editor gives what is typed after Enter the style of the character before
  # the caret, so a note typed under this line is plain rather than blue.
  assert '>DD+1</span></span>\N{HAIR SPACE}</div>' in page


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


# --- non-breaking spaces ---


def test_plain_text_writes_a_non_breaking_space_as_an_ordinary_one() -> None:
  table = Table(
    alignments=(Alignment.LEFT, Alignment.LEFT),
    rows=(('#5', '6\N{NO-BREAK SPACE}mps'),),
  )

  assert list(as_plain_text([table])) == ['#5\t6 mps']


def test_the_page_keeps_a_non_breaking_space() -> None:
  paragraph = Paragraph(('6\N{NO-BREAK SPACE}mps',))

  page = as_web_page('Monday Pairs', [[paragraph]])

  # So that a narrow screen never ends a line between the two words.
  assert '>6\N{NO-BREAK SPACE}mps</p>' in page


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


# --- emphasis ---


def test_emphasized_text_reads_as_written_in_plain_text() -> None:
  paragraph = Paragraph((('MP=', Emphasized('4.5', Emphasis.STRONG)),))

  assert list(as_plain_text([paragraph])) == ['MP=4.5']


def test_a_cell_s_run_of_pieces_is_one_value_in_plain_text() -> None:
  table = Table(
    alignments=(Alignment.LEFT, Alignment.LEFT),
    rows=(('#5', ('1C ', Emphasized('3NS+3', Emphasis.STRONG))),),
  )

  # No tab inside the run, so the spreadsheet keeps it to one cell.
  assert list(as_plain_text([table])) == ['#5\t1C 3NS+3']


@pytest.mark.parametrize(
  ('emphasis', 'style'),
  [
    (Emphasis.MUTED, 'color: #767676'),
    (Emphasis.STRONG, 'font-weight: bold; white-space: nowrap'),
    (Emphasis.GOOD, 'color: #2d74d8'),
    (Emphasis.BAD, 'color: #d73c36'),
  ],
)
def test_the_page_draws_each_emphasis_in_its_style(
  emphasis: Emphasis, style: str
) -> None:
  paragraph = Paragraph((('#5 ', Emphasized('DD+1', emphasis)),))

  page = as_web_page('Monday Pairs', [[paragraph]])

  assert f'>#5 <span style="{style}">DD+1</span></p>' in page


def test_the_page_draws_each_piece_of_a_table_cell_s_run() -> None:
  table = Table(
    alignments=(Alignment.LEFT,),
    rows=((('1C ', Emphasized('3NS+3', Emphasis.STRONG)),),),
  )

  page = as_web_page('Monday Pairs', [[table]])

  assert (
    'left">1C <span style="font-weight: bold; white-space: nowrap">3NS+3'
    '</span></td>'
  ) in page


# --- links ---


def test_plain_text_writes_a_link_s_address_on_a_line_under_it() -> None:
  paragraph = Paragraph(
    (
      ('Recap: ', Link('ACBL', 'https://example.com/recap')),
      'TOP=8',
    )
  )

  assert list(as_plain_text([paragraph])) == [
    'Recap: ACBL',
    '- https://example.com/recap',
    'TOP=8',
  ]


def test_plain_text_writes_a_row_s_link_under_the_row() -> None:
  table = Table(
    alignments=(Alignment.LEFT, Alignment.LEFT),
    rows=(
      (Link('#5', 'https://example.com/5'), '1C'),
      ('#6', '1H'),
    ),
  )

  # The cell keeps the link's text, so the row's columns stay where they were.
  assert list(as_plain_text([table])) == [
    '#5\t1C',
    '- https://example.com/5',
    '#6\t1H',
  ]


def test_the_page_makes_a_link_s_text_the_link() -> None:
  paragraph = Paragraph((('Recap: ', Link('ACBL', 'https://example.com/')),))

  page = as_web_page('Monday Pairs', [[paragraph]])

  assert '>Recap: <a href="https://example.com/">ACBL</a></p>' in page


def test_the_page_links_a_cell_of_a_table_set_as_lines() -> None:
  table = Table(
    alignments=(Alignment.LEFT, Alignment.LEFT),
    rows=((Link('#5', 'https://example.com/5'), '1C'),),
    allows_notes_between_rows=True,
  )

  page = as_web_page('Monday Pairs', [[table]])

  gap = '\N{NO-BREAK SPACE}' * 3 + ' '
  assert f'><a href="https://example.com/5">#5</a></span>{gap}<span' in page


def test_the_page_links_a_cell_of_a_table() -> None:
  table = Table(
    alignments=(Alignment.LEFT,),
    rows=((Link('#5', 'https://example.com/5'),),),
  )

  page = as_web_page('Monday Pairs', [[table]])

  assert 'left"><a href="https://example.com/5">#5</a></td>' in page


def test_plain_text_writes_a_link_list_as_its_addresses_alone() -> None:
  links = LinkList(
    (
      Link('ACBL', 'https://acbl.example.com/'),
      Link('club', 'https://club.example.com/'),
    )
  )
  paragraph = Paragraph((('Recaps: ', links),))

  # The space that set the list off goes with it, rather than trailing.
  assert list(as_plain_text([paragraph])) == [
    'Recaps:',
    '- https://acbl.example.com/',
    '- https://club.example.com/',
  ]


def test_the_page_names_each_link_of_a_list_a_comma_apart() -> None:
  links = LinkList(
    (
      Link('ACBL', 'https://acbl.example.com/'),
      Link('club', 'https://club.example.com/'),
    )
  )
  paragraph = Paragraph((('Recaps: ', links),))

  page = as_web_page('Monday Pairs', [[paragraph]])

  assert (
    '>Recaps: <a href="https://acbl.example.com/">ACBL</a>, '
    '<a href="https://club.example.com/">club</a></p>'
  ) in page


def test_the_page_escapes_a_link_s_address() -> None:
  paragraph = Paragraph(
    ((Link('#5', 'https://example.com/?board=5&dealer=N'),),)
  )

  page = as_web_page('Monday Pairs', [[paragraph]])

  assert 'href="https://example.com/?board=5&amp;dealer=N"' in page


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
