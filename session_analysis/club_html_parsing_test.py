# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for reading a Palo Alto club game's published HTML into a traveller.

Most tests write out the few elements they turn on, so what is being read sits
beside what is expected of it. Two tests parse whole captured files, one per
filename prefix the club's directors publish under; these carry the shape a real
BridgeComposer document arrives in, including the two ways the variants nest a
board. Both files describe the same game, so the par contract stands out as the
only thing they disagree about once parsed.

Names throughout are placeholders; the real captures hold club members' names
and live outside this repo (see travellers.md `#pii`).
"""

import datetime
import pathlib
from collections.abc import Mapping

from session_analysis.club_html_parsing import parse_club_html
from session_analysis.enums import (
  Direction,
  IssueSeverity,
  Penalty,
  Side,
  Strain,
  Suit,
)
from session_analysis.models import (
  CaptureReference,
  Passout,
  PlayedContract,
)
from session_analysis.travellers import (
  Par,
  Traveller,
  TravellerBoard,
  TravellerSource,
)

TESTDATA = pathlib.Path(__file__).parent / 'testdata/travellers'

# The parser records this on the traveller and no test here reads it back, so
# every call passes the same one rather than inventing a name apiece.
_REFERENCE = CaptureReference(path='capture.htm')

# The stem BridgeComposer builds each suit's glyph from: the CSS class
# `bcspades` and the entity `&spades;` both carry it. The parser reads the
# entity's character; the class is written here because the captures write it.
SUIT_GLYPHS: Mapping[Suit, str] = {
  Suit.SPADES: 'spades',
  Suit.HEARTS: 'hearts',
  Suit.DIAMONDS: 'diams',
  Suit.CLUBS: 'clubs',
}

# A whole deal for the diagrams that need one to be there but do not turn on
# which cards it holds. Board 1 of the fixtures.
DEAL: Mapping[Direction, Mapping[Suit, str]] = {
  Direction.NORTH: {
    Suit.SPADES: 'A K Q 8 3',
    Suit.HEARTS: 'A 5 4',
    Suit.DIAMONDS: 'K Q 2',
    Suit.CLUBS: '9 6',
  },
  Direction.WEST: {
    Suit.SPADES: '6 5',
    Suit.HEARTS: '9 8 2',
    Suit.DIAMONDS: 'J 8 7',
    Suit.CLUBS: 'Q J 10 7 3',
  },
  Direction.EAST: {
    Suit.SPADES: '10 9 4',
    Suit.HEARTS: 'Q J 10 3',
    Suit.DIAMONDS: '10 9 4',
    Suit.CLUBS: 'A K 5',
  },
  Direction.SOUTH: {
    Suit.SPADES: 'J 7 2',
    Suit.HEARTS: 'K 7 6',
    Suit.DIAMONDS: 'A 6 5 3',
    Suit.CLUBS: '8 4 2',
  },
}


def parse_markup(*elements: str) -> Traveller:
  """Parse a document written out here as the elements the test cares about."""
  return parse_club_html('\n'.join(elements), _REFERENCE)


def parse_fixture(name: str) -> Traveller:
  """Parse one of the two captured files by filename."""
  return parse_club_html((TESTDATA / name).read_text(), _REFERENCE)


def played(resolution: object) -> PlayedContract:
  """Narrow a resolution to the played contract the test expects it to be."""
  assert isinstance(resolution, PlayedContract)
  return resolution


def par(board: TravellerBoard) -> Par:
  """Narrow a board's par to the one the test expects it to have."""
  assert board.par is not None
  return board.par


def _make_hand(holdings: Mapping[Suit, str]) -> str:
  """One hand of a diagram: a row per suit, the glyph then the ranks held.

  A suit the player was dealt none of may be printed as an empty row or left out
  of the diagram altogether, so a caller states only the suits it wants rows
  for.
  """
  rows = ''.join(
    f'<tr class=bchand><td class=bcpip>'
    f'<span class=bc{SUIT_GLYPHS[suit]}>&{SUIT_GLYPHS[suit]};</span></td>'
    f'<td class=bchand>{ranks}</td></tr>'
    for suit, ranks in holdings.items()
  )
  return f'<table class=bchand>{rows}</table>'


