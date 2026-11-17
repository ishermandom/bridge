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
import math
from collections.abc import Iterable, Iterator, Mapping, Sequence


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


class Emphasis(enum.Enum):
  """How a run of text stands apart from the rest of its line on the web page.

  Plain text has no typography, so there the text reads as written.
  """

  # Gray, for what a reader passes over on the way to what they scan for.
  MUTED = enum.auto()
  # Bold, for what a reader scans the line for.
  STRONG = enum.auto()
  # Blue, for news that is good for the reader.
  GOOD = enum.auto()
  # Red, for news that is bad for the reader.
  BAD = enum.auto()


@dataclasses.dataclass(frozen=True)
class Emphasized:
  """Text set in an emphasis of its own on the web page."""

  text: str
  emphasis: Emphasis


# One piece of a line.
Piece = str | Placeholder | Link | LinkList | Emphasized

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


# One piece of a table cell.
CellPiece = str | Link | Emphasized

# What one cell of a table holds: one piece, or a run of them read as one value.
Cell = CellPiece | tuple[CellPiece, ...]

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
  # add one, so the page sets such a table's rows as lines of text instead, each
  # cell held to its column's width. Plain text, where a new line can go
  # anywhere, lays it out like any other table.
  allows_notes_between_rows: bool = False
  # For a table allowing notes, a width in em to hold its second column to,
  # rather than setting the column as wide as its widest value. Sizing a column
  # to its widest suits values of much the same length, but values as varied as
  # auctions would leave most lines a wide gap. Held to a width that fits most
  # of them instead, a longer value wraps within the column, and dots lead the
  # eye across from a shorter one to the next.
  second_column_width: float | None = None


# What a transcript is built from: runs of lines, and tables.
Block = Paragraph | Table


def as_plain_text(blocks: Sequence[Block]) -> Iterator[str]:
  """The blocks as lines of text, a blank line between one block and the next.

  A table's cells are separated by tabs. Empty cells at the end of a row are
  dropped, since a run of trailing tabs says nothing and pastes as nothing. The
  address of each link follows the line or row holding it, on a line of its own.

  A non-breaking space is written as an ordinary one. On the web page it keeps
  two words on one line, as `6 mps`, but plain text is never rewrapped, and a
  pasted cell is better without a character that looks like a space and is not
  one.
  """
  for line in _plain_lines(blocks):
    yield line.replace('\N{NO-BREAK SPACE}', ' ')


def _plain_lines(blocks: Sequence[Block]) -> Iterator[str]:
  """The blocks as lines of text, before their spaces are made ordinary."""
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
          yield '\t'.join(_cell_text(cell) for cell in row).rstrip('\t')
          yield from _link_lines(
            piece for cell in row for piece in _cell_pieces(cell)
          )


def _line_text(line: Line) -> str:
  """One line as plain text."""
  if isinstance(line, str):
    return line
  # A list of links ending the line is left out, which would otherwise leave the
  # space that set it off trailing with nothing after it.
  return ''.join(_text_of(piece) for piece in line).rstrip()


def _cell_pieces(cell: Cell) -> tuple[CellPiece, ...]:
  """A cell's pieces, whether it holds one or a run of them."""
  return cell if isinstance(cell, tuple) else (cell,)


def _cell_text(cell: Cell) -> str:
  """One cell as plain text."""
  return ''.join(_text_of(piece) for piece in _cell_pieces(cell))


def _text_of(piece: Piece) -> str:
  """A piece of a line, or of a cell, as plain text.

  A placeholder is set in its square brackets, and a link keeps its text, its
  address left for a line below. A list of links leaves out the names, and
  emphasized text reads as written.
  """
  if isinstance(piece, Placeholder):
    return f'[{piece.text}]'
  if isinstance(piece, Link | Emphasized):
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

# What separates two values on a table row set as a line of text: a muted middle
# dot with about two spaces' width either side. All but the last space are
# non-breaking, so that the email keeps the whole gap rather than collapsing it
# to one space, while a line too long for a narrow screen can still wrap after
# the dot.
_VALUE_SEPARATOR: tuple[Piece, ...] = (
  '\N{NO-BREAK SPACE}' * 2,
  Emphasized('\N{MIDDLE DOT}', Emphasis.MUTED),
  '\N{NO-BREAK SPACE} ',
)

# What sets the cell naming a row, such as a board's number, off from the values
# after it on a line: about four spaces' width, kept whole the way the separator
# is.
_NAME_GAP = '\N{NO-BREAK SPACE}' * 3 + ' '

