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
import itertools
from collections.abc import Iterable, Sequence
from pathlib import Path

import pytest

from session_analysis import notation
from session_analysis.enums import (
  CallKind,
  Direction,
  IssueSeverity,
  Penalty,
  Rank,
  Side,
  Strain,
  Suit,
  Vulnerability,
)
from session_analysis.models import (
  AuctionEntry,
  Board,
  BoardNumber,
  Call,
  CaptureReference,
  Card,
  Contract,
  Deal,
  Issue,
  Lead,
  Outcome,
  PairIdentity,
  Passout,
  PlayedContract,
  Result,
  Schedule,
  Session,
)
from session_analysis.testing import provenance
from session_analysis.testing.deals import a_deal_the_lead_decides
from session_analysis.travellers import (
  Traveller,
  TravellerBoard,
  TravellerSource,
)
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
  *,
  level: int,
  strain: Strain,
  declarer: Direction,
  tricks_taken: int,
  penalty: Penalty = Penalty.NONE,
  flagged_for_discussion: bool = False,
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
    flagged_for_discussion=flagged_for_discussion,
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
  our_side: Side | None = None,
  deal: Deal | None = None,
) -> Board:
  """A board carrying only the cells a test is asserting on.

  `our_side` fills the pair reconciliation would have placed us as, which the
  double-dummy column needs to tell a board we declared from one we defended. It
  stays absent for the tests about the rest of the line.
  """
  return Board(
    number=_make_number(number),
    auction=tuple(auction),
    outcome=outcome,
    opening_lead=opening_lead,
    matchpoints=matchpoints,
    our_pair=PairIdentity(number='3', side=our_side) if our_side else None,
    deal=deal,
  )


def _make_session(
  *boards: Board,
  event: str = 'Monday Pairs',
  date: datetime.date | None = datetime.date(2026, 6, 29),
  session_key: str | None = 'pabc-mon-2026-06-29',
  travellers: Sequence[CaptureReference] = (
    CaptureReference(path='club/D260629M.pbn'),
  ),
) -> Session:
  """A digitized session, with stand-in provenance nothing here reads.

  It names a traveller by default, as a reconciled session does, so that the
  header's no-traveller caveat stays out of the way of every test that is about
  something else. The tests about the caveat pass their own.
  """
  return Session(
    session_key=session_key,
    event=event,
    date=date,
    source=provenance.sheet_source(travellers=travellers),
    boards=boards,
  )


def _make_traveller(
  board_number: int, *, declarer: Direction, strain: Strain, tricks: int
) -> Traveller:
  """A traveller stating one cell of its table and leaving the other nineteen.

  A published table holds all twenty cells and writes as `None` any it has
  nothing to say about, so the nineteen no test asserts on are built that way
  rather than left out.
  """
  table: dict[Direction, dict[Strain, int | None]] = {
    seat: dict.fromkeys(notation.STRAINS_LOW_TO_HIGH) for seat in Direction
  }
  table[declarer][strain] = tricks
  return Traveller(
    source=TravellerSource.CLUB_PBN,
    reference=CaptureReference(path='club/D260629M.pbn'),
    event='Monday Pairs',
    boards=(TravellerBoard(number=board_number, double_dummy_tricks=table),),
  )


def _board_line(board: Board) -> str:
  """The one board line a single-board session renders to."""
  return _board_line_of(render_session(_make_session(board)))


def _board_line_of(lines: Iterable[str]) -> str:
  """The first board's line — the only one, in the sessions built here.

  Every test that reaches for this builds a single-board session, so the first
  board line is the only one.

  A transcript runs header, blank, boards, and then — where anything could be
  compared — a second blank and the recap. The line just past the header's blank
  is therefore the first board. Neither end of the transcript would do: the
  header sits above the boards and the recap below them. Nor would matching the
  `#` a board line usually opens with — a board number that did not parse writes
  its transcription there instead.
  """
  past_header = itertools.dropwhile(bool, lines)
  next(past_header)  # the blank line that closes the header
  return next(past_header)


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


def test_a_boxed_call_is_written_without_its_box() -> None:
  board = _make_board(
    auction=[
      _make_bid(1, Strain.CLUBS),
      _make_bid(2, Strain.NOTRUMP, flagged_for_discussion=True),
      _make_bid(3, Strain.CLUBS),
    ]
  )

  assert '1C 2N 3C' in _board_line(board)


