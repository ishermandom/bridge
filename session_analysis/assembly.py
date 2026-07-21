# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Compose the parsed cells of one sheet into a canonical `Session`.

Where `parsing` interprets a single cell, this module assembles a whole sheet:
it reads the vision model's flat output (`RawSession`) and drives the per-cell
parsers over each board, producing the canonical `Session`/`Board` record. Like
the parsers, it never raises — a board object the vision model returned
malformed is contained to one issue-bearing `Board`, so a single bad board never
costs the rest of the session (nothing is garbage).

`RawSheet`/`RawSession`/`RawBoard` model that flat vision-model output: a single
`sheet` envelope of all-string cells, distinct from the canonical models this
produces. They live here, with their only consumer, rather than in `models`
(which is canonical-only).

`parse_and_assemble_session` is the extraction entry point: it takes the vision
model's raw JSON string, parses it, assembles it, and runs `validate_session`
over the result, so a caller gets one call from raw output to a validated
`Session`.
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
  parse_footer,
  parse_lead,
)
from session_analysis.validation import validate_session

# Issue codes this module raises; see parsing.py for the shared code-set note.
_MALFORMED_BOARD = 'malformed_board'
_MALFORMED_SESSION = 'malformed_session'


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
  """The vision model's flat output: the session footer and its raw boards.

  Every field defaults, so a botched footer never fails the whole parse: a
  missing `date` degrades to a session-level issue downstream, a missing `event`
  to an empty string, missing `boards` to none. The boards stay unvalidated
  objects, not `RawBoard`s, so each is validated one at a time in assembly and a
  single malformed board is contained to itself rather than failing the session.
  """

  event: str = ''
  date: str = ''
  boards: tuple[object, ...] = ()


class RawSheet(_RawModel):
  """The vision model's top-level output: one session under a `sheet` key.

  The envelope exists because models deliver tool input as `{parameter_name:
  payload}` — see extraction_schema.py for why the wire contract leans into
  that. `sheet` has no default: output with the envelope missing is malformed,
  and the entry point contains it as a session-level issue rather than passing
  an empty session off as a parse.
  """

  sheet: RawSession


def assemble_session(
  raw: RawSession, source: Source, *, reference_date: datetime.date
) -> Session:
  """Assemble a `RawSession` into the canonical `Session` record.

  Drives the footer and per-cell parsers over the raw transcription. `source` is
  provenance the vision model never sees (the scan and travellers consulted);
  `reference_date` is the scan date the footer's yearless date is resolved
  against. The session is always produced — an unreadable footer date is a
  session-level issue, a malformed board a board-level one, never a failure.
  """
  footer = parse_footer(raw.date, reference_date=reference_date)
  boards = tuple(_assemble_board(board) for board in raw.boards)
  return Session(
    event=raw.event,
    date=footer.date,
    source=source,
    boards=boards,
    issues=footer.issues,
  )


def parse_and_assemble_session(
  raw_json: str, source: Source, *, reference_date: datetime.date
) -> Session:
  """Parse the vision model's raw JSON output into a validated `Session`.

  The extraction entry point: `RawSheet.model_validate_json` still raises where
  `_assemble_board` cannot help — the top-level shape is fundamentally wrong
  (not an object, no `sheet` envelope, or `boards` not a list), so there is no
  raw boards list to hand to `assemble_session` at all. That case is contained
  here as a single session-level issue rather than aborting extraction, the same
  nothing-is-garbage contract the rest of this module keeps. A session that does
  parse is run through `validate_session` before being returned, so the caller
  always gets a session with every board-level check already applied.
  """
  try:
    raw = RawSheet.model_validate_json(raw_json).sheet
  except pydantic.ValidationError as error:
    issue = Issue(
      code=_MALFORMED_SESSION,
      severity=IssueSeverity.HIGH,
      message=(
        f'could not read a session from the vision model output: '
        f'{raw_json!r} ({error})'
      ),
    )
    return Session(event='', source=source, issues=(issue,))

  return validate_session(
    assemble_session(raw, source, reference_date=reference_date)
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
