# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for reading an ACBL club-game page into a traveller.

Most tests write out the few blob fields they turn on, so what is being read
sits beside what is expected of it. Two tests parse a whole captured file, one
per movement, because the movement decides whether a pair number names one pair
or two: the one-winner capture also covers the shape a real page arrives in —
the event fields above the session and hand records listed out of board order —
while the two-winner capture covers a section numbering its pairs once per
direction.

Names throughout are placeholders; the real captures hold club members' names
and live outside this repo (see travellers.md `#pii`).
"""

import datetime
import json
import pathlib
from collections.abc import Mapping, Sequence

from session_analysis.acbl_club_parsing import parse_acbl_club_html
from session_analysis.enums import Direction, Penalty, Side, Strain, Suit
from session_analysis.models import Passout, PlayedContract
from session_analysis.travellers import Traveller, TravellerSource

TESTDATA = pathlib.Path(__file__).parent / 'testdata/travellers'

# The field name prefix and suffix the blob gives each holding: the seat, then
# the suit. Every seat is spelled out in full, unlike the compass letters the
# blob uses everywhere else.
SEAT_FIELDS: Mapping[Direction, str] = {
  Direction.NORTH: 'north',
  Direction.EAST: 'east',
  Direction.SOUTH: 'south',
  Direction.WEST: 'west',
}
SUIT_FIELDS: Mapping[Suit, str] = {
  Suit.SPADES: 'spades',
  Suit.HEARTS: 'hearts',
  Suit.DIAMONDS: 'diamonds',
  Suit.CLUBS: 'clubs',
}

# A whole deal, for the hand records that need one to be there but do not turn
# on which cards it holds. Board 1 of the fixture.
DEAL: Mapping[Direction, Mapping[Suit, str]] = {
  Direction.NORTH: {
    Suit.SPADES: '9 8 6 2',
    Suit.HEARTS: 'J 7 6 2',
    Suit.DIAMONDS: 'Q',
    Suit.CLUBS: 'A 10 7 6',
  },
  Direction.EAST: {
    Suit.SPADES: 'Q J',
    Suit.HEARTS: '10 8 3',
    Suit.DIAMONDS: '9 6 5 4 2',
    Suit.CLUBS: 'Q 5 2',
  },
  Direction.SOUTH: {
    Suit.SPADES: 'A K 10 7 5',
    Suit.HEARTS: 'K Q 5 4',
    Suit.DIAMONDS: 'K J 3',
    Suit.CLUBS: '4',
  },
  Direction.WEST: {
    Suit.SPADES: '4 3',
    Suit.HEARTS: 'A 9',
    Suit.DIAMONDS: 'A 10 8 7',
    Suit.CLUBS: 'K J 9 8 3',
  },
}


def parse_blob(data: object) -> Traveller:
  """Parse a page carrying this blob, whatever shape the blob is in."""
  return parse_acbl_club_html(
    f'<html><body></body><script>var data = {json.dumps(data)};</script></html>',
    reference='inline.html',
  )


def parse_page(
  *,
  sections: Sequence[Mapping[str, object]] = (),
  hand_records: Sequence[Mapping[str, object]] = (),
  **event: object,
) -> Traveller:
  """Parse a page whose blob describes one session of the pieces given here."""
  return parse_blob(
    {
      **event,
      'sessions': [
        {'sections': list(sections), 'hand_records': list(hand_records)}
      ],
    }
  )


def parse_rows(*rows: Mapping[str, object]) -> Traveller:
  """Parse a page whose one section played board 1 at the rows given here."""
  return parse_page(sections=[_make_section(boards={1: rows})])


def parse_fixture(name: str) -> Traveller:
  """Parse one of the two captured files by filename."""
  return parse_acbl_club_html((TESTDATA / name).read_text(), reference=name)


def played(resolution: object) -> PlayedContract:
  """Narrow a resolution to the played contract the test expects it to be."""
  assert isinstance(resolution, PlayedContract)
  return resolution


def _make_hand_record(
  board: int,
  *,
  hands: Mapping[Direction, Mapping[Suit, str]] | None = None,
  dealer: str = '',
  vulnerability: str = '',
  double_dummy_north_south: str = '',
  double_dummy_east_west: str = '',
  par: str = '',
) -> Mapping[str, object]:
  """One board's hand record: its deal, its analysis, and what par was.

  Only the holdings a caller states are written, since a seat the record says
  nothing about is exactly how a page with no hand record looks.
  """
  holdings = {
    f'{SEAT_FIELDS[seat]}_{SUIT_FIELDS[suit]}': cards
    for seat, by_suit in (hands or {}).items()
    for suit, cards in by_suit.items()
  }
  return {
    'board': board,
    'dealer': dealer,
    'vulnerability': vulnerability,
    'double_dummy_ns': double_dummy_north_south,
    'double_dummy_ew': double_dummy_east_west,
    'par': par,
    **holdings,
  }


def _make_pair_summary(
  number: str, *players: str, direction: str | None = None
) -> Mapping[str, object]:
  """One pair summary, naming its players the way ACBL files them."""
  return {
    'pair_number': number,
    'direction': direction,
    'players': [{'name': name} for name in players],
  }


def _make_row(
  *,
  north_south: str = '',
  east_west: str = '',
  contract: str = '',
  declarer: str = '',
  tricks_taken: str = '',
  north_south_score: str = '',
  east_west_score: str = '',
  north_south_matchpoints: str = '',
  east_west_matchpoints: str = '',
) -> Mapping[str, object]:
  """One board row of a section, under the blob's own field names."""
  return {
    'ns_pair': north_south,
    'ew_pair': east_west,
    'contract': contract,
    'declarer': declarer,
    'tricks_taken': tricks_taken,
    'ns_score': north_south_score,
    'ew_score': east_west_score,
    'ns_match_points': north_south_matchpoints,
    'ew_match_points': east_west_matchpoints,
    'opening_lead': '',
  }


