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
its values read best.

A transcript is therefore built once, as a short run of blocks, and laid out by
whichever of the two functions here its reader needs.
"""

import dataclasses
import enum
import html
from collections.abc import Iterator, Sequence


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


# A line of text, whole or in pieces, some of them placeholders.
Line = str | tuple[str | Placeholder, ...]


@dataclasses.dataclass(frozen=True)
class Paragraph:
  """Lines that belong together, set with no blank line between them."""

  lines: tuple[Line, ...]


@dataclasses.dataclass(frozen=True)
class FullWidthRow:
  """A table row holding one value across every column, such as a note."""

  text: str


# A row of cells, one per column, or one value spanning them all.
TableRow = tuple[str, ...] | FullWidthRow


@dataclasses.dataclass(frozen=True)
class Table:
  """Rows whose cells line up in columns."""

  # One per column; plain text has no use for them.
  alignments: tuple[Alignment, ...]
  rows: tuple[TableRow, ...]


# What a transcript is built from: runs of lines, and tables.
Block = Paragraph | Table


def as_plain_text(blocks: Sequence[Block]) -> Iterator[str]:
  """The blocks as lines of text, a blank line between one block and the next.

  A table's cells are separated by tabs. Empty cells at the end of a row are
  dropped, since a run of trailing tabs says nothing and pastes as nothing.
  """
  for index, block in enumerate(blocks):
    if index:
      yield ''
    if isinstance(block, Paragraph):
      yield from (_line_text(line) for line in block.lines)
    else:
      for row in block.rows:
        if isinstance(row, FullWidthRow):
          yield row.text
        else:
          yield '\t'.join(row).rstrip('\t')


def _line_text(line: Line) -> str:
  """One line as plain text, each placeholder in its square brackets."""
  if isinstance(line, str):
    return line
  return ''.join(
    f'[{piece.text}]' if isinstance(piece, Placeholder) else piece
    for piece in line
  )


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
# wide enough that two columns of numbers never read as one. `pre` keeps a
# cell's leading spaces, which indent a row, and stops an auction wrapping
# inside its cell.
_CELL_STYLE = (
  f'padding: 0 1.5em 0 0; white-space: pre; vertical-align: top; {_FONT}'
)


def _block_html(block: Block) -> str:
  """One block as markup: a paragraph of lines, or a table."""
  if isinstance(block, Paragraph):
    lines = '<br>\n'.join(_line_html(line) for line in block.lines)
    return f'<p style="{_PARAGRAPH_STYLE}">{lines}</p>'

  rows = '\n'.join(_row_html(row, block.alignments) for row in block.rows)
  return (
    '<table style="border-collapse: collapse; margin: 0 0 1em">\n'
    f'{rows}\n'
    '</table>'
  )


def _line_html(line: Line) -> str:
  """One line as markup, each placeholder bracketed and drawn in red."""
  if isinstance(line, str):
    return html.escape(line)
  return ''.join(
    f'<span style="color: red">[{html.escape(piece.text)}]</span>'
    if isinstance(piece, Placeholder)
    else html.escape(piece)
    for piece in line
  )


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
    f'{html.escape(cell)}</td>'
    for cell, alignment in zip(row, alignments, strict=True)
  )
  return f'<tr>{cells}</tr>'
