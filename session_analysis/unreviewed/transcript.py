# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Reading a digitized session back, in the shorthand it was written in.

The pipeline stores each session as a JSON record, which a program reads easily
and a player does not. This module renders the record as a transcript for the
player: a summary of how the session went, a line per board, and a table for
working out what the session could have scored.

Its shape follows its use. The whole transcript is pasted into an email to a
partner, with comments added under the boards they concern, and the board lines
are pasted into a spreadsheet. Those two uses take two layouts, plain text and
the web page `--page` opens, and `transcript_layout` lays the one transcript
built here out either way.

The board lines are in the sheet's own notation, rather than a canonical prose
spelling. Whoever wrote the sheet already reads its shorthand fluently, so a
board comes back as they wrote it, here with its columns spaced for reading:

```text
#2    1C (2C) (2H) 3C (3H) DBL 4C*E-4    lead=KoH    MP=0    DD+1    PLAY+1
```

Opponents' calls sit in parentheses, standing in for the circles the sheet draws
around them. The auction runs straight on into the contract cell: where its
final bid is the contract, the cell adds only what the bid leaves out — the
doubling, the declarer and the result — so a final double is written once, as
the contract's `*`. The result counts tricks beyond book, the convention spec.md
`#notation` settles.

The transcript deliberately leaves out two kinds of annotation that the record
keeps. One is for coming back to a board later: a circled board number, the
notes column, and a box around a call, the lead or the contract. The other
explains a call's meaning: an alert mark and a written announcement.

What no transcript can show is who sat where. Passes usually go unwritten, so
the seat rotation cannot be replayed from the tokens and even the opening side
is ambiguous — which is why the declarer is not derived anywhere in this project
(models.md `#validation`). The circle convention survives that gap: it says
whether a call was ours or theirs, and that is as fine a distinction as the
record supports. Nor does any record say which partner took which seat, so the
summary names seats where a reader would want players.

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
`double_dummy_comparison` argues. Declaring, `PLAY` never exceeds `DD`, so `DD+1
PLAY-1` is an opening lead that handed us two tricks, one of which the play gave
back. Defending, `PLAY` never falls below `DD`, so `DD-1 PLAY+1` is a lead of
ours that cost two tricks, of which the defense won one back — still a trick
down on what the deal offered, not recovered from.

The published cell comes from a traveller, and the deal the solved count needs
is written onto the board from one at reconciliation. So both columns stand
empty for a board no traveller reached, and are absent altogether from a session
none has reached — `double_dummy_comparison` carries what their silences mean.