def _make_diagram(
  hands: Mapping[Direction, Mapping[Suit, str]] | None = None,
  *,
  labels: str = '',
) -> str:
  """A board's hand diagram, laid out the way the club prints one.

  North sits on top, West and East in the middle row, South at the bottom —
  document order is all that assigns a hand to a seat. The dealer and
  vulnerability labels sit in the same table, which is how the parser reaches
  them from the top hand.
  """
  north, west, east, south = (
    _make_hand((hands or DEAL)[seat])
    for seat in (
      Direction.NORTH,
      Direction.WEST,
      Direction.EAST,
      Direction.SOUTH,
    )
  )
  return (
    '<table class=bchd>'
    f'<tr class=bchd1><td class=bchdlabels>{labels}</td>'
    f'<td class=bchd colspan=2>{north}</td></tr>'
    f'<tr class=bchd2><td class=bchd2a>{west}</td>'
    '<td class=bchd2b>N<br>W&nbsp;&nbsp;E<br>S</td>'
    f'<td class=bchd2c>{east}</td></tr>'
    f'<tr class=bchd3><td class=bchdhcp>&nbsp;</td>'
    f'<td class=bchd3b>{south}</td></tr>'
    '</table>'
  )


def _make_analysis(*lines: str) -> str:
  """The double-dummy paragraph, whose lines are `br` elements."""
  return f'<p class=bcdda>{"<br>".join(lines)}</p>'


def _make_score_row(
  *,
  contract: str = '',
  declarer: str = '',
  made: str = '',
  score_north_south: str = '',
  score_east_west: str = '',
  matchpoints_north_south: str = '',
  matchpoints_east_west: str = '',
  pair_north_south: str = '',
  pair_east_west: str = '',
) -> str:
  """One row of a score table, as the nine cells the club's table prints.

  Every column is written out, empty where the caller states nothing, because
  the table itself always prints all nine.
  """
  cells = (
    ('contract', contract),
    ('declarer', declarer),
    ('made', made),
    ('scorens', score_north_south),
    ('scoreew', score_east_west),
    ('mpns', matchpoints_north_south),
    ('mpew', matchpoints_east_west),
    ('pairns', pair_north_south),
    ('pairew', pair_east_west),
  )
  written = ''.join(
    f'<td class=bcst{column}>{value}</td>' for column, value in cells
  )
  return f'<tr class=bcst>{written}</tr>'


def _make_score_table(*rows: str) -> str:
  """A board's score table, holding the rows written out here."""
  return f'<table class=bcst>{"".join(rows)}</table>'


def _make_section_row(name: str) -> str:
  """The full-width row a multi-section table puts above a section's rows."""
  return f'<tr><td colspan=9>Section {name}</td></tr>'


def _make_recap(*lines: str) -> str:
  """The standings recap, whose columns are two or more spaces apart."""
  return '<pre id=bcrecap>\n' + '\n'.join(lines) + '\n</pre>'


# One ordinary row, for the boards that need a score table to be there but do
# not turn on what it holds. A board printing none reports a missing table, so
# every test that asserts on a board's issues has to print one.
SCORE_TABLE = _make_score_table(
  _make_score_row(
    contract='4S', declarer='N', made='4', score_north_south='420'
  )
)


# --- the captured files ---


def test_a_captured_file_parses_end_to_end() -> None:
  # The fixture is a real BridgeComposer document in miniature: a standings
  # recap, then two boards, each a container wrapping its diagram, its analysis
  # and its score table.
  traveller = parse_fixture('club_game_r.htm')

  assert traveller.source == TravellerSource.CLUB_HTML
  assert traveller.event == 'Placeholder Monday Pairs'
  # The date is printed in the standings recap, not in the title.
  assert traveller.date == datetime.date(2026, 3, 9)
  assert [board.number for board in traveller.boards] == [1, 2]
  assert [len(board.results) for board in traveller.boards] == [3, 3]
  assert traveller.boards[0].results[0].north_south.names == (
    'Ann Alfa',
    'Bob Bravo',
  )
  assert not traveller.issues