def _make_section(
  *,
  name: str = 'A',
  pair_summaries: Sequence[Mapping[str, object]] = (),
  boards: Mapping[int, Sequence[Mapping[str, object]]] | None = None,
) -> Mapping[str, object]:
  """One section: who its pairs were, and the rows it played each board at."""
  return {
    'name': name,
    'pair_summaries': list(pair_summaries),
    'boards': [
      {'board_number': number, 'board_results': list(rows)}
      for number, rows in (boards or {}).items()
    ],
  }


# --- the captured files ---


def test_a_captured_file_parses_end_to_end() -> None:
  # The fixture is a real club page in miniature: the event fields above the
  # session, two hand records listed out of board order, and a one-winner
  # movement whose pair summaries name no direction.
  traveller = parse_fixture('acbl_club_game.html')

  assert traveller.source == TravellerSource.ACBL_CLUB
  assert traveller.event == 'Placeholder Monday Morning'
  assert traveller.date == datetime.date(2026, 3, 9)
  assert [board.number for board in traveller.boards] == [1, 2]
  assert [len(board.results) for board in traveller.boards] == [3, 3]
  assert traveller.boards[0].results[0].north_south.names == (
    'Ann Alfa',
    'Bob Bravo',
  )
  # ACBL has a column for the opening lead, but this club leaves it empty on
  # every row — so the opening lead stays sheet-only.
  assert all(
    row.opening_lead is None
    for board in traveller.boards
    for row in board.results
  )
  assert not traveller.issues
  assert not [issue for board in traveller.boards for issue in board.issues]


def test_a_captured_two_winner_movement_parses_end_to_end() -> None:
  # The second fixture numbers its pairs once per direction, so pair 1 is one
  # pair sitting North-South and a different pair sitting East-West; the
  # summaries' `direction` is what tells the two apart.
  traveller = parse_fixture('acbl_club_two_winner_movement.html')

  assert traveller.source == TravellerSource.ACBL_CLUB
  assert traveller.event == 'Placeholder Thursday Morning'
  assert traveller.date == datetime.date(2026, 5, 7)

  row = traveller.boards[0].results[0]
  assert row.north_south.number == '1'
  assert row.east_west.number == '1'
  assert row.north_south.names == ('Meg Mike', 'Ned November')
  assert row.east_west.names == ('Sam Sierra', 'Tom Tango')

  assert not traveller.issues
  assert not [issue for board in traveller.boards for issue in board.issues]


