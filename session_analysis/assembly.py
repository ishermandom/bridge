# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Compose the parsed cells of one sheet into a canonical `Session`.

Where `parsing` interprets a single cell, this module assembles a whole sheet:
it reads the vision model's flat output (`RawSession`) and drives the per-cell
parsers over each board, producing the canonical `Session`/`Board` record. Like
the parsers, it never raises — a board object the vision model returned
malformed is contained to one issue-bearing `Board`, so a single bad board never
costs the rest of the session (nothing is garbage).

`RawSession`/`RawBoard` model that flat vision-model output: all-string cells,
distinct from the canonical models this produces. They live here, with their
only consumer, rather than in `models` (which is canonical-only).
"""

import datetime

import pydantic

from session_analysis.enums import IssueSeverity
from session_analysis.frozen_model import FrozenModel
from session_analysis.models import (
  Board,
  BoardNumber,
  Issue,
  Session,
  Source,
)
from session_analysis.parsing import (
  parse_auction,
  parse_board_number,
  parse_contract_cell,
  parse_header,
  parse_lead,
)

# Issue code this module raises; see parsing.py for the shared code-set note.
_MALFORMED_BOARD = 'malformed_board'


class _RawModel(FrozenModel):
  """Base for the raw vision-model input: frozen and number-lenient.

  Coerces a cell the model emitted as a JSON number to its string form, so a
  numeric slip (a board number sent as a number, not a string) is contained to
  that cell rather than failing validation and costing the whole board.
  """

  model_config = pydantic.ConfigDict(coerce_numbers_to_str=True)


class RawBoard(_RawModel):
  """The vision model's flat, all-string transcription of one board.

  Each field is a cell exactly as written, no interpretation. Every cell
  defaults to empty, so a board object is never rejected for a missing or blank
  cell: a missing number or lead is contained downstream to that one cell, not
  the whole board. The only board that fails validation is one that isn't an
  object at all, which the assembler contains too. Any extra field the model
  emits (a stray score, a leftover `vs`) is ignored.
  """

  board_number: str = ''
  auction: str = ''
  contract: str = ''
  lead: str = ''
  notes: str = ''


class RawSession(_RawModel):
  """The vision model's flat output: the session header and its raw boards.

  Every field defaults, so a botched header never fails the whole parse: a
  missing `date` degrades to a session-level issue downstream, a missing `event`
  to an empty string, missing `boards` to none. The boards stay unvalidated
  objects, not `RawBoard`s, so each is validated one at a time in assembly and a
  single malformed board is contained to itself rather than failing the session.
  """

  event: str = ''
  date: str = ''
  boards: tuple[object, ...] = ()


def assemble_session(
  raw: RawSession, source: Source, *, reference_date: datetime.date
) -> Session:
  """Assemble a `RawSession` into the canonical `Session` record.

  Drives the header and per-cell parsers over the raw transcription. `source` is
  provenance the vision model never sees (the scan and travellers consulted);
  `reference_date` is the scan date the header's yearless date is resolved
  against. The session is always produced — an unreadable header date is a
  session-level issue, a malformed board a board-level one, never a failure.
  """
  header = parse_header(raw.date, reference_date=reference_date)
  boards = tuple(_assemble_board(board) for board in raw.boards)
  return Session(
    event=raw.event,
    date=header.date,
    source=source,
    boards=boards,
    issues=header.issues,
  )


def _assemble_board(raw_board: object) -> Board:
  """Assemble one raw board object into a canonical `Board`.

  A raw board that isn't an object at all — a stray string or number the model
  emitted where a board belonged — fails `RawBoard` validation and is contained
  here as a single issue-bearing `Board`, so the rest of the session still
  assembles. A board that is an object but has unreadable cells (a missing
  number, an unparseable lead) is not malformed: each cell is parsed and its own
  error contained to that cell.
  """
  try:
    board = RawBoard.model_validate(raw_board)
  except pydantic.ValidationError as error:
    issue = Issue(
      code=_MALFORMED_BOARD,
      severity=IssueSeverity.HIGH,
      message=(
        f'could not read a board from the vision model output: '
        f'{raw_board!r} ({error})'
      ),
    )
    return Board(number=BoardNumber(raw=repr(raw_board), issues=(issue,)))

  number_cell = board.board_number.strip()
  # A circled board number is transcribed in parentheses — `(7)` — reusing the
  # auction's circle convention. The circle is the sheet's own "look here" mark:
  # strip it so the number parser sees a bare number, and flag the whole board
  # (not just its number envelope) for review.
  is_circled = number_cell.startswith('(') and number_cell.endswith(')')
  number_text = number_cell[1:-1] if is_circled else number_cell

  # A blank cell means nothing was recorded — distinct from a filled cell that
  # won't parse. The per-cell parsers assume a value was written, so the empty
  # case is resolved to an absent value here rather than sent down to become a
  # spurious issue. An empty auction is naturally just no entries.
  return Board(
    number=parse_board_number(number_text),
    flagged_for_review=is_circled,
    auction=tuple(parse_auction(board.auction)),
    opening_lead=parse_lead(board.lead) if board.lead.strip() else None,
    outcome=(
      parse_contract_cell(board.contract) if board.contract.strip() else None
    ),
    notes=board.notes.strip() or None,
  )