def test_the_two_variants_agree_on_everything_but_the_par_contract() -> None:
  # The same game published under both filename prefixes. `R` and `C` differ
  # only in presentation, so everything parsed out of them has to match.
  r_variant = parse_fixture('club_game_r.htm')
  c_variant = parse_fixture('club_game_c.htm')

  assert [board.results for board in r_variant.boards] == [
    board.results for board in c_variant.boards
  ]
  assert [board.deal for board in r_variant.boards] == [
    board.deal for board in c_variant.boards
  ]
  assert [board.double_dummy_tricks for board in r_variant.boards] == [
    board.double_dummy_tricks for board in c_variant.boards
  ]
  assert [par(board).score for board in r_variant.boards] == [
    par(board).score for board in c_variant.boards
  ]
  # The one difference: `R` prints the contract that achieves par, `C` the score
  # alone, and a score alone yields a par with no contracts rather than no par.
  assert [len(par(board).resolutions) for board in r_variant.boards] == [1, 1]
  assert [par(board).resolutions for board in c_variant.boards] == [(), ()]


# --- the session as a whole ---


def test_the_event_comes_from_the_document_title() -> None:
  traveller = parse_markup(
    '<title>Placeholder Tuesday Pairs</title>', '<div id=Board1></div>'
  )

  assert traveller.event == 'Placeholder Tuesday Pairs'


def test_the_date_comes_from_the_standings_recap() -> None:
  # The title names the event but never the day it was played; the recap's own
  # heading line is the only place the capture states a date.
  traveller = parse_markup(
    _make_recap('Placeholder Pairs Monday Aft Session May 12, 2026'),
    '<div id=Board1></div>',
  )

  assert traveller.date == datetime.date(2026, 5, 12)


def test_a_capture_with_no_recap_states_no_date() -> None:
  # The per-board rows stand on their own without the recap, so its absence
  # costs the date and the full names rather than the capture.
  traveller = parse_markup('<div id=Board1></div>')

  assert traveller.date is None
  assert not traveller.issues


# --- finding a board's markup ---


def test_a_board_container_with_no_class_is_still_a_board() -> None:
  # The `C` variant omits the container's class attribute, so a board is found
  # by the id that states its number.
  traveller = parse_markup('<div id=Board1></div>', '<div id=Board7></div>')

  assert [board.number for board in traveller.boards] == [1, 7]


def test_a_container_written_empty_still_owns_what_follows_it() -> None:
  # The `C` variant writes the board container as an empty element and lets the
  # board's parts follow it as siblings, so containment says nothing at all
  # about which board a score table belongs to.
  traveller = parse_markup(
    '<div id=Board1></div>',
    _make_score_table(
      _make_score_row(
        contract='4S', declarer='N', made='4', score_north_south='420'
      )
    ),
    '<div id=Board2></div>',
    _make_score_table(
      _make_score_row(
        contract='3NT', declarer='E', made='3', score_east_west='400'
      )
    ),
  )

  assert [board.number for board in traveller.boards] == [1, 2]
  assert [board.results[0].score for board in traveller.boards] == [420, -400]


def test_a_container_wrapping_its_parts_reads_the_same_way() -> None:
  # The `R` variant nests the same parts inside the container instead. Document
  # order is what the two variants agree on, so grouping by it reads both alike
  # — the assertions here are the ones above, on the other nesting.
  first_table = _make_score_table(
    _make_score_row(
      contract='4S', declarer='N', made='4', score_north_south='420'
    )
  )
  second_table = _make_score_table(
    _make_score_row(
      contract='3NT', declarer='E', made='3', score_east_west='400'
    )
  )
  traveller = parse_markup(
    f'<div id=Board1 class=bcbdid>{first_table}</div>',
    f'<div id=Board2 class=bcbdid>{second_table}</div>',
  )

  assert [board.number for board in traveller.boards] == [1, 2]
  assert [board.results[0].score for board in traveller.boards] == [420, -400]