# How each emphasis is drawn.
#
# - The gray, the blue and the red share one brightness, a relative luminance of
#   about 0.18. That is the only brightness at which a color contrasts equally
#   with white and with black, about 4.6 to 1 against each, so each stays
#   readable where a mail program darkens the background in dark mode yet leaves
#   the colors as written. The blue and the red stop a little short of the most
#   saturated colors that brightness allows, so that they read as color rather
#   than glare.
# - Bold rather than semibold: none of the page's fonts comes in a semibold, and
#   a font without one draws a weight of 600 as bold.
# - Bold text is also kept whole, since a reader scans for it, so that a
#   contract and its result never break across two lines.
_EMPHASIS_STYLES: Mapping[Emphasis, str] = {
  Emphasis.MUTED: 'color: #767676',
  Emphasis.STRONG: 'font-weight: bold; white-space: nowrap',
  Emphasis.GOOD: 'color: #2d74d8',
  Emphasis.BAD: 'color: #d73c36',
}

# Set on every line set as a block of its own. The extra spacing between lines
# helps the eye follow a long run of them across, and a note opened under a line
# by Enter takes the same spacing.
_LINE_STYLE = f'{_FONT}; line-height: 1.4'

# What ends every line set as a block of its own. An editor gives the text typed
# after Enter the style of the character before the caret, so a line ending in
# emphasized text would pass its emphasis on to a reader's note. This character
# has no emphasis and cannot be seen, so a note takes the line's plain style
# instead, and the line looks no different.
#
# A hair space, the thinnest of the spaces, is wide enough for this where a
# zero-width character is not. In Chrome, a click past the end of a line puts
# the caret after a hair space, but before a zero-width character, so that Enter
# carries the zero-width character off into the new line, and a second note
# under the same line takes the line's last emphasis after all.
_PLAIN_LINE_END = '\N{HAIR SPACE}'

# How a line of a table allowing notes holds each cell to its column's width. It
# works in layers, so that a mail program missing a layer loses only what that
# layer adds:
#
# - Each cell is an inline block, set to its column's width. A program without
#   inline blocks, such as Outlook for Windows, sets the cells as plain text,
#   where the gaps and separators written between them still part them, and the
#   line reads as it would unaligned.
# - The held second column draws its dots with a flex layout, inside its block.
#   A program without flex layout, such as Gmail's apps showing mail from
#   another provider's account, leaves the block its width, so the columns still
#   line up, only without the dots.
#
# Every block aligns by its top, so that the rest of a line stays level with the
# first line of a wrapped second column. Every other column is given a minimum
# width rather than a width, and kept from wrapping: Gmail breaks text too wide
# for its box, even mid-word, so a cell wider than estimated widens its own line
# instead.
_HELD_STYLE = 'display: inline-block; vertical-align: top'
_FITTED_STYLE = (
  'display: inline-block; vertical-align: top; white-space: nowrap'
)
_DOTS_STYLE = (
  'flex: 1 0 1em; margin-left: 0.4em; border-bottom: 1.5px dotted #a8a8a8'
)

# Arial's character widths, in em, from its published measurements, which
# Helvetica shares. Calibri and Roboto draw narrower, so a column wide enough in
# Arial is wide enough in each of the page's fonts. A character missing here is
# taken to be an em wide, wider than any listed.
_ARIAL_WIDTHS: Mapping[str, float] = {
  **dict.fromkeys("'", 0.191),
  **dict.fromkeys('ijl', 0.222),
  **dict.fromkeys('|', 0.26),
  **dict.fromkeys(' !,./:;I[\\]ft\N{NO-BREAK SPACE}\N{MIDDLE DOT}', 0.278),
  **dict.fromkeys('()-`r{}', 0.333),
  **dict.fromkeys('"', 0.355),
  **dict.fromkeys('*', 0.389),
  **dict.fromkeys('^', 0.469),
  **dict.fromkeys('Jckvsxyz', 0.5),
  **dict.fromkeys('#$0123456789?L_abdeghnopqu\N{FIGURE SPACE}', 0.556),
  **dict.fromkeys('+<=>~\N{MINUS SIGN}', 0.584),
  **dict.fromkeys('FTZ', 0.611),
  **dict.fromkeys('&ABEKPSVXY', 0.667),
  **dict.fromkeys('CDHNRUw', 0.722),
  **dict.fromkeys('GOQ', 0.778),
  **dict.fromkeys('Mm', 0.833),
  **dict.fromkeys('%', 0.889),
  **dict.fromkeys('W', 0.944),
  **dict.fromkeys('@', 1.015),
}


def _block_html(block: Block) -> str:
  """One block as markup: a paragraph of lines, or a table.

  A table that allows notes between its rows is set as lines of text instead.
  """
  if isinstance(block, Paragraph):
    lines = '<br>\n'.join(_line_html(line) for line in block.lines)
    return f'<p style="{_PARAGRAPH_STYLE}">{lines}</p>'
  if block.allows_notes_between_rows:
    return _noted_table_html(block)

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
  """A piece of a line, or of a cell, as markup.

  A placeholder is bracketed and drawn in red, and a link's text is made the
  link itself. A list of links names each in turn, a comma between two, and
  emphasized text is drawn in its emphasis.
  """
  if isinstance(piece, Placeholder):
    return f'<span style="color: red">[{html.escape(piece.text)}]</span>'
  if isinstance(piece, Link):
    return f'<a href="{html.escape(piece.url)}">{html.escape(piece.text)}</a>'
  if isinstance(piece, LinkList):
    return ', '.join(_html_of(link) for link in piece.links)
  if isinstance(piece, Emphasized):
    style = _EMPHASIS_STYLES[piece.emphasis]
    return f'<span style="{style}">{html.escape(piece.text)}</span>'
  return html.escape(piece)


