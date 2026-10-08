# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for reading a digitized session back as plain text.

Rendering is pure, so every test here builds its session in memory and asserts
on the lines that come out. Most assert on one board's line alone, which
`_board_line` picks out of a one-board transcript — the marks a call or a
contract cell carries are what those tests are about, not the summary or the
tables around them.

The command is the exception, and it reads real files under `tmp_path`: what it
is for is finding records on disk, so a stream would test something else.
"""

import datetime
import itertools
from collections.abc import Iterable, Sequence
from pathlib import Path

import pytest

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
  SolvedDoubleDummyTricks,
)
from session_analysis.testing import provenance
from session_analysis.testing.deals import a_deal_the_lead_decides
from session_analysis.travellers import (
  Traveller,
  TravellerBoard,
  TravellerResult,
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
  table: SolvedDoubleDummyTricks | None = None,
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
    solved_double_dummy_tricks=table,
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


def _make_table(
  *, declarer: Direction, strain: Strain, tricks: int
) -> SolvedDoubleDummyTricks:
  """A solved table whose one cell under test holds `tricks`.

  A solved table states all twenty cells, so the nineteen no test asserts on are
  filled with zero rather than left out.
  """
  table = {seat: dict.fromkeys(Strain, 0) for seat in Direction}
  table[declarer][strain] = tricks
  return table


def _board_line(board: Board) -> str:
  """The one board line a single-board session renders to."""
  return _board_line_of(render_session(_make_session(board)))


# The line separating the summary from the boards.
_RULE = '_____________'


def _board_line_of(lines: Iterable[str]) -> str:
  """The first board's line — the only one, in the sessions built here.

  Every test that reaches for this builds a single-board session, so the first
  board line is the only one.

  A transcript runs its header and summary, then a rule of underscores and a
  blank, then the boards. The line just past the rule's blank is therefore the
  first board. Neither end of the transcript would do, since the summary sits
  above the boards and the could-have table below them. Nor would matching the
  `#` a board line usually opens with — a board number that did not parse writes
  its transcription there instead.
  """
  from_rule = itertools.dropwhile(lambda line: line != _RULE, lines)
  next(from_rule)  # the rule itself
  next(from_rule)  # the blank line under it
  return next(from_rule)


def _lines_of(session: Session, travellers: Sequence[Traveller] = ()) -> str:
  """The whole transcript, as one string, for asserting on a run of lines."""
  return '\n'.join(render_session(session, travellers))


# --- the auction, in the sheet's own marks ---


def test_a_bid_is_written_as_its_level_and_strain() -> None:
  board = _make_board(auction=[_make_bid(2, Strain.HEARTS)])

  assert '2H' in _board_line(board)


def test_a_notrump_bid_writes_its_strain_as_one_letter() -> None:
  board = _make_board(auction=[_make_bid(1, Strain.NOTRUMP)])

  # The canonical strain is `NT`; the sheet writes the `N` alone.
  assert _board_line(board) == '#5\t1N'


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


def test_an_alerted_call_is_written_without_its_alert_mark() -> None:
  board = _make_board(
    auction=[
      _make_bid(1, Strain.CLUBS),
      _make_bid(2, Strain.HEARTS, alerted=True),
      _make_bid(3, Strain.CLUBS),
    ]
  )

  assert '1C 2H 3C' in _board_line(board)


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


# --- the auction running into the contract cell ---


def test_an_auction_ending_in_the_contract_runs_into_it() -> None:
  board = _make_board(
    auction=[_make_bid(1, Strain.NOTRUMP), _make_bid(3, Strain.NOTRUMP)],
    outcome=_make_outcome(
      level=3, strain=Strain.NOTRUMP, declarer=Direction.SOUTH, tricks_taken=9
    ),
  )

  # The final bid already says `3N`, so the cell adds only declarer and result.
  assert _board_line(board) == '#5\t1N 3NS+3'


def test_an_opponents_final_bid_keeps_its_parentheses() -> None:
  board = _make_board(
    auction=[
      _make_bid(4, Strain.SPADES),
      _make_bid(5, Strain.CLUBS, by_opponents=True),
    ],
    outcome=_make_outcome(
      level=5, strain=Strain.CLUBS, declarer=Direction.NORTH, tricks_taken=10
    ),
  )

  assert _board_line(board) == '#5\t4S (5C)N-1'


def test_a_final_double_is_carried_by_the_contract_s_mark() -> None:
  board = _make_board(
    auction=[
      _make_bid(4, Strain.CLUBS),
      _make_call(CallKind.DOUBLE, by_opponents=True),
    ],
    outcome=_make_outcome(
      level=4,
      strain=Strain.CLUBS,
      declarer=Direction.EAST,
      tricks_taken=6,
      penalty=Penalty.DOUBLED,
    ),
  )

  assert _board_line(board) == '#5\t4C*E-4'


def test_a_double_the_auction_left_unwritten_still_runs_in() -> None:
  board = _make_board(
    auction=[_make_bid(4, Strain.CLUBS)],
    outcome=_make_outcome(
      level=4,
      strain=Strain.CLUBS,
      declarer=Direction.EAST,
      tricks_taken=6,
      penalty=Penalty.DOUBLED,
    ),
  )

  assert _board_line(board) == '#5\t4C*E-4'


def test_a_double_contradicting_the_contract_cell_writes_both_out() -> None:
  board = _make_board(
    auction=[
      _make_bid(4, Strain.CLUBS),
      _make_call(CallKind.DOUBLE, by_opponents=True),
    ],
    outcome=_make_outcome(
      level=4, strain=Strain.CLUBS, declarer=Direction.EAST, tricks_taken=10
    ),
  )

  # The auction shows a double the contract cell does not, and folding the two
  # together would hide which of them is wrong.
  assert _board_line(board) == '#5\t4C (DBL) 4CE+4'


def test_an_auction_ending_short_of_the_contract_writes_both_out() -> None:
  board = _make_board(
    auction=[_make_bid(1, Strain.CLUBS)],
    outcome=_make_outcome(
      level=4, strain=Strain.CLUBS, declarer=Direction.WEST, tricks_taken=10
    ),
  )

  assert _board_line(board) == '#5\t1C 4CW+4'


def test_an_unread_final_call_writes_both_out() -> None:
  board = _make_board(
    auction=[_make_bid(4, Strain.CLUBS), _make_unread_call('x?')],
    outcome=_make_outcome(
      level=4, strain=Strain.CLUBS, declarer=Direction.WEST, tricks_taken=10
    ),
  )

  # The unread call could itself have been a higher bid.
  assert _board_line(board) == '#5\t4C ?x?? 4CW+4'


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
  board = _make_board(7, auction=[_make_bid(1, Strain.CLUBS)])

  assert _board_line(board).startswith('#7\t')


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
  board = _make_board(auction=[_make_bid(1, Strain.CLUBS)], matchpoints=None)

  assert 'MP=' not in _board_line(board)


# --- the session header ---


def test_the_header_names_the_session_and_its_date() -> None:
  session = _make_session(_make_board(auction=[_make_bid(1, Strain.CLUBS)]))

  assert next(iter(render_session(session))) == 'Monday Pairs — 2026-06-29'


def test_the_header_is_a_single_line() -> None:
  session = _make_session(
    _make_board(auction=[_make_bid(1, Strain.CLUBS)]),
    session_key='pabc-mon-2026-06-29',
  )

  # The stored key names the same session as the event and date, so it is left
  # out of a header kept to one line.
  assert list(render_session(session))[1] == ''


def test_a_date_the_footer_did_not_yield_says_so() -> None:
  session = _make_session(
    _make_board(auction=[_make_bid(1, Strain.CLUBS)]), date=None
  )

  assert next(iter(render_session(session))) == 'Monday Pairs — date not read'


# --- laying the boards out ---


def test_the_board_lines_run_with_nothing_between_them() -> None:
  session = _make_session(
    _make_board(5, auction=[_make_bid(1, Strain.CLUBS)]),
    _make_board(6, auction=[_make_bid(1, Strain.HEARTS)]),
  )

  # A solid block of rows is what pastes cleanly into a spreadsheet.
  assert '#5\t1C\n#6\t1H' in _lines_of(session)


def test_a_row_carrying_only_its_number_is_not_transcribed() -> None:
  # The last rows of a sheet are often numbered and never reached.
  played = _make_board(5, auction=[_make_bid(1, Strain.CLUBS)])
  unreached = _make_board(6)
  session = _make_session(played, unreached)

  assert '#6' not in _lines_of(session)


def test_a_board_scored_but_otherwise_unrecorded_is_transcribed() -> None:
  session = _make_session(_make_board(6, matchpoints=4.5))

  assert '#6\t\t\tMP=4.5' in _lines_of(session)


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

  `deal` and `opening_lead` are what the `PLAY` column needs. Given no deal,
  only the `DD` column, read from the board's table, can answer.
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
      table=_make_table(
        declarer=declarer, strain=strain, tricks=double_dummy_tricks
      ),
    )
  )
  return _board_line_of(render_session(session))


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


def test_a_board_carrying_no_table_is_not_compared() -> None:
  # No traveller reached the board, so reconciliation wrote no table onto it.
  session = _make_session(
    _make_board(
      5,
      outcome=_make_outcome(
        level=4, strain=Strain.CLUBS, declarer=Direction.WEST, tricks_taken=10
      ),
      our_side=Side.EAST_WEST,
    )
  )

  assert 'DD' not in _board_line_of(render_session(session))


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

  # The board's table still answers; the count after the lead cannot, with no
  # deal on the board to solve.
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


# --- the summary ---


def _make_scored_traveller(top: float, *board_numbers: int) -> Traveller:
  """A traveller scoring each board on `top`, from one row apiece.

  A row's two scores add up to the board's top, so one row is all a top needs.
  """
  row = TravellerResult(
    north_south=PairIdentity(number='1', side=Side.NORTH_SOUTH),
    east_west=PairIdentity(number='2', side=Side.EAST_WEST),
    north_south_matchpoints=top,
    east_west_matchpoints=0,
  )
  return Traveller(
    source=TravellerSource.CLUB_HTML,
    reference=CaptureReference(path='club/260629.html'),
    event='Monday Pairs',
    boards=tuple(
      TravellerBoard(number=number, results=(row,)) for number in board_numbers
    ),
  )


def _make_scored_board(
  number: int, *, declarer: Direction, matchpoints: float | None
) -> Board:
  """A board we sat East-West on, played in four spades by `declarer`."""
  return _make_board(
    number,
    outcome=_make_outcome(
      level=4, strain=Strain.SPADES, declarer=declarer, tricks_taken=10
    ),
    matchpoints=matchpoints,
    our_side=Side.EAST_WEST,
  )


def test_the_summary_totals_each_role_then_each_seat_within_it() -> None:
  session = _make_session(
    _make_scored_board(1, declarer=Direction.EAST, matchpoints=6),
    # North declaring puts East on lead.
    _make_scored_board(2, declarer=Direction.NORTH, matchpoints=2),
    _make_scored_board(3, declarer=Direction.WEST, matchpoints=4),
  )

  lines = _lines_of(session, [_make_scored_traveller(8, 1, 2, 3)])

  # Each board is scored out of eight: East declared six, led against two, and
  # West declared four.
  assert (
    '62.50%\tWe declared 2 hands\n'
    '  75.00%\t· E played 1\n'
    '  50.00%\t· W played 1\n'
    '\n'
    '25.00%\tWe defended 1 hand\n'
    '  25.00%\t· E on lead for 1\n'
    '\n'
    '50.00%\tNet, across 3 hands'
  ) in lines


def test_each_seat_of_ours_gets_a_line_for_its_errors() -> None:
  session = _make_session(
    _make_scored_board(1, declarer=Direction.EAST, matchpoints=6),
    _make_scored_board(2, declarer=Direction.WEST, matchpoints=2),
  )

  lines = _lines_of(session, [_make_scored_traveller(8, 1, 2)])

  assert 'E error =\nW error =' in lines


def test_the_summary_names_the_top() -> None:
  session = _make_session(
    _make_scored_board(1, declarer=Direction.EAST, matchpoints=6)
  )

  assert 'TOP=8' in _lines_of(session, [_make_scored_traveller(8, 1)])


def test_a_percentage_rounds_a_half_up() -> None:
  session = _make_session(
    _make_scored_board(1, declarer=Direction.EAST, matchpoints=17)
  )

  lines = _lines_of(session, [_make_scored_traveller(32, 1)])

  # 17 of 32 is exactly 53.125%, which a reader rounding by hand calls 53.13%.
  assert '53.13%\tNet, across 1 hand' in lines


def test_a_session_without_matchpoints_has_no_matchpoint_column() -> None:
  # The deal and its solved table give the board both double-dummy counts, as a
  # teams game's traveller does, and nothing scores it in matchpoints.
  session = _make_session(
    _make_board(
      5,
      outcome=_make_outcome(
        level=3,
        strain=Strain.NOTRUMP,
        declarer=Direction.SOUTH,
        tricks_taken=11,
      ),
      opening_lead=_make_lead(Rank.TWO, Suit.SPADES),
      our_side=Side.NORTH_SOUTH,
      deal=a_deal_the_lead_decides(),
      table=_make_table(
        declarer=Direction.SOUTH, strain=Strain.NOTRUMP, tricks=9
      ),
    )
  )

  lines = _lines_of(session)

  # Eleven tricks against the table's nine, and against the thirteen the spade
  # lead left standing.
  assert 'DD+2\tPLAY-2\tNet, across 1 hand' in lines
  assert '%' not in lines


def test_a_board_left_out_of_the_matchpoints_is_noted() -> None:
  session = _make_session(
    _make_scored_board(1, declarer=Direction.EAST, matchpoints=6),
    _make_scored_board(2, declarer=Direction.EAST, matchpoints=None),
  )

  lines = _lines_of(session, [_make_scored_traveller(8, 1, 2)])

  assert (
    '(1 hand had no matchpoints, or no top to score them against, and sat out '
    'of the percentages.)'
  ) in lines


# --- what the session could have scored ---


def test_the_could_have_table_starts_each_board_at_its_actual_score() -> None:
  session = _make_session(
    _make_scored_board(1, declarer=Direction.EAST, matchpoints=6)
  )

  lines = _lines_of(session, [_make_scored_traveller(8, 1)])

  assert 'Board\t\tActual\tCan Do\tAction\n1\t4♠E+4\t6.00\t6.00' in lines


def test_the_could_have_table_keeps_a_doubled_contract_s_mark() -> None:
  board = _make_board(
    1,
    outcome=_make_outcome(
      level=4,
      strain=Strain.CLUBS,
      declarer=Direction.EAST,
      tricks_taken=6,
      penalty=Penalty.DOUBLED,
    ),
    matchpoints=0,
    our_side=Side.EAST_WEST,
  )

  lines = _lines_of(_make_session(board), [_make_scored_traveller(8, 1)])

  assert '1\t4♣*E-4\t0.00\t0.00' in lines


def test_the_could_have_table_closes_on_the_session_average() -> None:
  session = _make_session(
    _make_scored_board(1, declarer=Direction.EAST, matchpoints=6),
    _make_scored_board(2, declarer=Direction.EAST, matchpoints=2),
  )

  lines = _lines_of(session, [_make_scored_traveller(8, 1, 2)])

  # Both columns start equal, so the two averages do too.
  assert lines.endswith('\tAVERAGE\t50.00%\t50.00%')


def test_the_could_have_table_leaves_its_standing_for_the_reader() -> None:
  session = _make_session(
    _make_scored_board(1, declarer=Direction.EAST, matchpoints=6)
  )

  lines = _lines_of(session, [_make_scored_traveller(8, 1)])

  assert (
    '[place overall] and [place in strat] earning [points] masterpoints'
  ) in lines


def test_a_session_without_matchpoints_has_no_could_have_table() -> None:
  session = _make_session(_make_board(5, auction=[_make_bid(1, Strain.CLUBS)]))

  assert 'Can Do' not in _lines_of(session)


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
      auction=[_make_bid(4, Strain.CLUBS)],
      outcome=_make_outcome(
        level=4, strain=Strain.CLUBS, declarer=Direction.WEST, tricks_taken=10
      ),
    )
  )
  record = _write_record(tmp_path, session)

  status = main([str(record)])

  assert status == 0
  assert '#5\t4CW+4' in capsys.readouterr().out


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
  readable = _write_record(
    tmp_path,
    _make_session(_make_board(5, auction=[_make_bid(1, Strain.CLUBS)])),
  )

  status = main([str(broken), str(readable)])

  captured = capsys.readouterr()
  # One unreadable record costs its own transcript, not the run's.
  assert status == 1
  assert '#5' in captured.out


def test_the_command_hands_over_a_page_rather_than_printing(
  tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
  record = _write_record(
    tmp_path,
    _make_session(_make_board(5, auction=[_make_bid(1, Strain.CLUBS)])),
  )
  pages: list[str] = []

  status = main([str(record), '--page'], show_page=pages.append)

  assert status == 0
  assert not capsys.readouterr().out
  # One page, titled for its one session, with the board in a table cell.
  [page] = pages
  assert '<title>Monday Pairs — 2026-06-29</title>' in page
  assert '>#5</td>' in page
