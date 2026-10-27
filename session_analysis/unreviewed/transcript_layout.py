# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Laying a transcript out two ways: as plain text, and as a web page.

A transcript goes two places. Its board lines are pasted into a spreadsheet, and
the whole of it into an email. A spreadsheet splits pasted text into cells at
its tabs, so plain text separates a table's columns with tabs, and its rows
paste one value to a cell.

Tabs line columns up only as far as tab stops allow, in any font: a value ends
somewhere between two stops, and the tab carries the next column to the second.
So a column lines up wherever all its values end between the same two stops,
however wide their characters are drawn — which short values such as numbers
usually do, and runs of words usually do not. Only a real table lines up
whatever its values, so the web page draws one, with each column aligned the way
its values read best. The exception is a table whose rows a reader writes notes
between, which the page sets as lines of text instead.

A transcript is therefore built once, as a short run of blocks, and laid out by
whichever of the two functions here its reader needs.
"""

import dataclasses
import enum
import html
from collections.abc import Iterable, Iterator, Sequence


class Alignment(enum.StrEnum):
  """Where a table column's values sit within it, on the web page."""

  LEFT = 'left'
  CENTER = 'center'
  RIGHT = 'right'


@dataclasses.dataclass(frozen=True)
class Placeholder:
  """Text for the reader to replace, written in square brackets.

  The web page also draws it in red, the color a reader fills it in with, so
  that typing over it keeps the color.
  """

  text: str


@dataclasses.dataclass(frozen=True)
class Link:
  """Text that leads to a web address.

  The web page makes the text itself the link. Plain text has no links, so it
  keeps the text where it stands, as part of what its line says, and gives the
  address a line of its own under the line or row holding it, written as a
  comment is: a dash, then the address.
  """

  text: str
  url: str


@dataclasses.dataclass(frozen=True)
class LinkList:
  """Links named one after another, such as the places a session is published.

  The web page names each in turn, a comma between two, with every name the link
  itself. Plain text leaves the names out and gives each address its comment
  line, as it does for a lone `Link`. A lone link's text is part of what its
  line says, where these names only say where each address leads, and the
  address says that itself.
  """

  links: tuple[Link, ...]


# One piece of a line.
Piece = str | Placeholder | Link | LinkList

# A line of text, whole or in pieces, some of them placeholders or links.
Line = str | tuple[Piece, ...]


@dataclasses.dataclass(frozen=True)
class Paragraph:
  """Lines that belong together, set with no blank line between them."""

  lines: tuple[Line, ...]


@dataclasses.dataclass(frozen=True)
class FullWidthRow:
  """A table row holding one value across every column, such as a blank line."""

  text: str


# What one cell of a table holds.
Cell = str | Link

# A row of cells, one per column, or one value spanning them all.
TableRow = tuple[Cell, ...] | FullWidthRow


@dataclasses.dataclass(frozen=True)
class Table:
  """Rows whose cells line up in columns."""

  # One per column; plain text has no use for them.
  alignments: tuple[Alignment, ...]
  rows: tuple[TableRow, ...]
  # Whether a reader should be able to write notes between its rows on the web
  # page. Most email editors can type into a row of a pasted table but cannot
  # add one, so the page sets such a table's rows as lines of text instead,
  # giving up its lined-up columns. Plain text, where a new line can go
  # anywhere, lays it out like any other table.
  allows_notes_between_rows: bool = False


# What a transcript is built from: runs of lines, and tables.
Block = Paragraph | Table


def as_plain_text(blocks: Sequence[Block]) -> Iterator[str]:
  """The blocks as lines of text, a blank line between one block and the next.

  A table's cells are separated by tabs. Empty cells at the end of a row are
  dropped, since a run of trailing tabs says nothing and pastes as nothing. The
  address of each link follows the line or row holding it, on a line of its own.
  """
  for index, block in enumerate(blocks):
    if index:
      yield ''
    if isinstance(block, Paragraph):
      for line in block.lines:
        yield _line_text(line)
        yield from _link_lines(() if isinstance(line, str) else line)
    else:
      for row in block.rows:
        if isinstance(row, FullWidthRow):
          yield row.text
        else:
          yield '\t'.join(_text_of(cell) for cell in row).rstrip('\t')
          yield from _link_lines(row)


def _line_text(line: Line) -> str:
  """One line as plain text."""
  if isinstance(line, str):
    return line
  # A list of links ending the line is left out, which would otherwise leave the
  # space that set it off trailing with nothing after it.
  return ''.join(_text_of(piece) for piece in line).rstrip()


def _text_of(piece: Piece) -> str:
  """A piece of a line, or a cell, as plain text.

  A placeholder is set in its square brackets, and a link keeps its text, its
  address left for a line below. A list of links leaves out the names.
  """
  if isinstance(piece, Placeholder):
    return f'[{piece.text}]'
  if isinstance(piece, Link):
    return piece.text
  if isinstance(piece, LinkList):
    return ''
  return piece


def _link_lines(pieces: Iterable[Piece]) -> Iterator[str]:
  """A comment line for each link among `pieces`, carrying its address."""
  for piece in pieces:
    if isinstance(piece, Link):
      yield f'- {piece.url}'
    elif isinstance(piece, LinkList):
      yield from (f'- {link.url}' for link in piece.links)


def as_web_page(title: str, documents: Sequence[Sequence[Block]]) -> str:
  """A web page laying out each document in turn, a rule between them.

  Every style the page relies on sits on its own paragraphs and cells rather
  than in a style sheet, so that it stays attached to whatever part of the page
  is copied into an email.
  """
  sections = '\n<hr>\n'.join(
    '\n'.join(_block_html(block) for block in document)
    for document in documents
  )
  return (
    '<!doctype html>\n'
    '<html lang="en">\n'
    '<head>\n'
    '<meta charset="utf-8">\n'
    f'<title>{html.escape(title)}</title>\n'
    '<style>body { margin: 2em; }</style>\n'
    '</head>\n'
    '<body>\n'
    f'{sections}\n'
    '</body>\n'
    '</html>\n'
  )


