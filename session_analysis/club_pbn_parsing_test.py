# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for reading a club game's PBN into a traveller.

Most tests write out the few PBN lines they turn on, so what is being read sits
beside what is expected of it. One test parses a whole captured file; this
covers the shape a real BridgeComposer document arrives in — a header comment
block, an opening game holding only the event tags, and columns padded to their
declared widths.

Names throughout are placeholders; the real captures hold club members' names
and live outside this repo (see travellers.md, Storage and PII).
"""

import datetime
import pathlib

from session_analysis.club_pbn_parsing import parse_club_pbn
from session_analysis.enums import Direction, Penalty, Side, Strain
from session_analysis.models import Passout, PlayedContract
from session_analysis.travellers import Traveller, TravellerSource

FIXTURE = pathlib.Path(__file__).parent / 'testdata/travellers/club_game.pbn'

# The score-table columns the row tests below write rows for. Spelled once
# because it is each test's rows, not this header, that the test is about; the
# tests that turn on a header's own shape spell out their own.
SCORE_TABLE = (
  '[ScoreTable "Section;PairId_NS;PairId_EW;Contract;Declarer;Result;'
  'Score_NS;Score_EW;MP_NS;MP_EW;Names_NS\\13;Names_EW"]'
)

# A whole deal, thirteen cards to a seat, for the tests that need one to be
# there but do not turn on which cards it holds.
DEAL = (
  '[Deal "N:AKQ2.AK3.AK4.AKQ JT98.QJT.QJT.JT9 '
  '765.9876.9876.87 43.542.532.65432"]'
)


def parse_lines(*lines: str) -> Traveller:
  """Parse a PBN written out here as the lines the test cares about."""
  return parse_club_pbn('\n'.join(lines) + '\n', reference='inline.pbn')


def played(resolution: object) -> PlayedContract:
  """Narrow a resolution to the played contract the test expects it to be."""
  assert isinstance(resolution, PlayedContract)
  return resolution


# --- a whole captured file ---


def test_a_captured_file_parses_end_to_end() -> None:
  # The fixture is a real BridgeComposer document in miniature: a header comment
  # block, an opening game carrying only the event tags, two boards, and one
  # score table whose name columns are padded to their declared width.
  traveller = parse_club_pbn(FIXTURE.read_text(), reference='club_game.pbn')

  assert traveller.source == TravellerSource.CLUB_PBN
  assert traveller.event == 'Placeholder Monday Pairs'
  assert traveller.date == datetime.date(2026, 3, 9)
  assert [board.number for board in traveller.boards] == [1, 2]
  assert [len(board.results) for board in traveller.boards] == [3, 0]
  assert traveller.boards[0].results[0].north_south.names == ('Alpha', 'Bravo')
  assert not traveller.issues


# --- the session as a whole ---


def test_the_event_and_date_come_from_the_title_comments() -> None:
  # BridgeComposer writes the title it prints above a hand record into comment
  # lines of its own, and most of the club's directors leave the standard tags
  # empty — so the comments are read ahead of the tags.
  traveller = parse_lines(
    '%HRTitleEvent "Placeholder Tuesday Pairs"',
    '%HRTitleDate 2026.05.12',
    '',
    '[Event ""]',
    '[Date ""]',
    '[Board "1"]',
  )

  assert traveller.event == 'Placeholder Tuesday Pairs'
  assert traveller.date == datetime.date(2026, 5, 12)


def test_a_tag_repeated_with_a_hash_takes_the_value_stated_earlier() -> None:
  # `#` means "the value from the nearest earlier game". The opening game here
  # says nothing at all, so neither the first game nor the `#` states the event.
  traveller = parse_lines(
    '[Event ""]',
    '',
    '[Event "Placeholder Pairs"]',
    '[Board "1"]',
    '',
    '[Event "#"]',
    '[Board "2"]',
  )

  assert traveller.event == 'Placeholder Pairs'


def test_a_game_carrying_no_board_is_not_a_board() -> None:
  # A file may open with a game holding only the shared event tags. It is not a
  # board, so only the games that name one come back.
  traveller = parse_lines(
    '[Event "Placeholder Pairs"]',
    '[Site "Placeholder Bridge Center"]',
    '',
    '[Board "7"]',
  )

  assert [board.number for board in traveller.boards] == [7]


def test_a_partly_unknown_date_is_no_date() -> None:
  # The date format is a fixed ten characters, so a file that knows only the
  # year still fills the month and day — with the `??` the standard reserves.
  traveller = parse_lines('[Date "2026.??.??"]', '[Board "1"]')

  assert traveller.date is None


# --- the deal ---


def test_a_deal_gives_each_seat_thirteen_cards() -> None:
  traveller = parse_lines('[Board "1"]', DEAL)

  deal = traveller.boards[0].deal
  assert deal is not None
  assert {
    seat: len(hand.cards) for seat, hand in deal.hands.items()
  } == dict.fromkeys(Direction, 13)


def test_the_hands_are_dealt_clockwise_from_the_seat_the_tag_names() -> None:
  # `E:` starts the list at East and runs clockwise — East, South, West, North —
  # so the four single-spade hands land in that order and nothing assumes the
  # list starts at North.
  traveller = parse_lines('[Board "1"]', '[Deal "E:A... K... Q... J..."]')

  deal = traveller.boards[0].deal
  assert deal is not None
  assert [
    deal.hands[seat].cards[0].rank.value
    for seat in (Direction.EAST, Direction.SOUTH, Direction.WEST)
  ] == ['A', 'K', 'Q']
  assert deal.hands[Direction.NORTH].cards[0].rank.value == 'J'


# --- the double-dummy table and par ---


def test_the_double_dummy_table_is_read_by_name_not_position() -> None:
  # Every row names its own declarer and denomination, so nothing rests on an
  # assumed ordering — here the rows are deliberately out of order.
  traveller = parse_lines(
    '[Board "1"]',
    '[OptimumResultTable "Declarer;Denomination;Result"]',
    'W C 7',
    'N H 11',
  )

  tricks = traveller.boards[0].double_dummy_tricks
  assert tricks is not None
  assert tricks[Direction.NORTH][Strain.HEARTS] == 11
  assert tricks[Direction.WEST][Strain.CLUBS] == 7


def test_par_stated_for_a_seat() -> None:
  traveller = parse_lines(
    '[Board "1"]', '[OptimumScore "NS 450"]', '[ParContract "N 4H+1"]'
  )

  par = traveller.boards[0].par
  assert par is not None
  assert par.score == 450
  assert played(par.resolutions[0]).contract.declarer == Direction.NORTH
  # `4H+1` is eleven tricks: the ten the contract needed, plus one.
  assert played(par.resolutions[0]).result.tricks_taken == 11


def test_an_east_west_par_score_is_turned_around() -> None:
  # The tag states the score from the named side's own perspective, so
  # `EW -1100` is North-South plus 1100 — the side every traveller score is
  # stated from.
  traveller = parse_lines(
    '[Board "1"]', '[OptimumScore "EW -1100"]', '[ParContract "EW 6DX-5"]'
  )

  par = traveller.boards[0].par
  assert par is not None
  assert par.score == 1100


def test_a_side_level_par_expands_to_both_seats() -> None:
  # Both seats of the side reach the same score, so the side expands rather than
  # leaving every later reader to handle a declarer that is not a seat.
  traveller = parse_lines(
    '[Board "1"]', '[OptimumScore "EW -1100"]', '[ParContract "EW 6DX-5"]'
  )

  par = traveller.boards[0].par
  assert par is not None
  assert [played(each).contract.declarer for each in par.resolutions] == [
    Direction.EAST,
    Direction.WEST,
  ]
  assert played(par.resolutions[0]).contract.penalty == Penalty.DOUBLED


# --- the traveller rows ---


def test_a_row_names_both_pairs() -> None:
  traveller = parse_lines(
    '[Board "1"]',
    SCORE_TABLE,
    'A 1 2 4S N 10 420 - 2.00 0.00 Alpha-Bravo   Charlie-Delta',
  )

  row = traveller.boards[0].results[0]
  assert row.north_south.number == '1'
  assert row.north_south.side == Side.NORTH_SOUTH
  assert row.east_west.number == '2'
  # A PBN names a pair by surnames alone; full names live only in the HTML.
  assert row.north_south.names == ('Alpha', 'Bravo')
  assert row.east_west.names == ('Charlie', 'Delta')


def test_a_row_carries_the_section_it_sat_in() -> None:
  # The section is what tells pair 1 in section A from pair 1 in section B, so
  # it is kept per row rather than once per capture.
  traveller = parse_lines(
    '[Board "1"]',
    SCORE_TABLE,
    'A 1 1 4S N 10 420 - 2.00 0.00 Alpha-Bravo   Charlie-Delta',
    'B 1 1 4S N 10 420 - 2.00 0.00 Echo-Foxtrot  Golf-Hotel',
  )

  sections = [row.north_south.section for row in traveller.boards[0].results]
  assert sections == ['A', 'B']


def test_a_made_contract() -> None:
  traveller = parse_lines(
    '[Board "1"]',
    SCORE_TABLE,
    'A 1 2 4S N 10 420 - 2.00 0.00 Alpha-Bravo   Charlie-Delta',
  )

  row = traveller.boards[0].results[0]
  contract = played(row.resolution).contract
  assert (contract.level, contract.strain) == (4, Strain.SPADES)
  assert contract.declarer == Direction.NORTH
  # The standard defines the `Result` column as the tricks declarer won, so ten
  # is the canonical count and not a result relative to the contract.
  assert played(row.resolution).result.tricks_taken == 10
  assert row.score == 420


def test_a_doubled_contract_going_down() -> None:
  # The score sits in the East-West column, so it is negative for North-South.
  traveller = parse_lines(
    '[Board "1"]',
    SCORE_TABLE,
    'A 2 3 3NTX S 8 - 100 0.00 2.00 Echo-Foxtrot  Golf-Hotel',
  )

  row = traveller.boards[0].results[0]
  assert played(row.resolution).contract.penalty == Penalty.DOUBLED
  assert row.score == -100


def test_a_passed_out_board() -> None:
  # The table writes `PASS` where the score would go; nobody scored anything.
  traveller = parse_lines(
    '[Board "1"]',
    SCORE_TABLE,
    'B 3 3 PASS - - PASS - 1.00 1.00 India-Juliet  Kilo-Lima',
  )

  row = traveller.boards[0].results[0]
  assert isinstance(row.resolution, Passout)
  assert row.score == 0


def test_matchpoints_are_kept_per_side() -> None:
  # Two numbers, not one signed number: what they sum to varies by source and by
  # how many tables played the board.
  traveller = parse_lines(
    '[Board "1"]',
    SCORE_TABLE,
    'A 1 2 4S N 10 420 - 2.00 0.00 Alpha-Bravo   Charlie-Delta',
  )

  row = traveller.boards[0].results[0]
  assert row.north_south_matchpoints == 2.0
  assert row.east_west_matchpoints == 0.0


def test_a_file_with_no_score_table_has_no_rows() -> None:
  # Several of the club's directors upload a hand record with no score table at
  # all. That is a complete parse of what the file says, not a failure.
  traveller = parse_lines('[Board "1"]', DEAL)

  assert traveller.boards[0].results == ()
  assert not traveller.boards[0].issues


def test_a_name_longer_than_its_declared_width_stays_whole() -> None:
  # A column's declared width is a minimum, not the width it was printed at, so
  # a long pair of surnames runs past it and pushes the column beside it along
  # rather than being cut off at it. `Whiskey-Yankee` is fourteen characters in
  # a column declared as thirteen.
  traveller = parse_lines(
    '[Board "1"]',
    '[ScoreTable "PairId_NS\\2R;PairId_EW\\2R;Contract\\4L;Declarer;'
    'Result\\2R;Score_NS\\3R;Score_EW\\3R;Names_NS\\13;Names_EW"]',
    ' 1  1 4S   N 10 420   - Whiskey-Yankee Charlie-Delta',
  )

  row = traveller.boards[0].results[0]
  assert row.north_south.names == ('Whiskey', 'Yankee')
  assert row.east_west.names == ('Charlie', 'Delta')


# --- what could not be read ---


def test_a_file_holding_no_game_reports_an_issue() -> None:
  # A capture that yielded nothing is itself worth recording, so a file with no
  # boards comes back as an empty traveller rather than as a refusal.
  traveller = parse_lines('% PBN 2.1')

  assert traveller.boards == ()
  assert [issue.code for issue in traveller.issues] == ['no_board_records']


def test_a_board_with_an_unreadable_number_is_dropped() -> None:
  # Everything about a board hangs off its number, so a record without one has
  # nowhere to go — recording the number as written is what keeps the record.
  traveller = parse_lines('[Board "1"]', '', '[Board "second"]')

  assert [board.number for board in traveller.boards] == [1]
  assert [issue.code for issue in traveller.issues] == [
    'unreadable_board_number'
  ]
  assert 'second' in traveller.issues[0].message


def test_an_unreadable_deal_costs_the_deal_and_nothing_else() -> None:
  # A partial deal would report cards nobody held, so anything unreadable within
  # one costs the whole deal — but not the rows it was played at.
  traveller = parse_lines(
    '[Board "1"]',
    '[Deal "N:AKQ2.AK3.AK4.AKQ JT98.QJT.QJT.JT9"]',
    SCORE_TABLE,
    'A 1 2 4S N 10 420 - 2.00 0.00 Alpha-Bravo   Charlie-Delta',
  )

  board = traveller.boards[0]
  assert board.deal is None
  assert [issue.code for issue in board.issues] == ['unreadable_deal']
  assert len(board.results) == 1


def test_an_unreadable_dealer_is_reported() -> None:
  # The dealer follows from the board number and is stored nowhere, so an
  # unreadable one costs only the cross-check — but a tag gone strange is worth
  # saying out loud rather than passing over.
  traveller = parse_lines('[Board "1"]', '[Dealer "x"]')

  assert [issue.code for issue in traveller.boards[0].issues] == [
    'unreadable_dealer'
  ]


def test_a_dealer_the_file_omits_is_not_an_issue() -> None:
  # A tag that says nothing is not a tag that says something unreadable.
  traveller = parse_lines('[Board "1"]', '[Dealer ""]')

  assert not traveller.boards[0].issues


def test_a_row_that_does_not_fit_its_header_is_dropped() -> None:
  # Once a row cannot be split it names no pair, so nothing downstream could
  # join it to anything; the issue carries the row's text instead.
  traveller = parse_lines(
    '[Board "1"]',
    SCORE_TABLE,
    'A 1 2 4S N 10 420 - 2.00 0.00 Alpha-Bravo   Charlie-Delta',
    'B 3 4',
  )

  board = traveller.boards[0]
  assert [row.north_south.number for row in board.results] == ['1']
  assert [issue.code for issue in board.issues] == ['unreadable_row']
  assert 'B 3 4' in board.issues[0].message


def test_a_row_with_an_unreadable_contract_is_kept() -> None:
  # `9S` is no contract — there is no ninth level — but the pairs and the score
  # on the row are still good, so the row stays and reports the field it lost.
  traveller = parse_lines(
    '[Board "1"]',
    SCORE_TABLE,
    'A 1 2 9S N 10 420 - 2.00 0.00 Alpha-Bravo   Charlie-Delta',
  )

  row = traveller.boards[0].results[0]
  assert row.resolution is None
  assert row.north_south.number == '1'
  assert row.score == 420
  assert [issue.code for issue in row.issues] == ['unreadable_contract']


def test_an_unreadable_double_dummy_row_leaves_the_others_standing() -> None:
  # Every row names its own declarer and denomination, so the cells around an
  # unreadable one keep their meaning.
  traveller = parse_lines(
    '[Board "1"]',
    '[OptimumResultTable "Declarer;Denomination;Result"]',
    'N NT 9',
    'N S ??',
  )

  board = traveller.boards[0]
  assert board.double_dummy_tricks == {Direction.NORTH: {Strain.NOTRUMP: 9}}
  assert [issue.code for issue in board.issues] == [
    'unreadable_double_dummy_row'
  ]


def test_a_double_dummy_table_with_no_readable_rows_is_no_table() -> None:
  # An empty mapping would claim an analysis that declined to say anything about
  # any seat; None is what stands for no analysis at all.
  traveller = parse_lines(
    '[Board "1"]',
    '[OptimumResultTable "Declarer;Denomination;Result"]',
    'N NT ??',
  )

  assert traveller.boards[0].double_dummy_tricks is None


def test_an_unreadable_par_contract_keeps_the_par_score() -> None:
  # The score is the primary fact and the contracts are ways to reach it, so
  # losing one contract does not lose par.
  traveller = parse_lines(
    '[Board "1"]', '[OptimumScore "NS 450"]', '[ParContract "N 4H+1;nonsense"]'
  )

  par = traveller.boards[0].par
  assert par is not None
  assert par.score == 450
  assert len(par.resolutions) == 1
  assert [issue.code for issue in traveller.boards[0].issues] == [
    'unreadable_par_contract'
  ]


def test_an_unreadable_par_score_costs_the_whole_par() -> None:
  # Nothing holds the contracts without the score they achieve.
  traveller = parse_lines(
    '[Board "1"]', '[OptimumScore "nonsense"]', '[ParContract "N 4H+1"]'
  )

  board = traveller.boards[0]
  assert board.par is None
  assert [issue.code for issue in board.issues] == ['unreadable_par_score']