The summary above the boards totals the matchpoints and both columns over the
groups `session_summary` defines. The table below them lists each board's
contract and score twice, under `Actual` and `Can Do`, beside an empty `Action`,
so that the reader can fill in what a better action would have scored. The line
above that table leaves blanks, in square brackets, for where the better score
would have placed.
"""

import argparse
import dataclasses
import sys
import tempfile
import webbrowser
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from session_analysis import notation
from session_analysis.enums import CallKind, Penalty, Rank, Strain
from session_analysis.models import (
  AuctionEntry,
  Board,
  BoardNumber,
  Call,
  Card,
  Contract,
  Lead,
  Outcome,
  Passout,
  PlayedContract,
  Session,
)
from session_analysis.private_paths import PrivateTree, discover_private_tree
from session_analysis.travellers import Traveller
from session_analysis.unreviewed import (
  double_dummy_comparison,
  session_summary,
)
from session_analysis.unreviewed.transcript_layout import (
  Alignment,
  Block,
  FullWidthRow,
  Paragraph,
  Placeholder,
  Table,
  TableRow,
  as_plain_text,
  as_web_page,
)

# How a call that is not a bid is written. A bid is spelled from its own level
# and strain instead.
_CALL_SPELLINGS: Mapping[CallKind, str] = {
  CallKind.PASS: 'PASS',
  CallKind.DOUBLE: 'DBL',
  CallKind.REDOUBLE: 'RDBL',
}

# The doubling a double or redouble in the auction leaves the contract at.
_PENALTY_BY_CALL: Mapping[CallKind, Penalty] = {
  CallKind.DOUBLE: Penalty.DOUBLED,
  CallKind.REDOUBLE: Penalty.REDOUBLED,
}

# A strain as the sheet writes one, every spelling a single character. The
# canonical notrump is `NT`, which the sheet shortens to `N` — the spelling
# `notation.STRAIN_BY_LETTER` reads back either way. Keeping it one character
# wide is what stops a written contract running its parts together illegibly:
# `3NS` separates into a level, a strain and a declarer where `3NTS` does not.
_STRAIN_LETTERS: Mapping[Strain, str] = {
  Strain.CLUBS: 'C',
  Strain.DIAMONDS: 'D',
  Strain.HEARTS: 'H',
  Strain.SPADES: 'S',
  Strain.NOTRUMP: 'N',
}

# The same, with each suit drawn as its symbol, for the table a reader scans
# down rather than reads along.
_STRAIN_SYMBOLS: Mapping[Strain, str] = {
  Strain.CLUBS: '♣',
  Strain.DIAMONDS: '♦',
  Strain.HEARTS: '♥',
  Strain.SPADES: '♠',
  Strain.NOTRUMP: 'N',
}

# The mark a contract's doubling trails, as the sheet writes it — the same
# spelling models.md's own worked example uses (`6H*W-1`).
_PENALTY_MARKS: Mapping[Penalty, str] = {
  Penalty.NONE: '',
  Penalty.DOUBLED: '*',
  Penalty.REDOUBLED: '**',
}

# Scores and percentages are printed to the hundredth, rounding a half up the
# way a reader rounding by hand would: 17 of 32 is 53.13%, not banker's 53.12%.
_HUNDREDTHS = Decimal('0.01')


def transcript_of(
  session: Session, travellers: Sequence[Traveller] = ()
) -> Sequence[Block]:
  """The whole of one session, as blocks `transcript_layout` lays out.

  `travellers` are the captures reconciliation joined to this session, and carry
  the matchpoint tops and the analysis the double-dummy columns compare each
  result with. They are passed in rather than read here so that rendering stays
  a pure function of what it is handed;
  `double_dummy_comparison.read_referenced_travellers` is what reads them off
  disk.
  """
  played = [board for board in session.boards if _was_played(board)]
  header = _header(session, has_played_boards=bool(played))
  if not played:
    return (header, Paragraph(('This session recorded no boards.',)))

  comparisons = double_dummy_comparison.compare_boards(session, travellers)
  summary = session_summary.summarize(played, travellers, comparisons)
  return (
    header,
    *_error_lines(summary),
    *_summary_blocks(summary),
    Paragraph(('Please see below . .',)),
    Paragraph(('_____________',)),
    _board_table(played, comparisons),
    *_could_have_blocks(played, summary),
  )


def render_session(
  session: Session, travellers: Sequence[Traveller] = ()
) -> Iterator[str]:
  """The transcript of one session as plain text, a line at a time."""
  return as_plain_text(transcript_of(session, travellers))


def _header(session: Session, *, has_played_boards: bool) -> Paragraph:
  """The session's name and date, then any caveat about the whole of it."""
  lines = [_session_title(session)]

  # A session no traveller has reached has no double-dummy analysis to compare
  # its results against — whether its game published no traveller, or
  # reconciliation has not yet run on it. The record cannot tell the two apart,
  # so the line states what they share rather than guessing. Left unsaid, an
  # absent column would read as a session whose every board came out even.
  if has_played_boards and not session.source.travellers:
    lines.append(
      'No traveller has reached this session; nothing to compare against.'
    )
  return Paragraph(tuple(lines))


def _session_title(session: Session) -> str:
  """The session's name and date, as one line."""
  # A date left unread is named rather than left blank, for the reason the `?…?`
  # marks exist: it should not read as a session that was never dated.
  date = session.date.isoformat() if session.date else 'date not read'
  return f'{session.event} — {date}'