def test_a_score_table_before_the_first_board_belongs_to_no_board() -> None:
  # Nothing states which board such a table would be for, so it is passed over
  # rather than attached to the board that opens after it.
  traveller = parse_markup(
    _make_score_table(
      _make_score_row(
        contract='4S', declarer='N', made='4', score_north_south='420'
      )
    ),
    '<div id=Board1></div>',
  )

  # And the board says so: it reports the score table it has none of, rather
  # than quietly adopting the one that came before it.
  assert traveller.boards[0].results == ()
  assert [issue.code for issue in traveller.boards[0].issues] == [
    'no_score_table'
  ]


# --- the deal ---


def test_every_seat_is_dealt_thirteen_cards() -> None:
  traveller = parse_markup('<div id=Board1></div>', _make_diagram(DEAL))

  deal = traveller.boards[0].deal
  assert deal is not None
  assert {
    seat: len(hand.cards) for seat, hand in deal.hands.items()
  } == dict.fromkeys(Direction, 13)


def test_the_diagram_is_read_as_it_is_laid_out() -> None:
  # North sits on top, West and East in the middle row, South at the bottom — an
  # order nothing in the markup states. Each seat here holds one whole suit, so
  # which seat got which hand is unambiguous; the three suits each hand names no
  # row for are voids.
  traveller = parse_markup(
    '<div id=Board1></div>',
    _make_diagram(
      {
        Direction.NORTH: {Suit.SPADES: 'A K Q J 10 9 8 7 6 5 4 3 2'},
        Direction.WEST: {Suit.HEARTS: 'A K Q J 10 9 8 7 6 5 4 3 2'},
        Direction.EAST: {Suit.DIAMONDS: 'A K Q J 10 9 8 7 6 5 4 3 2'},
        Direction.SOUTH: {Suit.CLUBS: 'A K Q J 10 9 8 7 6 5 4 3 2'},
      }
    ),
  )

  deal = traveller.boards[0].deal
  assert deal is not None
  assert {seat: hand.cards[0].suit for seat, hand in deal.hands.items()} == {
    Direction.NORTH: Suit.SPADES,
    Direction.WEST: Suit.HEARTS,
    Direction.EAST: Suit.DIAMONDS,
    Direction.SOUTH: Suit.CLUBS,
  }


def test_a_ten_printed_in_full() -> None:
  # The club prints a ten as `10` rather than as `T`, so `J 10 9 8` is four
  # cards and not five.
  traveller = parse_markup(
    '<div id=Board1></div>',
    _make_diagram(
      {
        Direction.NORTH: {Suit.SPADES: 'J 10 9 8'},
        Direction.WEST: {Suit.SPADES: 'A K Q'},
        Direction.EAST: {Suit.SPADES: '7 6 5'},
        Direction.SOUTH: {Suit.SPADES: '4 3 2'},
      }
    ),
  )

  deal = traveller.boards[0].deal
  assert deal is not None
  assert len(deal.hands[Direction.NORTH].cards) == 4


def test_a_suit_glyph_carrying_no_class_is_still_read() -> None:
  # A suit is identified by the character its entity decodes to, not by the
  # class beside it, so a glyph stripped of its class reads the same way.
  diagram = _make_diagram(DEAL).replace(' class=bcspades', '')
  traveller = parse_markup('<div id=Board1></div>', diagram)

  deal = traveller.boards[0].deal
  assert deal is not None
  assert {card.suit for card in deal.hands[Direction.NORTH].cards} == {
    Suit.SPADES,
    Suit.HEARTS,
    Suit.DIAMONDS,
    Suit.CLUBS,
  }


def test_a_suit_printed_as_an_empty_row_is_a_void() -> None:
  # The rows are read into suits by name, so a suit whose row holds no ranks
  # says the same thing as a suit with no row at all.
  traveller = parse_markup(
    '<div id=Board1></div>',
    _make_diagram(
      {
        Direction.NORTH: {Suit.SPADES: 'A K Q', Suit.HEARTS: ''},
        Direction.WEST: {Suit.SPADES: 'J 10 9'},
        Direction.EAST: {Suit.SPADES: '8 7 6'},
        Direction.SOUTH: {Suit.SPADES: '5 4 3'},
      }
    ),
  )

  deal = traveller.boards[0].deal
  assert deal is not None
  assert {card.suit for card in deal.hands[Direction.NORTH].cards} == {
    Suit.SPADES
  }