# --- the page ---


def test_the_blob_is_read_rather_than_the_rendered_markup() -> None:
  # The markup here says one thing and the blob another. Everything comes from
  # the blob, which is the whole point of reading it instead of the markup.
  traveller = parse_acbl_club_html(
    '<html><body><h1>Rendered Event</h1><table><tr><td>Board 99</td></tr>'
    '</table></body><script>var data = '
    '{"name": "Placeholder Pairs", "sessions": [{"sections": [{"boards": ['
    '{"board_number": 1, "board_results": []}]}]}]};</script></html>',
    reference='rendered.html',
  )

  assert traveller.event == 'Placeholder Pairs'
  assert [board.number for board in traveller.boards] == [1]


def test_an_assignment_written_without_spaces_is_still_found() -> None:
  # Every capture writes `var data = `, but the spacing around the assignment is
  # the page's own to choose and a browser reads either way — so resting a whole
  # capture on the spacing would be a needless place to break.
  traveller = parse_acbl_club_html(
    '<html><body></body><script>var data={"name": "Placeholder Pairs"};'
    '</script></html>',
    reference='compact.html',
  )

  assert traveller.event == 'Placeholder Pairs'


def test_the_event_and_date_come_from_the_blob() -> None:
  traveller = parse_page(
    name='Placeholder Tuesday Evening', start_date='05/12/2026'
  )

  assert traveller.event == 'Placeholder Tuesday Evening'
  assert traveller.date == datetime.date(2026, 5, 12)


def test_a_date_the_blob_states_unreadably_is_no_date() -> None:
  traveller = parse_page(name='Placeholder Pairs', start_date='sometime')

  assert traveller.date is None


# --- the deal ---


def test_every_seat_is_dealt_thirteen_cards() -> None:
  traveller = parse_page(hand_records=[_make_hand_record(1, hands=DEAL)])

  deal = traveller.boards[0].deal
  assert deal is not None
  assert {
    seat: len(hand.cards) for seat, hand in deal.hands.items()
  } == dict.fromkeys(Direction, 13)


def test_a_void_written_as_a_run_of_dashes() -> None:
  # ACBL's data writes an empty suit as several hyphens rather than one.
  traveller = parse_page(
    hand_records=[
      _make_hand_record(
        1,
        hands={
          Direction.NORTH: {
            Suit.SPADES: 'A K Q J 10 9 8 7 6 5 4 3 2',
            Suit.HEARTS: '-----',
            Suit.DIAMONDS: '-----',
            Suit.CLUBS: '-----',
          },
          Direction.EAST: {Suit.HEARTS: 'A K Q J 10 9 8 7 6 5 4 3 2'},
          Direction.SOUTH: {Suit.DIAMONDS: 'A K Q J 10 9 8 7 6 5 4 3 2'},
          Direction.WEST: {Suit.CLUBS: 'A K Q J 10 9 8 7 6 5 4 3 2'},
        },
      )
    ]
  )

  deal = traveller.boards[0].deal
  assert deal is not None
  north = deal.hands[Direction.NORTH]
  assert {card.suit for card in north.cards} == {Suit.SPADES}
  assert len(north.cards) == 13


def test_a_record_naming_no_seat_at_all_has_no_deal_and_no_issue() -> None:
  # A session whose hand records carry no cards is one whose deals were never
  # uploaded — ordinary, and the rows stand without them.
  traveller = parse_page(hand_records=[_make_hand_record(1)])

  assert traveller.boards[0].deal is None
  assert not traveller.boards[0].issues


def test_a_record_naming_some_seats_but_not_all_is_reported() -> None:
  # The deal is dropped either way; only the partial record means something went
  # wrong on the way in.
  traveller = parse_page(
    hand_records=[
      _make_hand_record(
        1,
        hands={
          Direction.NORTH: {Suit.SPADES: 'A K Q'},
          Direction.EAST: {Suit.SPADES: 'J 10 9'},
        },
      )
    ]
  )

  board = traveller.boards[0]
  assert board.deal is None
  assert [issue.code for issue in board.issues] == ['unreadable_deal']