def _was_played(board: Board) -> bool:
  """Whether the board's row records anything beyond its number.

  A form prints more rows than most sessions fill, and a sheet's last rows often
  carry a board number and nothing else: rows nobody reached. Such a board is
  stored like any other — nothing is garbage — but it was not played, and a line
  for it would read as one that was. A board played and otherwise left blank
  still has whatever matchpoints a traveller gave it.
  """
  return bool(
    board.auction
    or board.opening_lead
    or board.outcome
    or board.matchpoints is not None
  )


def _error_lines(summary: session_summary.SessionSummary) -> Iterator[Block]:
  """A line per seat of ours for the reader to count that player's errors on.

  Left for the reader to fill in, since no record holds what a player judges
  their own errors to have been.
  """
  if summary.seats:
    yield Paragraph(tuple(f'{seat} error =' for seat in summary.seats))


def _summary_blocks(summary: session_summary.SessionSummary) -> Iterator[Block]:
  """The session's totals as a table, its caveats, and the matchpoint top.

  The table runs a section per role and then the net, a blank line between. A
  role's section opens on its total, and the rows below break that total down by
  which of us was in play, each indented a little and led by a dot. A session
  nothing could be scored or compared for gets no table at all — its header has
  already said why.

  Every row puts its numbers first and its words last, and labels its numbers in
  their cells rather than under a heading. A tab lines a column up only where
  all its values end between the same two tab stops, which numbers this short do
  in nearly any font and a heading such as `hands` does not. The indent leaves a
  percentage within its stop in a proportional font. A terminal's stops sit
  closer, and there an indented row's later columns slip one stop right.
  """
  whole = summary.whole_session
  if not whole.scored and not whole.compared:
    return

  columns = _SummaryColumns(
    has_matchpoints=bool(whole.scored), has_counts=bool(whole.compared)
  )
  sections: list[list[TableRow]] = []
  # A role we played no board in is left out entirely, rather than printing a
  # row of zeroes.
  if summary.declaring:
    total = summary.declaring_total
    sections.append(
      [
        columns.cells(total, f'We declared {_spell_hand_count(total.boards)}'),
        *(
          columns.breakdown_cells(totals, f'{seat} played {totals.boards}')
          for seat, totals in summary.declaring.items()
        ),
      ]
    )
  if summary.defending:
    total = summary.defending_total
    sections.append(
      [
        columns.cells(total, f'We defended {_spell_hand_count(total.boards)}'),
        *(
          columns.breakdown_cells(totals, f'{seat} on lead for {totals.boards}')
          for seat, totals in summary.defending.items()
        ),
      ]
    )
  sections.append(
    [columns.cells(whole, f'Net, across {_spell_hand_count(whole.boards)}')]
  )

  # The blank row stays inside the one table, so that the columns still line up
  # on the web page from one section to the next.
  rows: list[TableRow] = []
  for index, section in enumerate(sections):
    if index:
      rows.append(FullWidthRow(''))
    rows.extend(section)
  yield Table(alignments=columns.alignments(), rows=tuple(rows))

  notes = tuple(_summary_notes(summary, columns))
  if notes:
    yield Paragraph(notes)
  if summary.tops:
    yield Paragraph((f'TOP={_spell_tops(summary.tops)}',))


@dataclasses.dataclass(frozen=True)
class _SummaryColumns:
  """Which measures the summary prints, and each row's cells for them.

  A measure no board could supply is left out as a column, rather than printed
  empty all the way down: a teams game has no matchpoints at all, and a session
  whose traveller published no hands has no double-dummy counts.
  """

  has_matchpoints: bool
  # Both double-dummy counts, which are printed together or not at all.
  has_counts: bool

  def alignments(self) -> tuple[Alignment, ...]:
    """Every column left-aligned, so that an indented row shows its indent."""
    return (Alignment.LEFT,) * len(self.cells(session_summary.Totals(), ''))

  def cells(
    self, totals: session_summary.Totals, label: str
  ) -> tuple[str, ...]:
    """One row: each measure's total, then words saying what it covers."""
    matchpoints = (
      (_spell_percentage(totals.percentage),) if self.has_matchpoints else ()
    )
    counts = (
      (
        _spell_gain('DD', totals.whole_deal),
        _spell_gain('PLAY', totals.after_lead),
      )
      if self.has_counts
      else ()
    )
    return (*matchpoints, *counts, label)

  def breakdown_cells(
    self, totals: session_summary.Totals, label: str
  ) -> tuple[str, ...]:
    """A row breaking a total down: indented two spaces, its label led by a dot.

    The spaces sit inside the first cell, where the web page's `pre` cells keep
    them as well.
    """
    first, *rest = self.cells(totals, f'· {label}')
    return (f'  {first}', *rest)


