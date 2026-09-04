# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for reading a digitized session back as plain text.

Rendering is pure, so every test here builds its session in memory and asserts
on the lines that come out. Most assert on one board's line alone, which
`_board_line` pulls off the end of a one-board transcript — the marks a call or
a contract cell carries are what those tests are about, not the table around
them.

The command is the exception, and it reads real files under `tmp_path`: what it
is for is finding records on disk, so a stream would test something else.
"""

import datetime
from collections.abc import Sequence
from pathlib import Path

import pytest

from session_analysis.enums import (
  CallKind,
  Direction,
  IssueSeverity,
  Penalty,
  Rank,
  Strain,
  Suit,
  Vulnerability,
)
from session_analysis.models import (
  AuctionEntry,
  Board,
  BoardNumber,
  Call,
  Card,
  Contract,
  Issue,
  Lead,
  Outcome,
  Passout,
  PlayedContract,
  Result,
  Schedule,
  Session,
)
from session_analysis.testing import provenance
from session_analysis.unreviewed.transcript import main, render_session


def _make_number(number: int) -> BoardNumber:
  """A board-number cell that parsed.

  The transcript reads the number alone, so the dealer and vulnerability the
  number also fixes are left at a constant rather than computed.
  """
  return BoardNumber(
    raw=str(number),
    schedule=Schedule(
      number=number,
      dealer=Direction.NORTH,
      vulnerability=Vulnerability.NONE,
    ),
  )


def _make_bid(
  level: int,
  strain: Strain,
  *,
  by_opponents: bool = False,
  alerted: bool = False,
  flagged_for_discussion: bool = False,
) -> AuctionEntry:
  """A bid that parsed, carrying whatever marks the sheet put on it."""
  return AuctionEntry(
    raw=f'{level}{strain}',
    by_opponents=by_opponents,
    alerted=alerted,
    flagged_for_discussion=flagged_for_discussion,
    call=Call(kind=CallKind.BID, level=level, strain=strain),
  )


def _make_call(kind: CallKind, *, by_opponents: bool = False) -> AuctionEntry:
  """A pass, double, or redouble that parsed."""
  return AuctionEntry(
    raw=kind.value, by_opponents=by_opponents, call=Call(kind=kind)
  )


def _make_unread_call(raw: str) -> AuctionEntry:
  """A token the parser could not understand, as the sheet wrote it."""
  return AuctionEntry(
    raw=raw,
    issues=(
      Issue(
        code='unparseable_call',
        severity=IssueSeverity.HIGH,
        message=f'could not parse call: {raw!r}',
      ),
    ),
  )


def _make_outcome(
  level: int,
  strain: Strain,
  declarer: Direction,
  tricks_taken: int,
  *,
  penalty: Penalty = Penalty.NONE,
) -> Outcome:
  """A contract cell that parsed into a contract and its result."""
  return Outcome(
    raw=f'{level}{strain}{declarer}',
    resolution=PlayedContract(
      contract=Contract(
        level=level, strain=strain, declarer=declarer, penalty=penalty
      ),
      result=Result(tricks_taken=tricks_taken),
    ),
  )


def _make_unread_outcome(raw: str) -> Outcome:
  """A contract cell the parser could not understand."""
  return Outcome(
    raw=raw,
    issues=(
      Issue(
        code='unparseable_contract',
        severity=IssueSeverity.HIGH,
        message=f'could not parse contract: {raw!r}',
      ),
    ),
  )


def _make_lead(rank: Rank, suit: Suit) -> Lead:
  """An opening-lead cell that parsed into a card."""
  return Lead(raw=f'{rank}{suit}', card=Card(rank=rank, suit=suit))


def _make_board(
  number: int = 5,
  *,
  auction: Sequence[AuctionEntry] = (),
  outcome: Outcome | None = None,
  opening_lead: Lead | None = None,
  matchpoints: float | None = None,
) -> Board:
  """A board carrying only the cells a test is asserting on."""
  return Board(
    number=_make_number(number),
    auction=tuple(auction),
    outcome=outcome,
    opening_lead=opening_lead,
    matchpoints=matchpoints,
  )


def _make_session(
  *boards: Board,
  event: str = 'Monday Pairs',
  date: datetime.date | None = datetime.date(2026, 6, 29),
  session_key: str | None = 'pabc-mon-2026-06-29',
) -> Session:
  """A digitized session, with stand-in provenance nothing here reads."""
  return Session(
    session_key=session_key,
    event=event,
    date=date,
    source=provenance.sheet_source(),
    boards=boards,
  )


def _board_line(board: Board) -> str:
  """The one board line a single-board session renders to.

  It is the last line of the transcript, so the header above it does not have to
  be counted.
  """
  return list(render_session(_make_session(board)))[-1]


# --- the auction, in the sheet's own marks ---


def test_a_bid_is_written_as_its_level_and_strain() -> None:
  board = _make_board(auction=[_make_bid(2, Strain.HEARTS)])

  assert '2H' in _board_line(board)


def test_a_notrump_bid_writes_its_strain_as_one_letter() -> None:
  board = _make_board(auction=[_make_bid(1, Strain.NOTRUMP)])

  # The canonical strain is `NT`; the sheet writes the `N` alone.
  assert _board_line(board) == '#5    1N'


def test_a_circled_call_is_written_in_parentheses() -> None:
  board = _make_board(
    auction=[
      _make_bid(1, Strain.CLUBS),
      _make_bid(1, Strain.DIAMONDS, by_opponents=True),
    ]
  )

  assert '1C (1D)' in _board_line(board)


def test_a_pass_double_and_redouble_are_spelled_out() -> None:
  board = _make_board(
    auction=[
      _make_call(CallKind.PASS),
      _make_call(CallKind.DOUBLE),
      _make_call(CallKind.REDOUBLE),
    ]
  )

  assert 'PASS DBL RDBL' in _board_line(board)


def test_an_alerted_call_keeps_its_alert_mark() -> None:
  board = _make_board(auction=[_make_bid(2, Strain.HEARTS, alerted=True)])

  assert '2H!' in _board_line(board)


def test_an_alert_mark_sits_inside_the_circle() -> None:
  board = _make_board(
    auction=[_make_bid(2, Strain.CLUBS, by_opponents=True, alerted=True)]
  )

  # The mark belongs to the call, and the circle to whose call it was.
  assert '(2C!)' in _board_line(board)


def test_a_call_that_did_not_parse_shows_its_transcription() -> None:
  board = _make_board(
    auction=[_make_bid(1, Strain.CLUBS), _make_unread_call('2Q')]
  )

  assert '1C ?2Q?' in _board_line(board)


def test_a_circled_call_that_did_not_parse_keeps_both_marks() -> None:
  entry = _make_unread_call('2Q').model_copy(update={'by_opponents': True})
  board = _make_board(auction=[entry])

  assert '(?2Q?)' in _board_line(board)


def test_a_boxed_span_is_written_as_one_pair_of_brackets() -> None:
  board = _make_board(
    auction=[
      _make_bid(1, Strain.CLUBS),
      _make_bid(2, Strain.NOTRUMP, flagged_for_discussion=True),
      _make_bid(3, Strain.CLUBS, flagged_for_discussion=True),
      _make_bid(3, Strain.NOTRUMP),
    ]
  )

  # The parser splits one drawn box into a flag per call; the span is put back
  # together here rather than bracketing each call of it.
  assert '1C [2N 3C] 3N' in _board_line(board)


def test_a_box_running_to_the_end_of_the_auction_is_closed() -> None:
  board = _make_board(
    auction=[
      _make_bid(1, Strain.CLUBS),
      _make_bid(2, Strain.CLUBS, flagged_for_discussion=True),
    ]
  )

  assert '1C [2C]' in _board_line(board)


# --- the contract cell ---


def test_a_contract_that_came_home_counts_tricks_beyond_book() -> None:
  board = _make_board(
    outcome=_make_outcome(4, Strain.CLUBS, Direction.WEST, tricks_taken=10)
  )

  # Ten tricks is book plus four, which is 4C making exactly.
  assert '4CW+4' in _board_line(board)


def test_an_overtrick_raises_the_count_beyond_book() -> None:
  board = _make_board(
    outcome=_make_outcome(4, Strain.SPADES, Direction.NORTH, tricks_taken=12)
  )

  assert '4SN+6' in _board_line(board)


def test_a_notrump_contract_writes_its_strain_as_one_letter() -> None:
  board = _make_board(
    outcome=_make_outcome(3, Strain.NOTRUMP, Direction.SOUTH, tricks_taken=9)
  )

  # One character wide is what keeps the declarer legible after the strain,
  # and nine tricks is book plus three, which is 3NT making exactly.
  assert '3NS+3' in _board_line(board)


def test_a_contract_that_failed_counts_the_tricks_it_fell_short() -> None:
  board = _make_board(
    outcome=_make_outcome(6, Strain.HEARTS, Direction.WEST, tricks_taken=11)
  )

  assert '6HW-1' in _board_line(board)


def test_a_doubled_contract_trails_one_mark() -> None:
  board = _make_board(
    outcome=_make_outcome(
      2,
      Strain.SPADES,
      Direction.SOUTH,
      tricks_taken=7,
      penalty=Penalty.DOUBLED,
    )
  )

  assert '2S*S-1' in _board_line(board)


def test_a_redoubled_contract_trails_two_marks() -> None:
  board = _make_board(
    outcome=_make_outcome(
      2,
      Strain.SPADES,
      Direction.SOUTH,
      tricks_taken=8,
      penalty=Penalty.REDOUBLED,
    )
  )

  assert '2S**S+2' in _board_line(board)


def test_a_passed_out_board_says_so() -> None:
  board = _make_board(outcome=Outcome(raw='---', resolution=Passout()))

  assert 'PASSED OUT' in _board_line(board)


def test_a_contract_cell_that_did_not_parse_shows_its_transcription() -> None:
  board = _make_board(outcome=_make_unread_outcome('4H W'))

  assert '?4H W?' in _board_line(board)


# --- the opening lead ---


def test_the_lead_is_labelled_and_written_with_its_of() -> None:
  board = _make_board(opening_lead=_make_lead(Rank.NINE, Suit.HEARTS))

  # The label and the `o` are what keep a lead from reading as a bid.
  assert 'lead=9oH' in _board_line(board)


def test_a_led_ten_is_written_with_both_its_digits() -> None:
  board = _make_board(opening_lead=_make_lead(Rank.TEN, Suit.SPADES))

  assert 'lead=10oS' in _board_line(board)


def test_a_lead_that_did_not_parse_shows_its_transcription() -> None:
  lead = Lead(
    raw='10oX',
    issues=(
      Issue(
        code='unparseable_lead',
        severity=IssueSeverity.MEDIUM,
        message="could not parse opening lead: '10oX'",
      ),
    ),
  )
  board = _make_board(opening_lead=lead)

  assert 'lead=?10oX?' in _board_line(board)


def test_a_lead_struck_through_is_not_marked_as_unread() -> None:
  # A struck-through cell records that no lead was played, which the parser
  # resolves to no card and no issue — it is not something it failed to read.
  board = _make_board(opening_lead=Lead(raw='---'))

  assert 'lead=---' in _board_line(board)


def test_a_board_with_no_lead_recorded_shows_none() -> None:
  board = _make_board(auction=[_make_bid(1, Strain.CLUBS)])

  assert 'lead=' not in _board_line(board)


# --- the board number and matchpoints ---


def test_a_board_number_leads_the_line() -> None:
  board = _make_board(7)

  assert _board_line(board).startswith('#7')


def test_a_board_number_that_did_not_parse_shows_its_transcription() -> None:
  number = BoardNumber(
    raw='B',
    issues=(
      Issue(
        code='unparseable_board_number',
        severity=IssueSeverity.HIGH,
        message="could not parse board number: 'B'",
      ),
    ),
  )
  board = Board(number=number, auction=(_make_bid(1, Strain.CLUBS),))

  assert _board_line(board).startswith('?B?')


def test_matchpoints_drop_a_whole_score_s_trailing_zero() -> None:
  board = _make_board(matchpoints=6.0)

  assert 'MP=6' in _board_line(board)


def test_matchpoints_keep_a_half_score() -> None:
  board = _make_board(matchpoints=4.5)

  assert 'MP=4.5' in _board_line(board)


def test_a_bottom_board_shows_its_zero() -> None:
  # Zero matchpoints is a score, not an absent one, so it has to print.
  board = _make_board(matchpoints=0.0)

  assert 'MP=0' in _board_line(board)


def test_a_board_no_traveller_has_reached_shows_no_matchpoints() -> None:
  board = _make_board(matchpoints=None)

  assert 'MP=' not in _board_line(board)


# --- the session header ---


def test_the_header_names_the_session_and_its_date() -> None:
  session = _make_session(_make_board())

  assert next(iter(render_session(session))) == 'Monday Pairs — 2026-06-29'


def test_the_header_carries_the_stored_session_key() -> None:
  session = _make_session(_make_board(), session_key='pabc-mon-2026-06-29')

  assert list(render_session(session))[1] == 'pabc-mon-2026-06-29'


def test_a_session_not_yet_ingested_has_no_key_to_name() -> None:
  session = _make_session(_make_board(), session_key=None)

  # The blank separating line takes the key's place.
  assert list(render_session(session))[1] == ''


def test_a_date_the_footer_did_not_yield_says_so() -> None:
  session = _make_session(_make_board(), date=None)

  assert next(iter(render_session(session))) == 'Monday Pairs — date not read'


# --- laying the boards out ---


def test_a_column_is_padded_to_its_widest_value() -> None:
  session = _make_session(
    _make_board(5, auction=[_make_bid(1, Strain.CLUBS)], matchpoints=6),
    _make_board(
      6,
      auction=[_make_bid(1, Strain.NOTRUMP), _make_bid(3, Strain.NOTRUMP)],
      matchpoints=4.5,
    ),
  )

  short_auction, long_auction = list(render_session(session))[-2:]

  # The shorter auction is padded out to the longer one, so both boards'
  # matchpoints start at the same column.
  assert short_auction.index('MP=') == long_auction.index('MP=')


def test_a_row_the_sheet_left_blank_is_not_transcribed() -> None:
  played = _make_board(5, auction=[_make_bid(1, Strain.CLUBS)])
  unused = Board(number=BoardNumber(raw=''))
  session = _make_session(played, unused)

  # The header's three lines plus the one board that recorded something.
  assert len(list(render_session(session))) == 4


def test_a_session_whose_every_row_was_blank_says_so() -> None:
  session = _make_session(Board(number=BoardNumber(raw='')))

  assert list(render_session(session))[-1] == 'This session recorded no boards.'


def test_a_line_carries_no_trailing_whitespace() -> None:
  session = _make_session(_make_board(5, auction=[_make_bid(1, Strain.CLUBS)]))

  assert [
    line for line in render_session(session) if line != line.rstrip()
  ] == []


# --- the command ---


def _write_record(directory: Path, session: Session) -> Path:
  """A session record on disk, named as the pipeline names one."""
  record = directory / f'{session.session_key}.json'
  record.write_text(session.model_dump_json())
  return record


def test_the_command_transcribes_a_record_it_is_given(
  tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
  session = _make_session(
    _make_board(
      5,
      auction=[_make_bid(1, Strain.CLUBS)],
      outcome=_make_outcome(4, Strain.CLUBS, Direction.WEST, tricks_taken=10),
    )
  )
  record = _write_record(tmp_path, session)

  status = main([str(record)])

  assert status == 0
  assert '#5    1C    4CW+4' in capsys.readouterr().out


def test_the_command_separates_two_records_with_a_blank_line(
  tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
  first = _write_record(
    tmp_path, _make_session(_make_board(), session_key='pabc-mon-2026-06-29')
  )
  second = _write_record(
    tmp_path, _make_session(_make_board(), session_key='pabc-mon-2026-07-06')
  )

  main([str(first), str(second)])

  assert '\n\nMonday Pairs' in capsys.readouterr().out


def test_the_command_reports_a_record_that_holds_no_session(
  tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
  record = tmp_path / 'broken.json'
  record.write_text('{"event": "Monday Pairs"}')

  status = main([str(record)])

  captured = capsys.readouterr()
  assert status == 1
  assert not captured.out
  assert 'no session record' in captured.err


def test_the_command_transcribes_the_records_it_can_read(
  tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
  broken = tmp_path / 'broken.json'
  broken.write_text('{"event": "Monday Pairs"}')
  readable = _write_record(tmp_path, _make_session(_make_board(5)))

  status = main([str(broken), str(readable)])

  captured = capsys.readouterr()
  # One unreadable record costs its own transcript, not the run's.
  assert status == 1
  assert '#5' in captured.out