def test_an_unreadable_rank_costs_the_whole_deal() -> None:
  # A partial deal would report cards nobody held, so anything unreadable within
  # one costs all four hands.
  traveller = parse_page(
    hand_records=[
      _make_hand_record(
        1,
        hands={
          Direction.NORTH: {Suit.SPADES: 'A K Z'},
          Direction.EAST: {Suit.SPADES: 'Q J'},
          Direction.SOUTH: {Suit.SPADES: '10 9'},
          Direction.WEST: {Suit.SPADES: '8 7'},
        },
      )
    ]
  )

  board = traveller.boards[0]
  assert board.deal is None
  assert [issue.code for issue in board.issues] == ['unreadable_deal']


# --- the double-dummy table ---


def test_every_cell_is_stated() -> None:
  # Unlike the club's own HTML, ACBL states the low cells too — as trick counts,
  # since there is no makeable contract to name below seven tricks.
  traveller = parse_page(
    hand_records=[
      _make_hand_record(
        1,
        double_dummy_north_south='NS: 4S 3NT C5 D1 H0',
        double_dummy_east_west='EW: 2C 5D 6H 1S 6NT',
      )
    ]
  )

  tricks = traveller.boards[0].double_dummy_tricks
  assert tricks is not None
  assert tricks[Direction.NORTH][Strain.SPADES] == 10
  assert tricks[Direction.NORTH][Strain.CLUBS] == 5
  assert tricks[Direction.NORTH][Strain.HEARTS] == 0


def test_seats_straddling_seven_tricks() -> None:
  # `1/-S` says the first seat makes a one-level spade contract and the second
  # makes none, which says only that it takes fewer than seven tricks.
  traveller = parse_page(
    hand_records=[_make_hand_record(1, double_dummy_east_west='EW: 1/-S')]
  )

  tricks = traveller.boards[0].double_dummy_tricks
  assert tricks is not None
  assert tricks[Direction.EAST][Strain.SPADES] == 7
  assert tricks[Direction.WEST][Strain.SPADES] is None


def test_a_slash_splits_the_two_seats() -> None:
  traveller = parse_page(
    hand_records=[_make_hand_record(1, double_dummy_east_west='EW: 5/6D')]
  )

  tricks = traveller.boards[0].double_dummy_tricks
  assert tricks is not None
  assert tricks[Direction.EAST][Strain.DIAMONDS] == 11
  assert tricks[Direction.WEST][Strain.DIAMONDS] == 12


def test_an_unreadable_double_dummy_line_costs_only_the_analysis() -> None:
  traveller = parse_page(
    hand_records=[
      _make_hand_record(1, hands=DEAL, double_dummy_north_south='NS: rubbish')
    ]
  )

  board = traveller.boards[0]
  assert board.double_dummy_tricks is None
  assert board.deal is not None
  assert [issue.code for issue in board.issues] == ['unreadable_double_dummy']


def test_a_par_result_that_cannot_be_recovered_costs_only_par() -> None:
  # ACBL omits the result whenever par makes exactly, leaving the double-dummy
  # table to supply it — so an unreadable table takes par down with it. That
  # costs par alone: the deal and the rows beside it are untouched, and nothing
  # is raised past the board.
  traveller = parse_page(
    sections=[_make_section(boards={1: [_make_row(north_south='1')]})],
    hand_records=[
      _make_hand_record(
        1,
        hands=DEAL,
        double_dummy_north_south='NS: rubbish',
        par='Par: 420 4S-N',
      )
    ],
  )

  board = traveller.boards[0]
  assert board.par is None
  assert board.deal is not None
  assert len(board.results) == 1
  assert [issue.code for issue in board.issues] == [
    'unreadable_double_dummy',
    'unreadable_par',
  ]


# --- par ---


