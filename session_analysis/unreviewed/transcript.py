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
#5    1C (DBL) 3C (3H)    4CW+4    lead=9oH    MP=6    DD+1    PLAY-1
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
one spelling reaches the reader however the sheet happened to write it — `p` and
`P` both arrive here as `PASS`, `x` and `*` as `DBL`, `1N` and `1NT` alike as
`1N`. Where a parse failed there is nothing to spell, and the raw transcription
stands in its place, wrapped in `?…?`: a call dropped for being unreadable would
leave a line reading as though the sheet had said nothing there.

Two last columns set each result beside what the deal allowed, from our own
side's point of view: `DD+1` says the board went a trick our way against what
best play by both sides yields, `DD-2` two tricks against us. Defending counts
the same way as declaring — the opponents held to a trick short of the count is
`DD+1`, exactly as our own declarer taking a trick more than the count is.

`PLAY` counts the same way but from the position the opening lead left, so it is
the play with the lead taken out of the reckoning, and the gap between the two
columns is what the lead itself was worth.

Which way that gap can run is fixed rather than free, for the reason
`double_dummy_comparison` argues. Declaring, `PLAY` never exceeds `DD`, and the
line above is that case: an opening lead that handed us two tricks, one of which
the play gave back. Defending, `PLAY` never falls below `DD`, so `DD-1 PLAY+1`
is a lead of ours that cost two tricks, of which the defense won one back —
still a trick down on what the deal offered, not recovered from.

The published cell comes from a traveller, and the deal the solved count needs
is written onto the board from one at reconciliation. So both columns stand
empty for a board no traveller reached, and are absent altogether from a session
none has reached — `double_dummy_comparison` carries what their silences mean.

A recap under the boards totals the two columns, and organizes them by our own
position throughout: the boards we declared split by which of us declared, the
boards we defended by which of us led. The opponents' seats never appear, since
a board they declared is one we led — so every board falls under a seat of ours
either way.
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
from session_analysis.travellers import Traveller
from session_analysis.unreviewed import double_dummy_comparison

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


def render_session(
  session: Session, travellers: Sequence[Traveller] = ()
) -> Iterator[str]:
  """The whole of one session as plain text, a line at a time.

  The header names the session; the lines below it are its boards, laid out as a
  table so that a column can be read down the page.

  `travellers` are the captures reconciliation joined to this session, and carry
  the analysis the double-dummy column compares each result with. They are
  passed in rather than read here so that rendering stays a pure function of
  what it is handed; `double_dummy_comparison.read_referenced_travellers` is
  what reads them off disk.
  """
  recorded = [board for board in session.boards if _holds_a_record(board)]
  comparisons = double_dummy_comparison.compare_boards(session, travellers)
  yield from _header_lines(session, has_recorded_boards=bool(recorded))
  yield from _board_lines(recorded, comparisons)
  yield from _recap_lines(double_dummy_comparison.recap_of(comparisons))


def _header_lines(
  session: Session, *, has_recorded_boards: bool
) -> Iterator[str]:
  """The session's name and date, its key, any caveat, then a blank."""
  # A date left unread is named rather than left blank, for the reason the `?…?`
  # marks exist: it should not read as a session that was never dated.
  date = session.date.isoformat() if session.date else 'date not read'
  yield f'{session.event} — {date}'

  # Assigned at ingest, so a session that has only been parsed has no key to
  # name yet.
  if session.session_key:
    yield session.session_key

  # Only a pairs game publishes a traveller, so a teams session has no
  # double-dummy analysis to set against, and never will; a session that
  # reconciliation has not yet reached has none for now. The record cannot tell
  # the two apart, so the line states what they share rather than guessing. Left
  # unsaid, an absent column would read as a session whose every board came out
  # even.
  if has_recorded_boards and not session.source.travellers:
    yield 'No traveller has reached this session; nothing to compare against.'

  yield ''


def _board_lines(
  boards: Sequence[Board],
  comparisons: Mapping[int, double_dummy_comparison.BoardComparison],
) -> Iterator[str]:
  """The boards that recorded something, as one aligned line each."""
  if not boards:
    yield 'This session recorded no boards.'
    return
  yield from _laid_out(
    [_columns_for(board, comparisons).cells for board in boards]
  )


def _recap_lines(recap: double_dummy_comparison.SessionRecap) -> Iterator[str]:
  """The session's comparisons totalled, as a small table under the boards.

  Every row is one of our own seats, because both halves are organized by our
  position: which of us declared, and which of us led. A session nothing could
  be compared for gets no recap at all — the header has already said why.
  """
  if not recap.whole_session.boards:
    return

  yield ''
  rows: list[Sequence[str]] = [('', 'boards', 'DD', 'PLAY')]
  rows.extend(_half_rows('declaring', recap.declaring))
  rows.extend(_half_rows('defending', recap.defending))
  rows.append(_recap_row('whole session', recap.whole_session))
  yield from _laid_out(rows)

  # Totalling the two columns over different boards would leave them
  # incomparable, so a board carrying only one count sits out — worth saying,
  # since the totals then no longer add up the column printed above.
  if recap.partly_compared:
    board_or_boards = 'board' if recap.partly_compared == 1 else 'boards'
    yield (
      f'({recap.partly_compared} {board_or_boards} carried only one of the two '
      f'counts, and so sat out of these totals.)'
    )