# --- the contract cell ---


def test_a_contract_that_came_home_counts_tricks_beyond_book() -> None:
  board = _make_board(
    outcome=_make_outcome(
      level=4, strain=Strain.CLUBS, declarer=Direction.WEST, tricks_taken=10
    )
  )

  # Ten tricks is book plus four, which is 4C making exactly.
  assert '4CW+4' in _board_line(board)


def test_an_overtrick_raises_the_count_beyond_book() -> None:
  board = _make_board(
    outcome=_make_outcome(
      level=4, strain=Strain.SPADES, declarer=Direction.NORTH, tricks_taken=12
    )
  )

  assert '4SN+6' in _board_line(board)


def test_a_notrump_contract_writes_its_strain_as_one_letter() -> None:
  board = _make_board(
    outcome=_make_outcome(
      level=3, strain=Strain.NOTRUMP, declarer=Direction.SOUTH, tricks_taken=9
    )
  )

  # One character wide is what keeps the declarer legible after the strain, and
  # nine tricks is book plus three, which is 3NT making exactly.
  assert '3NS+3' in _board_line(board)


def test_a_contract_that_failed_counts_the_tricks_it_fell_short() -> None:
  board = _make_board(
    outcome=_make_outcome(
      level=6, strain=Strain.HEARTS, declarer=Direction.WEST, tricks_taken=11
    )
  )

  assert '6HW-1' in _board_line(board)


def test_a_doubled_contract_trails_one_mark() -> None:
  board = _make_board(
    outcome=_make_outcome(
      level=2,
      strain=Strain.SPADES,
      declarer=Direction.SOUTH,
      tricks_taken=7,
      penalty=Penalty.DOUBLED,
    )
  )

  assert '2S*S-1' in _board_line(board)


def test_a_redoubled_contract_trails_two_marks() -> None:
  board = _make_board(
    outcome=_make_outcome(
      level=2,
      strain=Strain.SPADES,
      declarer=Direction.SOUTH,
      tricks_taken=8,
      penalty=Penalty.REDOUBLED,
    )
  )

  assert '2S**S+2' in _board_line(board)


def test_a_boxed_contract_is_written_without_its_box() -> None:
  board = _make_board(
    outcome=_make_outcome(
      level=4,
      strain=Strain.HEARTS,
      declarer=Direction.WEST,
      tricks_taken=10,
      flagged_for_discussion=True,
    )
  )

  # Matched as a whole cell, since a bracketed [4HW+4] would contain it too.
  assert '4HW+4' in _board_line(board).split()


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


def test_a_boxed_lead_is_written_without_its_box() -> None:
  lead = Lead(
    raw='[KoH]',
    card=Card(rank=Rank.KING, suit=Suit.HEARTS),
    flagged_for_discussion=True,
  )
  board = _make_board(opening_lead=lead)

  assert 'lead=KoH' in _board_line(board)


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


# --- the result against the double dummy ---


def _comparison_line(
  *,
  we_declared: bool,
  tricks_taken: int,
  double_dummy_tricks: int,
  declarer: Direction = Direction.NORTH,
  strain: Strain = Strain.SPADES,
  deal: Deal | None = None,
  opening_lead: Lead | None = None,
) -> str:
  """The board line for one board, set against a stated double-dummy count.

  Only the board number and the level the contract was bid to are fixed, since
  no assertion here turns on either. The seat and strain carry defaults for the
  same reason, and are worth passing whenever a deal is passed too: a deal
  solves for a particular declarer in a particular strain, so those three go
  together.

  `deal` and `opening_lead` are what the solved `PLAY` column needs. Given no
  deal, only the published `DD` column can answer.
  """
  declaring_side = (
    Side.NORTH_SOUTH if declarer in Side.NORTH_SOUTH.seats else Side.EAST_WEST
  )
  defending_side = (
    Side.EAST_WEST if declaring_side is Side.NORTH_SOUTH else Side.NORTH_SOUTH
  )
  session = _make_session(
    _make_board(
      5,
      outcome=_make_outcome(
        level=4,
        strain=strain,
        declarer=declarer,
        tricks_taken=tricks_taken,
      ),
      opening_lead=opening_lead,
      our_side=declaring_side if we_declared else defending_side,
      deal=deal,
    )
  )
  traveller = _make_traveller(
    5, declarer=declarer, strain=strain, tricks=double_dummy_tricks
  )
  return _board_line_of(render_session(session, [traveller]))