def test_a_result_acbl_omits_is_recovered() -> None:
  # `Par: 420 4S-N` states no result, because par makes exactly — so the trick
  # count comes from the double-dummy table beside it.
  traveller = parse_page(
    hand_records=[
      _make_hand_record(
        1, double_dummy_north_south='NS: 4S', par='Par: 420 4S-N'
      )
    ]
  )

  par = traveller.boards[0].par
  assert par is not None
  assert par.score == 420
  assert played(par.resolutions[0]).result.tricks_taken == 10


def test_a_side_level_par_expands_to_both_seats() -> None:
  # Both seats of the side reach the same score, so the side expands rather than
  # leaving every later reader to handle a declarer that is not a seat.
  traveller = parse_page(
    hand_records=[
      _make_hand_record(
        1, double_dummy_east_west='EW: 7S', par='Par: -1510 7S-EW'
      )
    ]
  )

  par = traveller.boards[0].par
  assert par is not None
  assert par.score == -1510
  assert [
    played(resolution).contract.declarer for resolution in par.resolutions
  ] == [Direction.EAST, Direction.WEST]


def test_a_doubled_par_contract() -> None:
  # ACBL spells a doubling with an asterisk where every other source trails an
  # `X`.
  traveller = parse_page(
    hand_records=[_make_hand_record(1, par='Par: -800 7H*-NS-4')]
  )

  par = traveller.boards[0].par
  assert par is not None
  assert played(par.resolutions[0]).contract.penalty == Penalty.DOUBLED
  # `-4` is four short of the thirteen tricks a grand slam needs.
  assert played(par.resolutions[0]).result.tricks_taken == 9


# --- the traveller rows ---


def test_names_come_from_the_section_pair_summaries() -> None:
  # A board row names its pairs by number alone; the summaries name the players,
  # surname-first, which is turned around on the way in.
  traveller = parse_page(
    sections=[
      _make_section(
        name='A',
        pair_summaries=[_make_pair_summary('1', 'Alfa, Ann', 'Bravo, Bob')],
        boards={1: [_make_row(north_south='1', east_west='2')]},
      )
    ]
  )

  north_south = traveller.boards[0].results[0].north_south
  assert north_south.number == '1'
  assert north_south.side == Side.NORTH_SOUTH
  assert north_south.section == 'A'
  assert north_south.names == ('Ann Alfa', 'Bob Bravo')


def test_a_pair_no_summary_names_keeps_its_number() -> None:
  # The number is what joins a row to anything later, so a pair the summaries
  # skip still comes back — just unnamed.
  traveller = parse_rows(_make_row(north_south='9', east_west='2'))

  north_south = traveller.boards[0].results[0].north_south
  assert north_south.number == '9'
  assert north_south.names == ()


def test_a_movement_numbering_the_two_directions_separately() -> None:
  # Where a movement numbers North-South and East-West apart, pair 1 sitting
  # North-South is a different pair from pair 1 sitting East-West, and the
  # summaries say which is which.
  traveller = parse_page(
    sections=[
      _make_section(
        pair_summaries=[
          _make_pair_summary('1', 'Alfa, Ann', 'Bravo, Bob', direction='NS'),
          _make_pair_summary('1', 'Charlie, Gus', 'Delta, Hal', direction='EW'),
        ],
        boards={1: [_make_row(north_south='1', east_west='1')]},
      )
    ]
  )

  row = traveller.boards[0].results[0]
  assert row.north_south.names == ('Ann Alfa', 'Bob Bravo')
  assert row.east_west.names == ('Gus Charlie', 'Hal Delta')


def test_a_direction_spelled_with_a_hyphen() -> None:
  # The captures write `NS`, but the blob spells that same side `N-S` in its
  # vulnerability field, so the hyphenated spelling is read too.
  traveller = parse_page(
    sections=[
      _make_section(
        pair_summaries=[
          _make_pair_summary('1', 'Alfa, Ann', 'Bravo, Bob', direction='N-S')
        ],
        boards={1: [_make_row(north_south='1', east_west='2')]},
      )
    ]
  )

  assert traveller.boards[0].results[0].north_south.names == (
    'Ann Alfa',
    'Bob Bravo',
  )