def _noted_table_html(table: Table) -> str:
  """A table allowing notes, as lines of text whose columns line up.

  Each line is a block of its own. An editor's Enter at the end of such a line
  opens a new one under it, which takes the line's font, and the line's last
  character leaves none of its emphasis to what is typed there. At the end of
  one line of a paragraph, Enter would split the paragraph instead, and its
  margin would set the two halves apart.
  """
  rows = [row for row in table.rows if not isinstance(row, FullWidthRow)]
  widths = _column_widths(table, rows)
  markup = '\n'.join(
    f'<div style="{_LINE_STYLE}">'
    f'{_noted_row_html(row, table, widths)}{_PLAIN_LINE_END}</div>'
    for row in table.rows
  )
  return f'<div style="margin: 0 0 1em">\n{markup}\n</div>'


def _column_widths(
  table: Table, rows: Sequence[tuple[Cell, ...]]
) -> Mapping[int, float]:
  """The minimum width in em of each column set to its widest, by its place.

  A column's width counts the separator its cells open with, so that an empty
  cell, which has none, still fills its column.
  """
  separator = ''.join(_text_of(piece) for piece in _VALUE_SEPARATOR)
  widths: dict[int, float] = {}
  for index, column in enumerate(zip(*rows, strict=True)):
    # A held column has its own width.
    if index == 1 and table.second_column_width:
      continue
    opening = separator if index >= _first_separated_column(table) else ''
    widths[index] = _arial_width(opening) + max(
      _arial_width(_cell_text(cell)) for cell in column
    )
  return widths


def _first_separated_column(table: Table) -> int:
  """The first column whose cells open with a separator.

  The column after the name, and the column after a held second column, need
  none: a gap sets each off, which the held column's dots lead across.
  """
  return 3 if table.second_column_width else 2


def _arial_width(text: str) -> float:
  """How wide `text` is drawn in Arial at its regular weight, in em.

  The estimate runs 3% over Arial's published measurements, since Arial as some
  systems draw it sets a few characters, such as `+`, a little wider.
  """
  return 1.03 * sum(_ARIAL_WIDTHS.get(character, 1.0) for character in text)


def _noted_row_html(
  row: TableRow, table: Table, widths: Mapping[int, float]
) -> str:
  """One row of a table allowing notes as a line, its cells held to width.

  The first cell names the row, as a board's number does, so a gap alone sets it
  off from the values after it, and a separator stands between each two of those
  values.
  """
  if isinstance(row, FullWidthRow):
    return html.escape(row.text)
  name, *values = row
  markup = _fitted_cell_html(_cell_pieces(name), widths[0]) + _NAME_GAP
  for index, value in enumerate(values, start=1):
    if index == 1 and table.second_column_width:
      markup += _held_cell_html(value, table.second_column_width) + _NAME_GAP
      continue
    pieces: tuple[Piece, ...] = _cell_pieces(value)
    if index >= _first_separated_column(table) and _cell_text(value):
      pieces = (*_VALUE_SEPARATOR, *pieces)
    markup += _fitted_cell_html(pieces, widths[index])
  return markup


def _fitted_cell_html(pieces: tuple[Piece, ...], width: float) -> str:
  """A cell kept on one line, at least as wide as its column."""
  return (
    f'<span style="{_FITTED_STYLE}; min-width: {_in_em(width)}">'
    f'{_line_html(pieces)}</span>'
  )


def _held_cell_html(cell: Cell, width: float) -> str:
  """A cell held to a set width, dots leading across from its text."""
  # The cell's pieces share one wrapper, which the flex layout sets as one item
  # beside the dots, where it would set each piece apart and drop the space
  # between two. The wrapper is styled, though its style is flex's default: a
  # page copied into Gmail loses a span with no style of its own.
  return (
    f'<span style="{_HELD_STYLE}; width: {_in_em(width)}">'
    '<span style="display: flex; align-items: baseline">'
    f'<span style="flex: 0 1 auto">{_line_html(_cell_pieces(cell))}</span>'
    f'<span style="{_DOTS_STYLE}"></span>'
    '</span></span>'
  )


def _in_em(width: float) -> str:
  """A width in em, rounded up to the hundredth, so as never to fall short."""
  return f'{math.ceil(width * 100) / 100:g}em'


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
    return ''.join(_html_of(piece) for piece in _cell_pieces(cell))
  text = cell.lstrip(' ')
  indent = '\N{NO-BREAK SPACE}' * (len(cell) - len(text))
  return indent + html.escape(text)