def _summary_notes(
  summary: session_summary.SessionSummary, columns: _SummaryColumns
) -> Iterator[str]:
  """A line for each way the totals leave boards out, where any did.

  Worth saying, because a total over fewer hands than its label counts no longer
  matches the board lines printed below it.
  """
  whole = summary.whole_session
  unscored = whole.boards - whole.scored
  if columns.has_matchpoints and unscored:
    yield (
      f'({_spell_hand_count(unscored)} had no matchpoints, or no top to '
      f'score them against, and sat out of the percentages.)'
    )
  uncompared = whole.boards - whole.compared
  if columns.has_counts and uncompared:
    yield (
      f'({_spell_hand_count(uncompared)} had only one double-dummy count or '
      f'none, and sat out of DD and PLAY.)'
    )
  if summary.unplaced:
    yield (
      f'({_spell_hand_count(summary.unplaced)} had no seat of ours to go '
      f'under, and sat out of everything but the net.)'
    )


def _spell_hand_count(count: int) -> str:
  """A count of hands played, as `1 hand` or `3 hands`."""
  return f'{count} hand' if count == 1 else f'{count} hands'


def _spell_tops(tops: Sequence[Decimal]) -> str:
  """The tops boards were scored against: one, or the range they spanned."""
  if len(tops) == 1:
    return _plain_number(tops[0])
  return f'{_plain_number(tops[0])}-{_plain_number(tops[-1])}'


def _plain_number(value: Decimal) -> str:
  """A number without trailing zeroes or an exponent: `8`, not `8.0`."""
  return format(value.normalize(), 'f')


def _spell_percentage(percentage: Decimal | None) -> str:
  """A share of the top to the hundredth, as `46.09%`; empty if unscored."""
  if percentage is None:
    return ''
  return f'{percentage.quantize(_HUNDREDTHS, rounding=ROUND_HALF_UP)}%'


def _board_table(
  boards: Sequence[Board],
  comparisons: Mapping[int, double_dummy_comparison.BoardComparison],
) -> Table:
  """The boards as one table, a line apiece.

  Nothing sits between two boards, so that the lines paste into a spreadsheet as
  a solid block of rows. A reader commenting on a board adds the lines under it
  as they go.
  """
  return Table(
    alignments=(Alignment.LEFT,) * 6,
    rows=tuple(_board_cells(board, comparisons) for board in boards),
  )


def _board_cells(
  board: Board,
  comparisons: Mapping[int, double_dummy_comparison.BoardComparison],
) -> tuple[str, ...]:
  """One board's line, a cell empty where nothing was recorded or compared."""
  # A board whose number went unread reaches no traveller row, and so has no
  # comparison waiting for it under any key.
  schedule = board.number.schedule
  compared = comparisons.get(schedule.number) if schedule else None
  return (
    _spell_number(board.number, prefix='#'),
    _spell_bidding(board),
    _spell_lead(board.opening_lead),
    _spell_matchpoints(board.matchpoints),
    _spell_gain('DD', compared.whole_deal if compared else None),
    _spell_gain('PLAY', compared.after_lead if compared else None),
  )