# --- the double-dummy list ---


def test_only_the_contracts_that_make_are_stated() -> None:
  # The club lists the contracts that make, so a seat and strain it leaves out
  # takes fewer than seven tricks without saying how many — `None` is the honest
  # value, not zero.
  traveller = parse_markup(
    '<div id=Board1></div>', _make_analysis('N 4S; N 2H;')
  )

  tricks = traveller.boards[0].double_dummy_tricks
  assert tricks is not None
  assert tricks[Direction.NORTH][Strain.SPADES] == 10
  assert tricks[Direction.NORTH][Strain.HEARTS] == 8
  assert tricks[Direction.NORTH][Strain.CLUBS] is None


def test_a_side_level_entry_covers_both_its_seats() -> None:
  # `NS` states one result for the side, which both its seats achieve.
  traveller = parse_markup('<div id=Board1></div>', _make_analysis('NS 3N;'))

  tricks = traveller.boards[0].double_dummy_tricks
  assert tricks is not None
  assert tricks[Direction.NORTH][Strain.NOTRUMP] == 9
  assert tricks[Direction.SOUTH][Strain.NOTRUMP] == 9


def test_a_makeable_list_that_wraps_onto_a_second_line() -> None:
  # BridgeComposer breaks a long list across `br` elements, so the list runs to
  # par wherever par falls rather than ending with the first line.
  traveller = parse_markup(
    '<div id=Board1></div>',
    _make_analysis('N 4S; NS 3N; ', 'S 2H; E 2D; ', 'Par +420: N 4S='),
  )

  tricks = traveller.boards[0].double_dummy_tricks
  assert tricks is not None
  # Both entries sit on the second line, past where the first line ended.
  assert tricks[Direction.SOUTH][Strain.HEARTS] == 8
  assert tricks[Direction.EAST][Strain.DIAMONDS] == 8


def test_the_opening_lead_notes_are_not_read_as_analysis() -> None:
  # A blank line ends the list and par; what follows is a note per opening lead,
  # which the traveller does not carry. `vs N 7H` would read as a makeable
  # contract if the notes were read on.
  traveller = parse_markup(
    '<div id=Board1></div>',
    _make_analysis('N 4S;', '', 'W vs N 7H: any card'),
  )

  tricks = traveller.boards[0].double_dummy_tricks
  assert tricks is not None
  assert tricks[Direction.NORTH][Strain.SPADES] == 10
  assert tricks[Direction.NORTH][Strain.HEARTS] is None


# --- par ---


def test_par_stated_with_the_contract_that_achieves_it() -> None:
  # The `R` variant's form: the score, then the contract reaching it.
  traveller = parse_markup(
    '<div id=Board1></div>', _make_analysis('Par +420: N 4S=')
  )

  achieved = par(traveller.boards[0])
  assert achieved.score == 420
  assert played(achieved.resolutions[0]).contract.declarer == Direction.NORTH
  # `4S=` is ten tricks: the ten the contract needed, with none to spare.
  assert played(achieved.resolutions[0]).result.tricks_taken == 10


def test_par_stated_as_a_score_alone() -> None:
  # The `C` variant's form. A par with no contracts, not an absent par: the
  # score is the part both variants state and the part reconciliation compares.
  traveller = parse_markup('<div id=Board1></div>', _make_analysis('Par +420'))

  achieved = par(traveller.boards[0])
  assert achieved.score == 420
  assert achieved.resolutions == ()


def test_a_par_score_written_with_a_unicode_minus() -> None:
  # The club writes a negative score with a Unicode minus sign, which does not
  # survive into the parsed value.
  traveller = parse_markup(
    '<div id=Board1></div>', _make_analysis('Par &minus;1430: E 6D=')
  )

  assert par(traveller.boards[0]).score == -1430


def test_par_stating_a_contract_for_each_seat() -> None:
  # Several contracts can reach the same score; the statements are separated by
  # semicolons and every one of them is kept.
  traveller = parse_markup(
    '<div id=Board1></div>', _make_analysis('Par +420: N 4S=; S 4S=')
  )

  achieved = par(traveller.boards[0])
  assert [played(each).contract.declarer for each in achieved.resolutions] == [
    Direction.NORTH,
    Direction.SOUTH,
  ]


