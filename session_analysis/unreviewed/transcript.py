# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Reading a digitized session back, in the shorthand it was written in.

What this pipeline produces is a JSON record, and nothing rendered it — so the
first thing anyone wants from a digitized sheet, reading the session back, took
a JSON viewer. This module prints the record instead, a line per board.

The sheet's own notation is what those lines are in, rather than a canonical
prose spelling. Whoever wrote the sheet already reads its shorthand fluently, so
a board comes back as they wrote it:

```text
#5    1C (DBL) 3C (3H)    4CW+4    lead=9oH    MP=6
```

Opponents' calls sit in parentheses, standing in for the circles the sheet draws
around them; the contract cell keeps the level, strain, declarer and result run
together; the result counts tricks beyond book, the convention spec.md
`#notation` settles.

What no transcript can show is who sat where. Passes usually go unwritten, so
the seat rotation cannot be replayed from the tokens and even the opening side
is ambiguous — which is why the declarer is not derived anywhere in this project
(models.md `#validation`). The circle convention survives that gap: it says
whether a call was ours or theirs, and that is as fine a distinction as the
record supports.

Each value is rendered from its parse rather than from the envelope's `raw`, so
one spelling reaches the reader however the sheet happened to write it — `p`
and `P` both arrive here as `PASS`, `x` and `*` as `DBL`, `1N` and `1NT` alike
as `1N`. Where a parse failed there
is nothing to spell, and the raw transcription stands in wrapped in `?…?`: a
call dropped for being unreadable would leave a line reading as though the sheet
had said nothing there.
"""

import argparse
import dataclasses
import sys
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path

from session_analysis import notation
from session_analysis.enums import CallKind, Penalty, Rank, Strain
from session_analysis.models import (
  AuctionEntry,
  Board,
  BoardNumber,
  Call,
  Card,
  Lead,
  Outcome,
  Passout,
  Session,
)
from session_analysis.private_paths import PrivateTree, discover_private_tree

# How a call that is not a bid is written. A bid is spelled from its own level
# and strain instead, by `_spell_strain` below.
_CALL_SPELLINGS: Mapping[CallKind, str] = {
  CallKind.PASS: 'PASS',
  CallKind.DOUBLE: 'DBL',
  CallKind.REDOUBLE: 'RDBL',
}

# The mark a contract's doubling trails, as the sheet writes it — the same
# spelling models.md's own worked example uses (`6H*W-1`).
_PENALTY_MARKS: Mapping[Penalty, str] = {
  Penalty.NONE: '',
  Penalty.DOUBLED: '*',
  Penalty.REDOUBLED: '**',
}

# Set between columns. Four spaces rather than one, so that a column's values
# read down the page as a group instead of running into the next column's.
_COLUMN_GAP = ' ' * 4


def render_session(session: Session) -> Iterator[str]:
  """The whole of one session as plain text, a line at a time.

  The header names the session; the lines below it are its boards, laid out as a
  table so that a column can be read down the page.
  """
  yield from _header_lines(session)
  yield from _board_lines(session.boards)


def _header_lines(session: Session) -> Iterator[str]:
  """The session's name and date, its stored key, then a separating blank."""
  # A date left unread is named rather than left blank, for the reason the
  # `?…?` marks exist: it should not read as a session that was never dated.
  date = session.date.isoformat() if session.date else 'date not read'
  yield f'{session.event} — {date}'

  # Assigned at ingest, so a session that has only been parsed has no key to
  # name yet.
  if session.session_key:
    yield session.session_key

  yield ''


def _board_lines(boards: Sequence[Board]) -> Iterator[str]:
  """Every board that recorded something, as one aligned line each."""
  rows = [_columns_for(board) for board in boards if _holds_a_record(board)]
  if not rows:
    yield 'This session recorded no boards.'
    return
  yield from _laid_out(rows)


@dataclasses.dataclass(frozen=True)
class _BoardColumns:
  """One board's line, split into the columns it is laid out in.

  Splitting is kept apart from laying out because a column's width is a property
  of the whole session rather than of any one board: a column is as wide as its
  widest value, which is not known until every board has been rendered.
  """

  number: str
  auction: str
  contract: str
  lead: str
  matchpoints: str

  @property
  def cells(self) -> Sequence[str]:
    """The columns in the order they are printed."""
    return (
      self.number,
      self.auction,
      self.contract,
      self.lead,
      self.matchpoints,
    )