def _could_have_blocks(
  boards: Sequence[Board], summary: session_summary.SessionSummary
) -> Iterator[Block]:
  """The table for working out what the session could have scored.

  `Can Do` starts out as the score each board actually got, and `Action` empty,
  for the reader to revise. A session with no matchpoints has nothing to revise,
  and gets no table.
  """
  if not summary.whole_session.scored:
    return

  yield Paragraph(('Here is what we could have done . .',))
  # Where the revised score would have placed, for the reader to fill in from
  # the club's standings.
  standing = (
    Placeholder('place overall'),
    ' and ',
    Placeholder('place in strat'),
    ' earning ',
    Placeholder('points'),
    ' masterpoints',
  )
  yield Paragraph((standing,))

  # In a proportional font these headings overrun a tab stop, so in plain text
  # the header row drifts right of the columns beneath it. That is accepted: the
  # body rows still line up, and the web page's table is exact.
  rows: list[TableRow] = [('Board', '', 'Actual', 'Can Do', 'Action')]
  for board in boards:
    score = _spell_score(board.matchpoints)
    rows.append(
      (
        _spell_number(board.number),
        _spell_outcome(board.outcome, _STRAIN_SYMBOLS),
        score,
        score,
        '',
      )
    )
  average = _spell_percentage(summary.whole_session.percentage)
  # Labelled in the contract's column, which is as wide as the label, so that in
  # plain text the averages reach the same tab stop as the scores above.
  rows.append(('', 'AVERAGE', average, average, ''))
  yield Table(
    alignments=(
      Alignment.RIGHT,
      Alignment.CENTER,
      Alignment.RIGHT,
      Alignment.RIGHT,
      Alignment.RIGHT,
    ),
    rows=tuple(rows),
  )


def _spell_number(number: BoardNumber, *, prefix: str = '') -> str:
  """The board number, or its transcription where it went unread."""
  if not number.schedule:
    return _unreadable(number.raw)
  return f'{prefix}{number.schedule.number}'


def _spell_bidding(board: Board) -> str:
  """The auction run on into the contract cell, as one cell of the line.

  Where the auction visibly ends in the contract, the cell adds only what the
  final bid leaves out, joined onto it: `4S (5C)` and `5CN-1` read `4S (5C)N-1`.
  Anywhere else — a passed-out board, an auction left unfinished, a contract
  cell disagreeing with the auction — the two are written out in full, side by
  side, so that nothing either recorded goes unseen.
  """
  resolution = board.outcome.resolution if board.outcome else None
  if isinstance(resolution, PlayedContract):
    final_bid = _final_bid_position(board.auction, resolution.contract)
    if final_bid is not None:
      calls = ' '.join(
        _spell_entry(entry) for entry in board.auction[: final_bid + 1]
      )
      return calls + _contract_suffix(resolution)

  spelled = (
    _spell_auction(board.auction),
    _spell_outcome(board.outcome, _STRAIN_LETTERS),
  )
  return ' '.join(part for part in spelled if part)


def _final_bid_position(
  auction: Sequence[AuctionEntry], contract: Contract
) -> int | None:
  """Where the auction bids the contract, if it visibly ends there.

  Only passes, doubles and redoubles may follow that bid. A double the auction
  shows must be the one the contract cell records: one the auction leaves out is
  merely unwritten, but one contradicting the cell is a disagreement worth
  seeing. An unread call could be anything, the final bid included, so it stops
  the search too.
  """
  stated: Penalty | None = None
  for position in reversed(range(len(auction))):
    call = auction[position].call
    if not call:
      return None
    if call.kind == CallKind.BID:
      if (call.level, call.strain) != (contract.level, contract.strain):
        return None
      if stated and stated != contract.penalty:
        return None
      return position
    # Walking back, the first double or redouble met is the one that stands.
    if not stated:
      stated = _PENALTY_BY_CALL.get(call.kind)
  return None


def _spell_auction(entries: Sequence[AuctionEntry]) -> str:
  """The auction as one space-separated run of calls."""
  return ' '.join(_spell_entry(entry) for entry in entries)


def _spell_entry(entry: AuctionEntry) -> str:
  """One written call, in parentheses when it was the opponents'."""
  call = _spell_call(entry.call) if entry.call else None
  # An unparsed token has no parse to spell from, so its raw transcription
  # stands as written, alert mark included.
  spelled = call or _unreadable(entry.raw)
  return _circled(spelled, entry.by_opponents)


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
  return f'{call.level}{_STRAIN_LETTERS[call.strain]}'