# --- the traveller rows ---


def test_a_row_names_both_pairs_by_surname() -> None:
  traveller = parse_markup(
    '<div id=Board1></div>',
    _make_score_table(
      _make_score_row(
        contract='4S',
        declarer='N',
        made='4',
        pair_north_south='1-Alfa-Bravo',
        pair_east_west='2-Charlie-Delta',
      )
    ),
  )

  row = traveller.boards[0].results[0]
  assert row.north_south.number == '1'
  assert row.north_south.side == Side.NORTH_SOUTH
  assert row.north_south.names == ('Alfa', 'Bravo')
  assert row.east_west.number == '2'
  assert row.east_west.names == ('Charlie', 'Delta')


def test_full_names_come_from_the_standings_recap() -> None:
  # A row names a pair by surnames alone. The recap names the same pair in full,
  # keyed by its number and side, and is preferred wherever it has an entry.
  traveller = parse_markup(
    _make_recap(
      'Scores after  1 round   Average:    2.0      Section  A North-South',
      '  1   75.00    3.00  A   1     Ann Alfa - Bob Bravo',
    ),
    '<div id=Board1></div>',
    _make_score_table(
      _make_score_row(
        contract='4S', declarer='N', made='4', pair_north_south='1-Alfa-Bravo'
      )
    ),
  )

  assert traveller.boards[0].results[0].north_south.names == (
    'Ann Alfa',
    'Bob Bravo',
  )


def test_surnames_stand_in_where_the_recap_has_no_entry() -> None:
  # A pair that played but placed nowhere is absent from the recap, which costs
  # that pair its full names and nothing else.
  traveller = parse_markup(
    _make_recap(
      'Scores after  1 round   Average:    2.0      Section  A North-South',
      '  1   75.00    3.00  A   1     Ann Alfa - Bob Bravo',
    ),
    '<div id=Board1></div>',
    _make_score_table(
      _make_score_row(
        contract='4S',
        declarer='N',
        made='4',
        pair_north_south='9-Mike-November',
      )
    ),
  )

  assert traveller.boards[0].results[0].north_south.names == (
    'Mike',
    'November',
  )


def test_a_made_contract() -> None:
  traveller = parse_markup(
    '<div id=Board1></div>',
    _make_score_table(
      _make_score_row(
        contract='4S', declarer='N', made='4', score_north_south='420'
      )
    ),
  )

  row = traveller.boards[0].results[0]
  contract = played(row.resolution).contract
  assert (contract.level, contract.strain) == (4, Strain.SPADES)
  assert contract.declarer == Direction.NORTH
  # The `Made` column shows the level the contract made, so `4` is ten tricks.
  assert played(row.resolution).result.tricks_taken == 10
  assert row.score == 420


def test_a_contract_written_with_the_typographic_glyphs() -> None:
  # A doubling is a multiplication sign, a suit is a glyph carrying its class, a
  # thin space separates level from strain, and the `Made` column's minus is a
  # Unicode minus. None of the four survives into the parsed value.
  traveller = parse_markup(
    '<div id=Board1></div>',
    _make_score_table(
      _make_score_row(
        contract='6&thinsp;<span class=bcdiams>&diams;</span>&times;',
        declarer='W',
        made='&minus;5',
        score_north_south='1100',
      )
    ),
  )

  row = traveller.boards[0].results[0]
  contract = played(row.resolution).contract
  assert (contract.strain, contract.penalty) == (
    Strain.DIAMONDS,
    Penalty.DOUBLED,
  )
  # Down five from a six-level contract: twelve tricks needed, seven taken.
  assert played(row.resolution).result.tricks_taken == 7
  assert row.score == 1100


def test_a_score_in_the_east_west_column_is_negative() -> None:
  # The table prints a score in whichever side's column it is positive for and
  # leaves the other blank, so the two columns collapse to one signed number.
  traveller = parse_markup(
    '<div id=Board1></div>',
    _make_score_table(
      _make_score_row(
        contract='3NT', declarer='S', made='-1', score_east_west='100'
      )
    ),
  )

  assert traveller.boards[0].results[0].score == -100