def _half_rows(
  role: str, half: double_dummy_comparison.RecapHalf
) -> Iterator[Sequence[str]]:
  """One half of the recap: its own total, then the seats we sat it from.

  The seats are indented under the total rather than listed beside it, because
  they divide it — the rows below any total add up to it. A half we played no
  board in is left out entirely instead of printing a row of zeroes.
  """
  if not half.by_seat:
    return

  yield _recap_row(role, half.total)
  for seat, totals in half.by_seat.items():
    # `as E` reads under either heading: the seat we declared from, or the seat
    # we led from. Naming the seat alone is what keeps the table organized by
    # our own position rather than by the table's.
    yield _recap_row(f'  as {seat}', totals)


def _recap_row(
  label: str, totals: double_dummy_comparison.ComparisonTotals
) -> Sequence[str]:
  """One recap row's cells: what it covers, how many boards, and the totals."""
  return (
    label,
    str(totals.boards),
    f'{totals.whole_deal:+d}',
    f'{totals.after_lead:+d}',
  )


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
  double_dummy: str
  play: str

  @property
  def cells(self) -> Sequence[str]:
    """The columns in the order they are printed."""
    return (
      self.number,
      self.auction,
      self.contract,
      self.lead,
      self.matchpoints,
      self.double_dummy,
      self.play,
    )


def _laid_out(rows: Sequence[Sequence[str]]) -> Iterator[str]:
  """Pad every column to its widest value, so the rows read as a table.

  A trailing column that every row left empty is stripped rather than padded, so
  a session where no traveller has landed yet does not print a page of trailing
  whitespace.
  """
  column_count = len(rows[0])
  widths = [
    max(len(row[column]) for row in rows) for column in range(column_count)
  ]
  for row in rows:
    padded = (
      cell.ljust(width) for cell, width in zip(row, widths, strict=True)
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


def _columns_for(
  board: Board,
  comparisons: Mapping[int, double_dummy_comparison.BoardComparison],
) -> _BoardColumns:
  """One board's columns, each empty where nothing was recorded or compared."""
  # A board whose number went unread reaches no traveller row, and so has no
  # comparison waiting for it under any key.
  schedule = board.number.schedule
  compared = comparisons.get(schedule.number) if schedule else None
  return _BoardColumns(
    number=_spell_number(board.number),
    auction=_spell_auction(board.auction),
    contract=_spell_outcome(board.outcome),
    lead=_spell_lead(board.opening_lead),
    matchpoints=_spell_matchpoints(board.matchpoints),
    double_dummy=_spell_gain('DD', compared.whole_deal if compared else None),
    play=_spell_gain('PLAY', compared.after_lead if compared else None),
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


def _spell_gain(label: str, tricks_gained: int | None) -> str:
  """What our side gained on one of the counts, as a signed trick count.

  Every value carries its sign, `+0` included, so that a column reads as a
  comparison rather than as a stray count of tricks. Empty where no comparison
  could be made — `double_dummy_comparison` says what leaves one unmade.
  """
  # A board that came out exactly even gained zero, so a column is filled on a
  # stated value rather than on a truthy one.
  if tricks_gained is None:
    return ''
  return f'{label}{tricks_gained:+d}'


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
  if records:
    return _transcribe(records, _private_tree_if_any())

  try:
    tree = discover_private_tree()
  except (FileNotFoundError, RuntimeError) as error:
    print(f'could not find the stored sessions: {error}', file=sys.stderr)
    return 1

  stored = _stored_records(tree)
  if not stored:
    print('No sessions have been digitized yet.', file=sys.stderr)
    return 1
  return _transcribe(stored, tree)


def _transcribe(records: Sequence[Path], tree: PrivateTree | None) -> int:
  """Print each record's transcript, and return the command's exit status."""
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
    for line in render_session(session, _travellers_for(session, tree)):
      print(line)
  return status


def _private_tree_if_any() -> PrivateTree | None:
  """The private tree beside this checkout, or None where there is none.

  A record named on the command line is transcribed wherever it sits, so having
  no tree is not fatal on that path. It costs only the double-dummy comparison,
  and `_travellers_for` says so on standard error when a session named
  travellers.
  """
  try:
    return discover_private_tree()
  except (FileNotFoundError, RuntimeError):
    return None


def _travellers_for(
  session: Session, tree: PrivateTree | None
) -> Sequence[Traveller]:
  """The stored travellers a session names, with any trouble on standard error.

  A session naming none needs no tree at all, which is what lets a record handed
  over by path be transcribed outside the private tree entirely. One that does
  name travellers and has no tree to read them from is complained about rather
  than left to print as a session nothing could be compared for.
  """
  if not session.source.travellers:
    return ()

  if not tree:
    print(
      f'{session.event}: no private tree beside this checkout, so the '
      f'travellers this session names went unread',
      file=sys.stderr,
    )
    return ()

  read = double_dummy_comparison.read_referenced_travellers(tree, session)
  for issue in read.issues:
    print(issue.message, file=sys.stderr)
  return read.value


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