# The page's typeface, set on every paragraph and cell so that it travels with a
# copy pasted into an email. A message can name only fonts its reader already
# has, since most mail clients, Gmail among them, load none from the web. So the
# list runs from Calibri, the typeface the emails are usually written in,
# through fonts most readers have:
#
# - `Calibri` comes with Windows and with Microsoft Office.
# - `Carlito` is drawn to Calibri's measurements, and comes with ChromeOS and
#   many Linux systems.
# - `Arial` and `Helvetica` cover Windows and Apple systems without Office.
# - `sans-serif` ends the list on the reader's own sans-serif, such as Roboto on
#   Android, rather than on their default, which is often a serif.
_FONT = 'font-family: Calibri, Carlito, Arial, Helvetica, sans-serif'

# Set on every paragraph.
_PARAGRAPH_STYLE = f'margin: 0 0 1em; {_FONT}'

# Set on every cell. The padding keeps a gap of a word or so between columns,
# wide enough that two columns of numbers never read as one. `nowrap` stops an
# auction wrapping inside its cell.
#
# `nowrap` also folds any line break written into a cell's markup into a single
# space, where `pre` would show it. Some mail programs re-wrap the markup of a
# message they quote in a reply, Windows Live Mail among them, and so break
# lines inside cells. `_cell_html` keeps a row's indent under `nowrap`.
_CELL_STYLE = (
  f'padding: 0 1.5em 0 0; white-space: nowrap; vertical-align: top; {_FONT}'
)

# What separates two values on a table row set as a line of text: about four
# spaces' width. All but the last space are non-breaking, so that the email
# keeps the whole gap rather than collapsing it to one space, while a line too
# long for a narrow screen can still wrap at the last.
_VALUE_GAP = '\N{NO-BREAK SPACE}' * 3 + ' '


def _block_html(block: Block) -> str:
  """One block as markup: a paragraph of lines, or a table.

  A table that allows notes between its rows is set as lines of text instead.
  """
  if isinstance(block, Paragraph):
    lines = '<br>\n'.join(_line_html(line) for line in block.lines)
    return f'<p style="{_PARAGRAPH_STYLE}">{lines}</p>'
  if block.allows_notes_between_rows:
    return _lines_as_blocks_html(_row_as_line(row) for row in block.rows)

  rows = '\n'.join(_row_html(row, block.alignments) for row in block.rows)
  return (
    '<table style="border-collapse: collapse; margin: 0 0 1em">\n'
    f'{rows}\n'
    '</table>'
  )


def _line_html(line: Line) -> str:
  """One line as markup."""
  if isinstance(line, str):
    return html.escape(line)
  return ''.join(_html_of(piece) for piece in line)


def _html_of(piece: Piece) -> str:
  """A piece of a line, or a cell, as markup.

  A placeholder is bracketed and drawn in red, and a link's text is made the
  link itself. A list of links names each in turn, a comma between two.
  """
  if isinstance(piece, Placeholder):
    return f'<span style="color: red">[{html.escape(piece.text)}]</span>'
  if isinstance(piece, Link):
    return f'<a href="{html.escape(piece.url)}">{html.escape(piece.text)}</a>'
  if isinstance(piece, LinkList):
    return ', '.join(_html_of(link) for link in piece.links)
  return html.escape(piece)


def _lines_as_blocks_html(lines: Iterable[Line]) -> str:
  """Lines as markup, each a block of its own.

  An editor's Enter at the end of such a line opens a new one under it, which
  takes the line's font. At the end of one line of a paragraph, Enter would
  split the paragraph instead, and its margin would set the two halves apart.
  """
  markup = '\n'.join(
    f'<div style="{_FONT}">{_line_html(line)}</div>' for line in lines
  )
  return f'<div style="margin: 0 0 1em">\n{markup}\n</div>'


def _row_as_line(row: TableRow) -> Line:
  """A table row as one line of text, its values set a gap apart.

  An empty cell is left out rather than widening the gap around it: with the
  columns no longer lining up, its place says nothing.
  """
  if isinstance(row, FullWidthRow):
    return row.text
  pieces: list[Cell] = []
  for cell in row:
    if not cell:
      continue
    if pieces:
      pieces.append(_VALUE_GAP)
    pieces.append(cell)
  return tuple(pieces)


def _row_html(row: TableRow, alignments: Sequence[Alignment]) -> str:
  """One table row as markup."""
  if isinstance(row, FullWidthRow):
    # An empty row still holds a line's height, so that it reads as a gap.
    text = html.escape(row.text) or '&nbsp;'
    return (
      f'<tr><td colspan="{len(alignments)}" style="{_CELL_STYLE}">'
      f'{text}</td></tr>'
    )

  cells = ''.join(
    f'<td style="{_CELL_STYLE}; text-align: {alignment}">'
    f'{_cell_html(cell)}</td>'
    for cell, alignment in zip(row, alignments, strict=True)
  )
  return f'<tr>{cells}</tr>'


def _cell_html(cell: Cell) -> str:
  """A table cell as markup, its leading spaces made non-breaking.

  A cell's `nowrap` style drops ordinary spaces at its start, and with them the
  indent they give a row.
  """
  if not isinstance(cell, str):
    return _html_of(cell)
  text = cell.lstrip(' ')
  indent = '\N{NO-BREAK SPACE}' * (len(cell) - len(text))
  return indent + html.escape(text)