def _laid_out(rows: Sequence[_BoardColumns]) -> Iterator[str]:
  """Pad every column to its widest value, so the boards read as a table.

  A trailing column a board left empty is stripped rather than padded, so a
  session where no traveller has landed yet does not print a page of trailing
  whitespace.
  """
  column_count = len(rows[0].cells)
  widths = [
    max(len(row.cells[column]) for row in rows)
    for column in range(column_count)
  ]
  for row in rows:
    padded = (
      cell.ljust(width) for cell, width in zip(row.cells, widths, strict=True)
    )
    yield _COLUMN_GAP.join(padded).rstrip()


def _holds_a_record(board: Board) -> bool:
  """Whether the board's row on the sheet recorded anything at all.

  A form prints more rows than most sessions fill, and an unused row assembles
  into a board whose every cell was blank. Such a board is stored like any other
  — nothing is garbage — but it has nothing to transcribe, and a line naming
  neither a board nor anything played on it tells a reader less than no line at
  all.
  """
  return bool(
    board.number.raw.strip()
    or board.auction
    or board.opening_lead
    or board.outcome
  )


def _columns_for(board: Board) -> _BoardColumns:
  """One board's columns, each empty where the sheet recorded nothing."""
  return _BoardColumns(
    number=_spell_number(board.number),
    auction=_spell_auction(board.auction),
    contract=_spell_outcome(board.outcome),
    lead=_spell_lead(board.opening_lead),
    matchpoints=_spell_matchpoints(board.matchpoints),
  )


def _spell_number(number: BoardNumber) -> str:
  """The board number, as `#5`, or its transcription where it went unread."""
  if not number.schedule:
    return _unreadable(number.raw)
  return f'#{number.schedule.number}'


def _spell_auction(entries: Sequence[AuctionEntry]) -> str:
  """The auction as one space-separated run of calls, in the sheet's marks.

  A box the sheet drew around a run of calls to revisit with partner is
  reassembled here from the per-call flag the parser split it into, so a span
  comes back as the one `[…]` it was drawn as rather than as a bracket around
  each of its calls.
  """
  tokens: list[str] = []
  is_in_box = False
  for entry in entries:
    token = _spell_entry(entry)
    if entry.flagged_for_discussion and not is_in_box:
      token = f'[{token}'
      is_in_box = True
    elif is_in_box and not entry.flagged_for_discussion:
      # The span ended at the call before this one, so it is that call the
      # closing bracket belongs to.
      tokens[-1] += ']'
      is_in_box = False
    tokens.append(token)

  # A span running to the end of the auction has no following call to close it.
  if is_in_box and tokens:
    tokens[-1] += ']'

  return ' '.join(tokens)


def _spell_entry(entry: AuctionEntry) -> str:
  """One written call: its own spelling, plus the marks the sheet put on it."""
  call = _spell_call(entry.call) if entry.call else None
  if not call:
    # An unparsed token's `raw` carries any alert mark already, since the parser
    # strips only the circle and box from it.
    return _circled(_unreadable(entry.raw), entry.by_opponents)

  alerted = f'{call}!' if entry.alerted else call
  return _circled(alerted, entry.by_opponents)


def _circled(call: str, by_opponents: bool) -> str:
  """A call in parentheses when the sheet circled it as the opponents'."""
  return f'({call})' if by_opponents else call


def _spell_call(call: Call) -> str | None:
  """An understood call as the sheet writes it, or None if it cannot be spelled.

  A bid holds its level and strain and every other kind of call holds neither,
  so a bid missing either is a shape the parser does not produce. Returning None
  rather than spelling a partial bid sends such a call down the same path as one
  that never parsed, where the raw transcription makes the trouble visible
  instead of a plausible-looking bid hiding it.
  """
  if call.kind != CallKind.BID:
    return _CALL_SPELLINGS[call.kind]
  if not call.level or not call.strain:
    return None
  return f'{call.level}{_spell_strain(call.strain)}'


def _spell_strain(strain: Strain) -> str:
  """A strain as the sheet writes one, every spelling a single character.

  The canonical notrump is `NT`, which the sheet shortens to `N` — the spelling
  `notation.STRAIN_BY_LETTER` reads back either way. Keeping it one character
  wide is what stops a written contract running its parts together illegibly:
  `3NS` separates into a level, a strain and a declarer where `3NTS` does not.
  """
  return 'N' if strain == Strain.NOTRUMP else strain.value