def test_a_passed_out_board() -> None:
  # The table writes `Pass` in the score column rather than a zero; nobody
  # scored anything.
  traveller = parse_markup(
    '<div id=Board1></div>',
    _make_score_table(
      _make_score_row(contract='Pass', score_north_south='Pass')
    ),
  )

  row = traveller.boards[0].results[0]
  assert isinstance(row.resolution, Passout)
  assert row.score == 0


def test_matchpoints_are_kept_per_side() -> None:
  # Two numbers, not one signed number: what they sum to varies by source and by
  # how many tables played the board.
  traveller = parse_markup(
    '<div id=Board1></div>',
    _make_score_table(
      _make_score_row(
        contract='4S',
        declarer='N',
        made='4',
        matchpoints_north_south='2.00',
        matchpoints_east_west='0.00',
      )
    ),
  )

  row = traveller.boards[0].results[0]
  assert row.north_south_matchpoints == 2.0
  assert row.east_west_matchpoints == 0.0


# --- sections ---


def test_a_single_section_game_leaves_the_section_unnamed() -> None:
  # A game that ran one section prints no section letter anywhere in its table,
  # which is what the rows themselves say.
  traveller = parse_markup(
    '<div id=Board1></div>',
    _make_score_table(
      _make_score_row(
        contract='4S', declarer='N', made='4', pair_north_south='1-Alfa-Bravo'
      )
    ),
  )

  assert traveller.boards[0].results[0].north_south.section is None


def test_a_full_width_heading_assigns_the_rows_below_it() -> None:
  # A multi-section table introduces each section with a full-width row, and the
  # rows under it belong to that section until the next heading.
  traveller = parse_markup(
    '<div id=Board1></div>',
    _make_score_table(
      _make_section_row('A'),
      _make_score_row(
        contract='4S', declarer='N', made='4', pair_north_south='1-Alfa-Bravo'
      ),
      _make_section_row('B'),
      _make_score_row(
        contract='3NT',
        declarer='S',
        made='3',
        pair_north_south='1-Echo-Foxtrot',
      ),
    ),
  )

  rows = traveller.boards[0].results
  assert [row.north_south.section for row in rows] == ['A', 'B']
  # The section is what tells pair 1 in section A from pair 1 in section B.
  assert [row.north_south.number for row in rows] == ['1', '1']


def test_a_pair_cell_stating_its_own_section_is_taken_at_its_word() -> None:
  # The games with more than one section letter their pair cells, which says the
  # same thing as the heading above them and outranks it where they differ.
  traveller = parse_markup(
    '<div id=Board1></div>',
    _make_score_table(
      _make_section_row('A'),
      _make_score_row(
        contract='4S',
        declarer='N',
        made='4',
        pair_north_south='B9-Mike-November',
      ),
    ),
  )

  north_south = traveller.boards[0].results[0].north_south
  assert (north_south.section, north_south.number) == ('B', '9')


# --- what could not be read ---


def test_a_capture_holding_no_game_reports_an_issue() -> None:
  # A capture that yielded nothing is itself worth recording, so a page with no
  # boards comes back as an empty traveller rather than as a refusal.
  traveller = parse_markup('<html><body></body></html>')

  assert traveller.boards == ()
  assert [issue.code for issue in traveller.issues] == ['no_boards']


def test_a_board_printing_no_score_table_reports_it() -> None:
  # Every board of every capture prints one, so a board with none means the
  # markup has moved. A whole board's play would otherwise go missing without a
  # word, which is why this ranks alongside a capture holding no boards at all.
  traveller = parse_markup('<div id=Board1></div>', _make_diagram())

  board = traveller.boards[0]
  assert board.results == ()
  assert [issue.code for issue in board.issues] == ['no_score_table']
  assert board.issues[0].severity == IssueSeverity.HIGH


def test_a_board_printing_the_wrong_number_of_hands_loses_its_deal() -> None:
  # Every capture seen prints four diagrams, so a different count means the
  # markup has moved — reported rather than passed over, since the deal goes
  # missing either way.
  traveller = parse_markup(
    '<div id=Board1></div>',
    _make_hand({Suit.SPADES: 'A K Q'}),
    SCORE_TABLE,
  )

  board = traveller.boards[0]
  assert board.deal is None
  assert [issue.code for issue in board.issues] == ['unreadable_deal']
  assert '1 hand diagrams' in board.issues[0].message