def test_a_board_that_went_our_way_shows_a_positive_count() -> None:
  # We declared and took ten tricks where best play by both sides yields nine.
  line = _comparison_line(
    we_declared=True, tricks_taken=10, double_dummy_tricks=9
  )

  assert 'DD+1' in line


def test_a_board_that_went_against_us_shows_a_negative_count() -> None:
  line = _comparison_line(
    we_declared=True, tricks_taken=8, double_dummy_tricks=10
  )

  assert 'DD-2' in line


def test_a_board_we_defended_counts_the_shortfall_our_way() -> None:
  # The same board as above, defended rather than declared: the declarer fell
  # two short of the count, which is two tricks our way and so reads as a gain.
  line = _comparison_line(
    we_declared=False, tricks_taken=8, double_dummy_tricks=10
  )

  assert 'DD+2' in line


def test_a_result_matching_the_double_dummy_carries_a_signed_zero() -> None:
  line = _comparison_line(
    we_declared=True, tricks_taken=9, double_dummy_tricks=9
  )

  # A board that came out exactly even is a comparison, not an empty column, so
  # it is written with its sign like every other value.
  assert 'DD+0' in line


def test_a_board_the_traveller_does_not_record_is_not_compared() -> None:
  session = _make_session(
    _make_board(
      5,
      outcome=_make_outcome(
        level=4, strain=Strain.CLUBS, declarer=Direction.WEST, tricks_taken=10
      ),
      our_side=Side.EAST_WEST,
    )
  )
  # The sheet played board five; this traveller records board six and nothing
  # else, so it has nothing to say about the board in hand.
  traveller = _make_traveller(
    6, declarer=Direction.WEST, strain=Strain.CLUBS, tricks=9
  )

  assert 'DD' not in _board_line_of(render_session(session, [traveller]))


def test_the_play_column_is_solved_rather_than_read_from_the_table() -> None:
  # In `a_deal_the_lead_decides`, South is held to nine by a heart lead and
  # takes thirteen against anything else — so the table's nine and the thirteen
  # a spade leaves are both true of this one board, and neither is invented.
  line = _comparison_line(
    we_declared=True,
    declarer=Direction.SOUTH,
    strain=Strain.NOTRUMP,
    tricks_taken=11,
    double_dummy_tricks=9,
    deal=a_deal_the_lead_decides(),
    opening_lead=_make_lead(Rank.TWO, Suit.SPADES),
  )

  # Eleven tricks against the table's nine is two our way; against the thirteen
  # the spade lead left standing, two against us. One number cannot be both, so
  # a `PLAY` quietly reusing the table would fail here.
  assert 'DD+2' in line
  assert 'PLAY-2' in line


def test_the_play_column_stands_empty_without_a_deal_to_solve() -> None:
  line = _comparison_line(
    we_declared=True,
    declarer=Direction.SOUTH,
    strain=Strain.NOTRUMP,
    tricks_taken=11,
    double_dummy_tricks=9,
    opening_lead=_make_lead(Rank.TWO, Suit.SPADES),
  )

  # The table still answers, being read from the traveller; the solved count
  # cannot, since a board that reconciliation has not reached carries no deal.
  assert 'DD+2' in line
  assert 'PLAY' not in line


def test_a_session_no_traveller_has_reached_says_so() -> None:
  session = _make_session(
    _make_board(5, auction=[_make_bid(1, Strain.CLUBS)]), travellers=()
  )

  assert [
    line for line in render_session(session) if 'No traveller' in line
  ] == ['No traveller has reached this session; nothing to compare against.']


def test_a_session_a_traveller_has_reached_carries_no_caveat() -> None:
  session = _make_session(_make_board(5, auction=[_make_bid(1, Strain.CLUBS)]))

  assert not [
    line for line in render_session(session) if 'No traveller' in line
  ]


def test_a_session_that_recorded_nothing_carries_no_caveat() -> None:
  session = _make_session(Board(number=BoardNumber(raw='')), travellers=())

  # There was nothing to compare in the first place, so the absence of a
  # traveller is not something a reader of this session needs to be told.
  assert not [
    line for line in render_session(session) if 'No traveller' in line
  ]


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
      outcome=_make_outcome(
        level=4, strain=Strain.CLUBS, declarer=Direction.WEST, tricks_taken=10
      ),
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