def _spell_outcome(outcome: Outcome | None) -> str:
  """The contract cell: the contract and its result, run together as written."""
  if not outcome:
    return ''
  resolution = outcome.resolution
  if not resolution:
    return _unreadable(outcome.raw)
  if isinstance(resolution, Passout):
    # The sheet strikes such a cell through, which has no rendering here that a
    # reader would not take for an empty column, so it is spelled out.
    return 'PASSED OUT'

  contract = resolution.contract
  return (
    f'{contract.level}{_spell_strain(contract.strain)}'
    f'{_PENALTY_MARKS[contract.penalty]}{contract.declarer}'
    f'{_spell_result(contract.level, resolution.result.tricks_taken)}'
  )


def _spell_result(level: int, tricks_taken: int) -> str:
  """A result in the sheet's convention: tricks beyond book, or tricks short.

  The two halves count from different places, which is the convention spec.md
  `#notation` records: a contract that came home is written `+N` for the tricks
  it took above book, so `4C` making exactly is `+4` rather than `=`, while one
  that failed is written `-N` for the tricks it fell short by.
  """
  tricks_needed = level + notation.BOOK
  if tricks_taken >= tricks_needed:
    return f'+{tricks_taken - notation.BOOK}'
  return f'-{tricks_needed - tricks_taken}'


def _spell_lead(lead: Lead | None) -> str:
  """The opening lead, labelled so it cannot be misread as a bid.

  The label is what separates `9oH` from a call: both are a digit and a letter,
  and the `o` for the spoken 'of' is the only thing between them. A lead the
  sheet recorded as not played — a cell struck through rather than illegible —
  carries no issue and no card, and shows as written.
  """
  if not lead:
    return ''
  if lead.card:
    card = _spell_card(lead.card)
  elif lead.issues:
    card = _unreadable(lead.raw)
  else:
    card = lead.raw.strip()
  return f'lead={card}'


def _spell_card(card: Card) -> str:
  """A card as the sheet writes one: a rank, an `o` for 'of', then a suit."""
  # The canonical ten is `T`, where a sheet writes the two characters out.
  rank = '10' if card.rank == Rank.TEN else card.rank.value
  return f'{rank}o{card.suit}'


def _spell_matchpoints(matchpoints: float | None) -> str:
  """Our matchpoints on the board, empty until a traveller supplies them."""
  # A bottom board scores zero, so absence has to be tested for rather than
  # falsiness. `g` drops the trailing `.0` a whole score would otherwise carry
  # while leaving a half score its `.5`.
  if matchpoints is None:
    return ''
  return f'MP={matchpoints:g}'


def _unreadable(raw: str) -> str:
  """A transcription no parse could understand, marked as standing unread."""
  return f'?{raw.strip()}?'


def main(argv: Sequence[str] | None = None) -> int:
  """Print a transcript of each session record named, or of every stored one.

  Returns:
    The exit status: non-zero if any record could not be read, so a run that
    skipped one is distinguishable from one that printed everything asked of
    it.
  """
  records = _parse_args(argv).records
  if not records:
    try:
      tree = discover_private_tree()
    except (FileNotFoundError, RuntimeError) as error:
      print(f'could not find the stored sessions: {error}', file=sys.stderr)
      return 1
    records = _stored_records(tree)
    if not records:
      print('No sessions have been digitized yet.', file=sys.stderr)
      return 1

  status = 0
  is_first = True
  for record in records:
    session = _read_session(record)
    if not session:
      status = 1
      continue
    if not is_first:
      print()
    is_first = False
    for line in render_session(session):
      print(line)
  return status


def _read_session(record: Path) -> Session | None:
  """The session a record holds, or None with a complaint on standard error.

  A record that cannot be read costs its own transcript and not the run's:
  pointed at a whole tree, the command should still print the records it can.
  """
  try:
    text = record.read_text()
  except OSError as error:
    print(f'could not read {record}: {error}', file=sys.stderr)
    return None

  try:
    return Session.model_validate_json(text)
  except ValueError as error:
    print(f'{record} holds no session record: {error}', file=sys.stderr)
    return None


def _stored_records(tree: PrivateTree) -> Sequence[Path]:
  """Every stored session record, the reviewed and the pending alike.

  The pending records sit inside the session root, so one walk finds both — a
  session reads back the same whether or not review has reached it yet.
  """
  root = tree.session_records
  if not root.is_dir():
    return ()
  return sorted(root.rglob('*.json'))


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
  """Parse the command line: which session records to transcribe, if any."""
  parser = argparse.ArgumentParser(
    description='Print a digitized session as plain text, in the shorthand '
    'the scoresheet itself was written in.'
  )
  parser.add_argument(
    'records',
    nargs='*',
    type=Path,
    help='the session records to transcribe; every stored session by default',
  )
  return parser.parse_args(argv)


if __name__ == '__main__':
  sys.exit(main())