def test_a_made_contract() -> None:
  traveller = parse_rows(
    _make_row(
      north_south='1',
      east_west='2',
      contract='4 S',
      declarer='N',
      tricks_taken='10',
      north_south_score='420',
    )
  )

  row = traveller.boards[0].results[0]
  contract = played(row.resolution).contract
  assert (contract.level, contract.strain) == (4, Strain.SPADES)
  assert contract.declarer == Direction.NORTH
  # The blob carries the trick count outright, so nothing is derived from the
  # result token beside it.
  assert played(row.resolution).result.tricks_taken == 10
  assert row.score == 420


def test_a_doubled_contract_going_down() -> None:
  traveller = parse_rows(
    _make_row(
      north_south='1',
      east_west='2',
      contract='3 NT x',
      declarer='S',
      tricks_taken='8',
      north_south_score='-100',
    )
  )

  row = traveller.boards[0].results[0]
  assert played(row.resolution).contract.penalty == Penalty.DOUBLED
  assert played(row.resolution).result.tricks_taken == 8
  assert row.score == -100


def test_a_contract_doubled_more_times_than_exist_is_no_contract() -> None:
  # Nothing is doubled three times, so the cell is nonsense — and nonsense in
  # one cell costs that cell rather than the capture around it.
  traveller = parse_rows(
    _make_row(
      north_south='1',
      east_west='2',
      contract='3 NT xxx',
      declarer='S',
      tricks_taken='8',
      north_south_score='-100',
    )
  )

  row = traveller.boards[0].results[0]
  assert row.resolution is None
  assert row.score == -100


def test_a_passed_out_board() -> None:
  # Nobody scored anything, which the blob writes as the contract `PASS`.
  traveller = parse_rows(
    _make_row(north_south='1', east_west='2', contract='PASS')
  )

  row = traveller.boards[0].results[0]
  assert isinstance(row.resolution, Passout)
  assert row.score == 0


def test_matchpoints_are_kept_per_side() -> None:
  # Two numbers, not one signed number: what they sum to varies by source and by
  # how many tables played the board.
  traveller = parse_rows(
    _make_row(
      north_south='1',
      east_west='2',
      north_south_matchpoints='2.50',
      east_west_matchpoints='1.50',
    )
  )

  row = traveller.boards[0].results[0]
  assert row.north_south_matchpoints == 2.5
  assert row.east_west_matchpoints == 1.5


def test_a_score_the_east_west_column_alone_states() -> None:
  # The blob writes the two sides' scores as the negation of each other, so
  # either column alone gives the signed number.
  traveller = parse_rows(
    _make_row(
      north_south='1',
      east_west='2',
      contract='4 S',
      declarer='E',
      tricks_taken='10',
      east_west_score='420',
    )
  )

  assert traveller.boards[0].results[0].score == -420


def test_a_row_recording_no_contract() -> None:
  # A board a pair never played, or one the director adjusted. The row is kept
  # because the pairs and the fact of the non-result are part of the record.
  traveller = parse_rows(
    _make_row(north_south='1', east_west='2', north_south_score='420')
  )

  row = traveller.boards[0].results[0]
  assert row.resolution is None
  assert row.north_south.number == '1'


# --- boards, sections, and hand records ---


def test_a_hand_record_is_placed_by_the_board_number_it_states() -> None:
  # The records arrive in no particular order, so a record is matched to its
  # board by the number it states rather than by where it sits in the list.
  traveller = parse_page(
    sections=[_make_section(boards={1: [], 2: []})],
    hand_records=[
      _make_hand_record(2, par='Par: 630 3NT-N+1'),
      _make_hand_record(1, par='Par: 450 4S-S+1'),
    ],
  )

  assert [board.number for board in traveller.boards] == [1, 2]
  assert [
    board.par.score if board.par else None for board in traveller.boards
  ] == [450, 630]


def test_a_board_the_hand_records_cover_but_nobody_played() -> None:
  # A board that was dealt and analyzed still belongs in the record, even with
  # no rows against it.
  traveller = parse_page(
    sections=[_make_section(boards={1: [_make_row(north_south='1')]})],
    hand_records=[_make_hand_record(5, hands=DEAL)],
  )

  assert [board.number for board in traveller.boards] == [1, 5]
  assert traveller.boards[1].results == ()
  assert traveller.boards[1].deal is not None