def test_a_board_printing_no_hands_at_all_is_not_an_issue() -> None:
  # A capture with no hand records is ordinary, not damaged.
  traveller = parse_markup('<div id=Board1></div>', SCORE_TABLE)

  assert traveller.boards[0].deal is None
  assert not traveller.boards[0].issues


def test_a_dealer_contradicting_the_board_number_is_reported() -> None:
  # The dealer follows from the board number and is stored nowhere, so the
  # printed one is read only to be checked. Board 1 is North's deal, and a
  # contradiction suggests the number was read off the wrong part of the page.
  traveller = parse_markup(
    '<div id=Board1></div>',
    _make_diagram(labels='Board 1 East Deals None Vul'),
    SCORE_TABLE,
  )

  assert [issue.code for issue in traveller.boards[0].issues] == [
    'dealer_contradicts_board_number'
  ]


def test_an_unreadable_par_contract_keeps_the_par_score() -> None:
  # The score is the primary fact and the contracts are ways to reach it, so
  # losing a contract does not lose par. This one states no result and there is
  # no makeable-contract list to recover the result from.
  traveller = parse_markup(
    '<div id=Board1></div>', _make_analysis('Par +420: N 4S'), SCORE_TABLE
  )

  board = traveller.boards[0]
  assert par(board).score == 420
  assert par(board).resolutions == ()
  assert [issue.code for issue in board.issues] == ['unreadable_par_contract']


def test_a_row_whose_pair_cell_will_not_read_keeps_the_row() -> None:
  # The row's other side, its contract, and its score are all still good, so the
  # row stays and reports the one cell it lost.
  traveller = parse_markup(
    '<div id=Board1></div>',
    _make_score_table(
      _make_score_row(
        contract='4S',
        declarer='N',
        made='4',
        score_north_south='420',
        pair_north_south='rubbish',
        pair_east_west='2-Charlie-Delta',
      )
    ),
  )

  row = traveller.boards[0].results[0]
  assert row.north_south.number == ''
  assert row.east_west.number == '2'
  assert row.score == 420
  assert [issue.code for issue in row.issues] == ['unreadable_pair']
  assert row.issues[0].location == 'north_south'


def test_a_row_naming_no_pair_at_all_is_not_an_issue() -> None:
  # An empty cell is the capture stating no pair, which a row is entitled to do.
  traveller = parse_markup(
    '<div id=Board1></div>',
    _make_score_table(
      _make_score_row(
        contract='4S', declarer='N', made='4', score_north_south='420'
      )
    ),
  )

  row = traveller.boards[0].results[0]
  assert row.north_south.number == ''
  assert not row.issues


def test_a_row_whose_made_column_will_not_read_keeps_the_row() -> None:
  # The column holds neither the level made nor how far down the contract went,
  # so the contract cannot be resolved — but the pairs and the score are good.
  traveller = parse_markup(
    '<div id=Board1></div>',
    _make_score_table(
      _make_score_row(
        contract='4S',
        declarer='N',
        made='?',
        score_north_south='420',
        pair_north_south='1-Alfa-Bravo',
      )
    ),
  )

  row = traveller.boards[0].results[0]
  assert row.resolution is None
  assert row.north_south.number == '1'
  assert row.score == 420
  assert [issue.code for issue in row.issues] == ['unreadable_contract']


def test_a_row_naming_no_contract_at_all_is_not_an_issue() -> None:
  # A board never played, or one the director adjusted, names no contract — a
  # legitimate state, so only a row that named one and then could not be read is
  # worth reporting.
  traveller = parse_markup(
    '<div id=Board1></div>',
    _make_score_table(
      _make_score_row(
        pair_north_south='1-Alfa-Bravo', pair_east_west='2-Charlie-Delta'
      )
    ),
  )

  row = traveller.boards[0].results[0]
  assert row.resolution is None
  assert row.north_south.number == '1'
  assert not row.issues