def _spell_outcome(
  outcome: Outcome | None, strains: Mapping[Strain, str]
) -> str:
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
    f'{contract.level}{strains[contract.strain]}{_contract_suffix(resolution)}'
  )


def _contract_suffix(played: PlayedContract) -> str:
  """What a contract cell says beyond its bid: doubling, declarer and result."""
  contract = played.contract
  return (
    f'{_PENALTY_MARKS[contract.penalty]}{contract.declarer}'
    f'{_spell_result(contract.level, played.result.tricks_taken)}'
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


def _spell_score(matchpoints: float | None) -> str:
  """Our matchpoints on the board to the hundredth, as `7.50`, or empty."""
  if matchpoints is None:
    return ''
  # The float's shortest spelling is the value its source printed, so it rounds
  # as printed rather than as the nearest binary fraction.
  exact = Decimal(str(matchpoints))
  return str(exact.quantize(_HUNDREDTHS, rounding=ROUND_HALF_UP))


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


def _show_page(page: str) -> None:
  """Write a web page to a file of its own, and open it in the browser."""
  # Kept after this process exits, since the browser reads it only afterward;
  # the system clears it away with its other temporary files.
  with tempfile.NamedTemporaryFile(
    'w', encoding='utf-8', prefix='transcript-', suffix='.html', delete=False
  ) as file:
    file.write(page)
  path = Path(file.name)
  # Named on standard error, so the page can be found again — or opened by hand
  # where no browser could be.
  print(f'wrote {path}', file=sys.stderr)
  webbrowser.open(path.as_uri())


def main(
  argv: Sequence[str] | None = None,
  *,
  show_page: Callable[[str], None] = _show_page,
) -> int:
  """Transcribe each session record named, or every stored one.

  Prints the transcripts as plain text, or with `--page` hands them to
  `show_page` as one web page instead.

  Returns:
    The exit status: non-zero if any record could not be read, so a run that
    skipped one is distinguishable from one that transcribed everything asked
    of it.
  """
  arguments = _parse_args(argv)
  records: Sequence[Path] = arguments.records
  tree: PrivateTree | None
  if records:
    tree = _private_tree_if_any()
  else:
    try:
      tree = discover_private_tree()
    except (FileNotFoundError, RuntimeError) as error:
      print(f'could not find the stored sessions: {error}', file=sys.stderr)
      return 1
    records = _stored_records(tree)
    if not records:
      print('No sessions have been digitized yet.', file=sys.stderr)
      return 1

  sessions = [
    session for record in records if (session := _read_session(record))
  ]
  status = 0 if len(sessions) == len(records) else 1
  # Built lazily, so that plain text prints each session as soon as it is
  # transcribed, rather than all of them at the end.
  transcripts = (
    transcript_of(session, _travellers_for(session, tree))
    for session in sessions
  )
  if not arguments.page:
    _print_transcripts(transcripts)
  elif sessions:
    title = _session_title(sessions[0]) if len(sessions) == 1 else 'Transcripts'
    show_page(as_web_page(title, list(transcripts)))
  return status


def _print_transcripts(transcripts: Iterable[Sequence[Block]]) -> None:
  """Print each transcript as plain text, a blank line between two."""
  for index, transcript in enumerate(transcripts):
    if index:
      print()
    for line in as_plain_text(transcript):
      print(line)


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
  """Parse the command line: which session records to transcribe, and how."""
  parser = argparse.ArgumentParser(
    description='Transcribe a digitized session: a summary, a line per board '
    'in the shorthand the scoresheet itself was written in, and a table for '
    'working out what the session could have scored.'
  )
  parser.add_argument(
    'records',
    nargs='*',
    type=Path,
    help='the session records to transcribe; every stored session by default',
  )
  parser.add_argument(
    '--page',
    action='store_true',
    help='open the transcripts as a web page, whose tables keep their columns '
    'lined up when pasted into an email, instead of printing them',
  )
  return parser.parse_args(argv)


if __name__ == '__main__':
  sys.exit(main())