def test_a_board_played_but_absent_from_the_hand_records() -> None:
  traveller = parse_page(
    sections=[_make_section(boards={7: [_make_row(north_south='1')]})],
    hand_records=[_make_hand_record(1, hands=DEAL)],
  )

  played_board = traveller.boards[1]
  assert played_board.number == 7
  assert played_board.deal is None
  assert len(played_board.results) == 1


def test_two_sections_rows_gather_onto_one_board() -> None:
  # A board's deal and par are session-level and its rows are per section, so
  # the sections' rows land on one board apiece rather than one board each.
  traveller = parse_page(
    sections=[
      _make_section(
        name='A', boards={1: [_make_row(north_south='1', east_west='2')]}
      ),
      _make_section(
        name='B', boards={1: [_make_row(north_south='1', east_west='2')]}
      ),
    ]
  )

  assert [board.number for board in traveller.boards] == [1]
  assert [row.north_south.section for row in traveller.boards[0].results] == [
    'A',
    'B',
  ]


# --- what could not be read ---


def test_a_page_with_no_data_blob_reports_an_issue() -> None:
  # Everything this parser reads comes out of the blob, so a page without one
  # yields a traveller holding only the issue that says why.
  traveller = parse_acbl_club_html('<html></html>', reference='empty.html')

  assert traveller.boards == ()
  assert [issue.code for issue in traveller.issues] == ['no_page_data']
  assert 'var data' in traveller.issues[0].message


def test_a_page_whose_blob_is_not_readable_json_reports_an_issue() -> None:
  traveller = parse_acbl_club_html(
    '<html><script>var data = {oops;</script></html>', reference='bad.html'
  )

  assert [issue.code for issue in traveller.issues] == ['no_page_data']


def test_a_blob_that_is_not_an_object_reports_an_issue() -> None:
  traveller = parse_blob([1, 2, 3])

  assert [issue.code for issue in traveller.issues] == ['no_page_data']
  assert 'not an object' in traveller.issues[0].message


def test_a_page_describing_no_session_reports_an_issue() -> None:
  traveller = parse_blob({'name': 'Placeholder Pairs'})

  assert traveller.boards == ()
  assert [issue.code for issue in traveller.issues] == ['no_session']


def test_a_team_game_reports_that_it_carries_no_traveller() -> None:
  # A team game's page publishes match scores and no per-board rows, so there is
  # no traveller in it. Recording that beats handing back a silent empty one.
  traveller = parse_page(type='TEAMS')

  assert traveller.boards == ()
  assert [issue.code for issue in traveller.issues] == ['no_per_board_results']
  assert 'TEAMS' in traveller.issues[0].message


def test_a_page_describing_more_than_one_session_reports_the_extra() -> None:
  # A traveller covers one session and every club game seen publishes one, so a
  # second means the page is a shape this parser has not been shown.
  traveller = parse_blob(
    {
      'sessions': [
        {'sections': [_make_section(boards={1: [_make_row(north_south='1')]})]},
        {'sections': []},
      ]
    }
  )

  assert [issue.code for issue in traveller.issues] == ['extra_sessions']
  assert [board.number for board in traveller.boards] == [1]


def test_a_hand_record_with_no_board_number_is_dropped() -> None:
  # A record's board number is what places it against the rows, so a record
  # without one has nowhere to go.
  traveller = parse_page(
    sections=[_make_section(boards={1: [_make_row(north_south='1')]})],
    hand_records=[{'board': None}],
  )

  assert [board.number for board in traveller.boards] == [1]
  assert [issue.code for issue in traveller.issues] == [
    'unreadable_board_number'
  ]


def test_a_dealer_contradicting_the_board_number_is_reported() -> None:
  # The dealer follows from the board number and is stored nowhere, so the
  # stated one is read only to be checked. Board 1 is North's deal.
  traveller = parse_page(
    hand_records=[_make_hand_record(1, hands=DEAL, dealer='E')]
  )

  assert [issue.code for issue in traveller.boards[0].issues] == [
    'dealer_contradicts_board_number'
  ]
