# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for reading an ACBL tournament session summary into a traveller.

Most tests write out the few elements they turn on, so what is being read sits
beside what is expected of it. One test parses a whole captured file; that
covers the shape a real summary arrives in — a section heading above the board
panels, and each panel sharing a row with the two results tables that state its
rows from either side.

Names throughout are placeholders; the real captures hold players' names and
live outside this repo (see travellers.md `#pii`).
"""

import datetime
import pathlib
from collections.abc import Mapping, Sequence

from session_analysis.acbl_tournament_parsing import (
  parse_acbl_tournament_html,
)
from session_analysis.enums import Direction, Penalty, Side, Strain, Suit
from session_analysis.models import (
  CaptureReference,
  Passout,
  PlayedContract,
)
from session_analysis.travellers import Traveller, TravellerSource

FIXTURE = (
  pathlib.Path(__file__).parent
  / 'testdata/travellers/acbl_tournament_session.html'
)

# The parser records this on the traveller and no test here reads it back, so
# every call passes the same one rather than inventing a name apiece.
_REFERENCE = CaptureReference(path='capture.html')

# The class the page gives each suit's span. The span is empty — the stylesheet
# draws the glyph from the class — so the class is the only place a suit is
# written down.
SUIT_CLASSES: Mapping[Suit, str] = {
  Suit.SPADES: 'spades',
  Suit.HEARTS: 'hearts',
  Suit.DIAMONDS: 'diams',
  Suit.CLUBS: 'clubs',
}

# How the page writes a suit a player holds none of.
VOID = '—'

# A whole deal, for the diagrams that need one to be there but do not turn on
# which cards it holds. Board 1 of the fixture.
DEAL: Mapping[Direction, Mapping[Suit, str]] = {
  Direction.NORTH: {
    Suit.SPADES: 'J 10 6 4',
    Suit.HEARTS: 'A Q 10 9 3',
    Suit.DIAMONDS: '9 6 2',
    Suit.CLUBS: '5',
  },
  Direction.WEST: {
    Suit.SPADES: '3 2',
    Suit.HEARTS: VOID,
    Suit.DIAMONDS: 'Q J 10 8 5 3',
    Suit.CLUBS: 'A K 7 4 2',
  },
  Direction.EAST: {
    Suit.SPADES: 'A K 7',
    Suit.HEARTS: 'J 6 5',
    Suit.DIAMONDS: 'A K 7 4',
    Suit.CLUBS: 'J 9 8',
  },
  Direction.SOUTH: {
    Suit.SPADES: 'Q 9 8 5',
    Suit.HEARTS: 'K 8 7 4 2',
    Suit.DIAMONDS: VOID,
    Suit.CLUBS: 'Q 10 6 3',
  },
}


def parse_markup(*elements: str) -> Traveller:
  """Parse a page written out here as the elements the test cares about."""
  return parse_acbl_tournament_html('\n'.join(elements), _REFERENCE)


def parse_fixture() -> Traveller:
  """Parse the captured session summary."""
  return parse_acbl_tournament_html(
    FIXTURE.read_text(),
    _REFERENCE,
  )


def played(resolution: object) -> PlayedContract:
  """Narrow a resolution to the played contract the test expects it to be."""
  assert isinstance(resolution, PlayedContract)
  return resolution


def _make_glyph(suit: Suit) -> str:
  """A suit as the page writes it: an empty span the stylesheet draws."""
  return f'<span class="{SUIT_CLASSES[suit]} symbol"></span>'


def _make_hand(holdings: Mapping[Suit, str]) -> str:
  """One hand's holdings: a span per suit, opening with the suit's own span."""
  return ''.join(
    f'<span class="">{_make_glyph(suit)} {ranks}</span>'
    for suit, ranks in holdings.items()
  )


def _make_diagram(
  hands: Mapping[Direction, Mapping[Suit, str]] | None = None,
) -> str:
  """A board's diagram, laid out the way the page renders one.

  North on top and South at the bottom, with the middle block holding West on
  its left and East on its right.
  """
  dealt = hands or DEAL
  return (
    f'<div class="hand">{_make_hand(dealt[Direction.NORTH])}</div>'
    '<div class="hand middle">'
    f'<div class="inner-slice left">{_make_hand(dealt[Direction.WEST])}</div>'
    f'<div class="inner-slice right">{_make_hand(dealt[Direction.EAST])}</div>'
    '</div>'
    f'<div class="hand">{_make_hand(dealt[Direction.SOUTH])}</div>'
  )


def _make_panel(
  number: int,
  *,
  labels: str = '',
  diagram: str = '',
  double_dummy: tuple[str, str] | None = None,
  par: str = '',
) -> str:
  """One board's panel: what it was dealt, and what analysis says about it.

  Each block opens with a link explaining itself, as the page's do, so nothing
  here rests on the value being the block's only child.
  """
  blocks = [f'<div class="board-data">{labels}</div>' if labels else '']
  blocks.append(diagram)
  if double_dummy:
    blocks.append(
      '<div class="double-dummy"><a href="#ddmakes">Double Dummy Makes</a>'
      f'<span>{double_dummy[0]}</span><span>{double_dummy[1]}</span></div>'
    )
  if par:
    blocks.append(
      f'<div class="par-score"><a href="#par">Par Score</a>'
      f'<span>{par}</span></div>'
    )
  return f'<div class="board" id="board-{number}">{"".join(blocks)}</div>'


def _make_pairs(
  first: tuple[str, Sequence[str]], second: tuple[str, Sequence[str]]
) -> str:
  """A results row's pairs cell: one pair, then `vs.`, then the other.

  A pair's number is loose text and each of its players sits in a span, which is
  what keeps a hyphenated name from splitting where the players separate.
  """

  def named(number: str, players: Sequence[str]) -> str:
    spans = '-'.join(f'<span class="name">{name}</span>' for name in players)
    return f'{number}-{spans}'

  return f' {named(*first)} vs. {named(*second)}'


def _make_results_row(
  *,
  contract: str = '',
  declarer: str = '',
  score: str = '',
  matchpoints: str = '',
  pairs: str = '',
) -> str:
  """One results row, with the menu cell and commented-out results column the
  page renders around its values.
  """
  return (
    '<tr><td><div class="btn-group"></div></td>'
    f'<td>{contract}</td><td>{declarer}</td>'
    '<!-- <td></td> -->'
    f'<td>{score}</td><td>{matchpoints}</td><td></td>'
    f'<td>{pairs}</td></tr>'
  )


def _make_results_table(side: str, rows: Sequence[str]) -> str:
  """A board's results table for one side, under the heading naming it."""
  return (
    f'<div class="scores"><h4>{side}</h4><div class="table-responsive">'
    '<table class="tablesorter table board-results-table"><tbody>'
    f'{"".join(rows)}</tbody></table></div></div>'
  )


def _make_board(
  panel: str,
  *,
  north_south_rows: Sequence[str] = (),
  east_west_rows: Sequence[str] = (),
) -> str:
  """A board's row: the panel on one side, its two results tables on the other.

  The tables sit beside the panel rather than inside it, which is why `_tables`
  reaches them through the row the two share.
  """
  return (
    '<div class="row">'
    f'<div class="col-sm-4">{panel}</div>'
    '<div class="col-sm-8">'
    f'{_make_results_table("N-S", north_south_rows)}'
    f'{_make_results_table("E-W", east_west_rows)}'
    '</div></div>'
  )


# --- the captured file ---


def test_a_captured_file_parses_end_to_end() -> None:
  # The fixture is a real summary in miniature: a section heading above the
  # panels, and each panel sharing a row with the two tables stating its rows
  # from either side.
  traveller = parse_fixture()

  assert traveller.source == TravellerSource.ACBL_TOURNAMENT
  assert traveller.event == 'Placeholder Open Pairs'
  assert traveller.date == datetime.date(2026, 3, 9)
  assert [board.number for board in traveller.boards] == [1, 2]
  assert [len(board.results) for board in traveller.boards] == [3, 3]
  assert traveller.boards[0].results[0].north_south.names == (
    'Ann-Marie Alfa',
    'Bob Bravo',
  )
  assert not traveller.issues
  assert not [issue for board in traveller.boards for issue in board.issues]


# --- the session as a whole ---


def test_the_event_comes_from_the_summary_heading() -> None:
  # The page names the event in the heading that announces the summary, with the
  # words `Event Summary` trailing it.
  traveller = parse_markup(
    '<h2>Placeholder Open Pairs Event Summary</h2>',
    _make_board(_make_panel(1)),
  )

  assert traveller.event == 'Placeholder Open Pairs'


def test_the_date_comes_from_the_opening_heading() -> None:
  traveller = parse_markup(
    '<h1>May 12, 2026 - Tuesday 1:00 pm</h1>', _make_board(_make_panel(1))
  )

  assert traveller.date == datetime.date(2026, 5, 12)


def test_boards_take_the_section_heading_above_them() -> None:
  # Sections are headings rather than containers, so a board belongs to
  # whichever one most recently preceded it.
  traveller = parse_markup(
    '<h3 class="section">Section A</h3>',
    _make_board(
      _make_panel(1),
      north_south_rows=[
        _make_results_row(pairs=_make_pairs(('1', ['Alfa']), ('4', ['Bravo'])))
      ],
    ),
    '<h3 class="section">Section B</h3>',
    _make_board(
      _make_panel(2),
      north_south_rows=[
        _make_results_row(
          pairs=_make_pairs(('1', ['Charlie']), ('4', ['Delta']))
        )
      ],
    ),
  )

  assert [
    board.results[0].north_south.section for board in traveller.boards
  ] == ['A', 'B']


# --- the deal ---


def test_every_seat_is_dealt_thirteen_cards() -> None:
  traveller = parse_markup(_make_board(_make_panel(1, diagram=_make_diagram())))

  deal = traveller.boards[0].deal
  assert deal is not None
  assert {
    seat: len(hand.cards) for seat, hand in deal.hands.items()
  } == dict.fromkeys(Direction, 13)


def test_the_diagram_is_read_as_it_is_laid_out() -> None:
  # North on top, South at the bottom, and the middle block holding West on its
  # left and East on its right. Each seat here holds one whole suit, so which
  # seat got which hand is unambiguous.
  traveller = parse_markup(
    _make_board(
      _make_panel(
        1,
        diagram=_make_diagram(
          {
            Direction.NORTH: {Suit.SPADES: 'A K Q J 10 9 8 7 6 5 4 3 2'},
            Direction.WEST: {Suit.HEARTS: 'A K Q J 10 9 8 7 6 5 4 3 2'},
            Direction.EAST: {Suit.DIAMONDS: 'A K Q J 10 9 8 7 6 5 4 3 2'},
            Direction.SOUTH: {Suit.CLUBS: 'A K Q J 10 9 8 7 6 5 4 3 2'},
          }
        ),
      )
    )
  )

  deal = traveller.boards[0].deal
  assert deal is not None
  assert {seat: hand.cards[0].suit for seat, hand in deal.hands.items()} == {
    Direction.NORTH: Suit.SPADES,
    Direction.WEST: Suit.HEARTS,
    Direction.EAST: Suit.DIAMONDS,
    Direction.SOUTH: Suit.CLUBS,
  }


def test_a_void_written_as_an_em_dash() -> None:
  traveller = parse_markup(
    _make_board(
      _make_panel(
        1,
        diagram=_make_diagram(
          {
            Direction.NORTH: {
              Suit.SPADES: 'A K Q J 10 9 8 7 6 5 4 3 2',
              Suit.HEARTS: VOID,
              Suit.DIAMONDS: VOID,
              Suit.CLUBS: VOID,
            },
            Direction.WEST: {Suit.HEARTS: 'A K Q J 10 9 8 7 6 5 4 3 2'},
            Direction.EAST: {Suit.DIAMONDS: 'A K Q J 10 9 8 7 6 5 4 3 2'},
            Direction.SOUTH: {Suit.CLUBS: 'A K Q J 10 9 8 7 6 5 4 3 2'},
          }
        ),
      )
    )
  )

  deal = traveller.boards[0].deal
  assert deal is not None
  north = deal.hands[Direction.NORTH]
  assert {card.suit for card in north.cards} == {Suit.SPADES}
  assert len(north.cards) == 13


def test_a_panel_printing_no_diagram_has_no_deal() -> None:
  # A panel is still a board without one, and its rows stand on their own.
  traveller = parse_markup(_make_board(_make_panel(1)))

  assert traveller.boards[0].deal is None
  assert not traveller.boards[0].issues


# --- the double-dummy table ---


def test_seats_straddling_seven_tricks() -> None:
  # The page states the strain twice — `1/-S` for the levels, then `S7/6` for
  # the counts — and the counts are what survive.
  spades = _make_glyph(Suit.SPADES)
  traveller = parse_markup(
    _make_board(
      _make_panel(
        1,
        double_dummy=(f'NS: {spades}6/7', f'EW: 1/-{spades} {spades}7/6'),
      )
    )
  )

  tricks = traveller.boards[0].double_dummy_tricks
  assert tricks is not None
  assert tricks[Direction.EAST][Strain.SPADES] == 7
  assert tricks[Direction.WEST][Strain.SPADES] == 6


def test_a_trick_count_below_seven() -> None:
  # A seat that makes nothing has no contract to name, so the page states what
  # it takes instead.
  hearts, clubs = _make_glyph(Suit.HEARTS), _make_glyph(Suit.CLUBS)
  traveller = parse_markup(
    _make_board(
      _make_panel(
        1, double_dummy=(f'NS: {hearts}0 {clubs}5', f'EW: 6{hearts} 2{clubs}')
      )
    )
  )

  tricks = traveller.boards[0].double_dummy_tricks
  assert tricks is not None
  assert tricks[Direction.NORTH][Strain.HEARTS] == 0
  assert tricks[Direction.NORTH][Strain.CLUBS] == 5


def test_an_unreadable_double_dummy_line_costs_only_the_analysis() -> None:
  traveller = parse_markup(
    _make_board(
      _make_panel(
        1, diagram=_make_diagram(), double_dummy=('NS: rubbish', 'EW: rubbish')
      )
    )
  )

  board = traveller.boards[0]
  assert board.double_dummy_tricks is None
  assert board.deal is not None
  assert [issue.code for issue in board.issues] == ['unreadable_double_dummy']


def test_a_double_dummy_block_that_is_not_two_lines_is_reported() -> None:
  # The block states one line per side, so any other count means the markup has
  # moved — and the analysis would otherwise be dropped without a word. Written
  # out here rather than through `_make_panel`, which only builds well-formed
  # blocks.
  traveller = parse_markup(
    _make_board(
      '<div class="board" id="board-1">'
      '<div class="double-dummy"><a href="#ddmakes">Double Dummy Makes</a>'
      '<span>NS: 4H</span></div>'
      '</div>'
    )
  )

  board = traveller.boards[0]
  assert board.double_dummy_tricks is None
  assert [issue.code for issue in board.issues] == ['unreadable_double_dummy']


# --- par ---


def test_par_stated_for_a_seat() -> None:
  # The tournament pages write no `Par:` label — the block's own link carries
  # that — so the value opens with the score.
  spades = _make_glyph(Suit.SPADES)
  traveller = parse_markup(
    _make_board(
      _make_panel(
        1, double_dummy=(f'NS: 4{spades}', 'EW: '), par=f'+420 4{spades}-N'
      )
    )
  )

  par = traveller.boards[0].par
  assert par is not None
  assert par.score == 420
  assert played(par.resolutions[0]).contract.declarer == Direction.NORTH
  # `4S-N` states no result because par makes exactly, so the trick count comes
  # from the double-dummy line beside it.
  assert played(par.resolutions[0]).result.tricks_taken == 10


def test_a_doubling_wrapped_in_a_span_of_its_own() -> None:
  # The renderer sizes the asterisk with a span of its own, inside the value
  # span — which is why par is read from the block's own first span rather than
  # the last one anywhere inside it.
  hearts = _make_glyph(Suit.HEARTS)
  traveller = parse_markup(
    _make_board(
      _make_panel(
        1,
        par=(
          f'-100 4{hearts}'
          '<span style="font-size: 18px;display: inline;">*</span>-N-1'
        ),
      )
    )
  )

  par = traveller.boards[0].par
  assert par is not None
  assert par.score == -100
  assert played(par.resolutions[0]).contract.penalty == Penalty.DOUBLED
  # `-1` is one short of the ten tricks a four-level contract needs.
  assert played(par.resolutions[0]).result.tricks_taken == 9


def test_a_par_result_that_cannot_be_recovered_costs_only_par() -> None:
  # ACBL omits the result whenever par makes exactly, leaving the double-dummy
  # table to supply it — so a panel printing par and no table loses par. That
  # costs par alone, and nothing is raised past the board.
  spades = _make_glyph(Suit.SPADES)
  traveller = parse_markup(
    _make_board(
      _make_panel(1, diagram=_make_diagram(), par=f'+420 4{spades}-N'),
      north_south_rows=[
        _make_results_row(pairs=_make_pairs(('1', ['Alfa']), ('4', ['Bravo'])))
      ],
    )
  )

  board = traveller.boards[0]
  assert board.par is None
  assert board.deal is not None
  assert len(board.results) == 1
  assert [issue.code for issue in board.issues] == ['unreadable_par']


# --- the traveller rows ---


def test_a_row_names_both_pairs() -> None:
  traveller = parse_markup(
    _make_board(
      _make_panel(1),
      north_south_rows=[
        _make_results_row(
          pairs=_make_pairs(
            ('1', ['Ann Alfa', 'Bob Bravo']),
            ('3', ['Gus Charlie', 'Hal Delta']),
          )
        )
      ],
    )
  )

  row = traveller.boards[0].results[0]
  assert row.north_south.number == '1'
  assert row.north_south.side == Side.NORTH_SOUTH
  assert row.north_south.names == ('Ann Alfa', 'Bob Bravo')
  assert row.east_west.number == '3'
  assert row.east_west.names == ('Gus Charlie', 'Hal Delta')


def test_a_player_whose_own_name_is_hyphenated() -> None:
  # Each player sits in a span of their own, so the hyphens between players are
  # never what the names are split on.
  traveller = parse_markup(
    _make_board(
      _make_panel(1),
      north_south_rows=[
        _make_results_row(
          pairs=_make_pairs(
            ('1', ['Ann-Marie Alfa', 'Bob Bravo']), ('3', ['Gus Charlie'])
          )
        )
      ],
    )
  )

  assert traveller.boards[0].results[0].north_south.names == (
    'Ann-Marie Alfa',
    'Bob Bravo',
  )


def test_the_trick_count_is_recovered_from_the_score() -> None:
  # The page's results column is commented out of the markup, so the trick count
  # comes from scoring the contract against the published score.
  spades = _make_glyph(Suit.SPADES)
  traveller = parse_markup(
    _make_board(
      _make_panel(1),
      north_south_rows=[
        _make_results_row(contract=f'4{spades}', declarer='N', score='420')
      ],
    )
  )

  row = traveller.boards[0].results[0]
  contract = played(row.resolution).contract
  assert (contract.level, contract.strain) == (4, Strain.SPADES)
  assert played(row.resolution).result.tricks_taken == 10
  assert row.score == 420


def test_recovery_uses_the_vulnerability_the_board_number_fixes() -> None:
  # Board 2 is North-South vulnerable, so West's doubled six diamonds is not:
  # 1100 is five down at the non-vulnerable rate, which is seven tricks.
  diamonds = _make_glyph(Suit.DIAMONDS)
  traveller = parse_markup(
    _make_board(
      _make_panel(2),
      north_south_rows=[
        _make_results_row(contract=f'6{diamonds}x', declarer='W', score='1100')
      ],
    )
  )

  row = traveller.boards[0].results[0]
  assert played(row.resolution).contract.declarer == Direction.WEST
  assert played(row.resolution).result.tricks_taken == 7
  assert row.score == 1100


def test_a_vulnerable_grand_slam() -> None:
  # Board 2 is North-South vulnerable, so North's seven spades is: 2210 is the
  # vulnerable grand slam, which is all thirteen tricks.
  spades = _make_glyph(Suit.SPADES)
  traveller = parse_markup(
    _make_board(
      _make_panel(2),
      north_south_rows=[
        _make_results_row(contract=f'7{spades}', declarer='N', score='2210')
      ],
    )
  )

  row = traveller.boards[0].results[0]
  assert played(row.resolution).result.tricks_taken == 13
  assert row.score == 2210


def test_a_contract_doubled_more_times_than_exist_is_no_contract() -> None:
  # Nothing is doubled three times, so the cell is nonsense — and nonsense in
  # one cell costs that cell rather than the capture around it.
  spades = _make_glyph(Suit.SPADES)
  traveller = parse_markup(
    _make_board(
      _make_panel(1),
      north_south_rows=[
        _make_results_row(contract=f'4{spades}xxx', declarer='N', score='420')
      ],
    )
  )

  row = traveller.boards[0].results[0]
  assert row.resolution is None
  assert row.score == 420


def test_matchpoints_are_joined_across_the_two_tables() -> None:
  # The page prints the same row twice so each side sees its own matchpoints,
  # and the two are joined on the pair numbers both tables name.
  pairs = _make_pairs(('1', ['Alfa']), ('3', ['Charlie']))
  reversed_pairs = _make_pairs(('3', ['Charlie']), ('1', ['Alfa']))
  traveller = parse_markup(
    _make_board(
      _make_panel(1),
      north_south_rows=[_make_results_row(pairs=pairs, matchpoints='2.50')],
      east_west_rows=[
        _make_results_row(pairs=reversed_pairs, matchpoints='1.50')
      ],
    )
  )

  row = traveller.boards[0].results[0]
  assert row.north_south_matchpoints == 2.5
  assert row.east_west_matchpoints == 1.5


def test_the_east_west_table_lists_its_own_pair_first() -> None:
  # Each table names its own side's pair first, so the East-West one has to be
  # put back into North-South order before the join. Distinct numbers on the two
  # sides are what make a wrong order visible.
  traveller = parse_markup(
    _make_board(
      _make_panel(1),
      north_south_rows=[
        _make_results_row(
          pairs=_make_pairs(('1', ['Alfa']), ('9', ['Charlie'])),
          matchpoints='2.00',
        )
      ],
      east_west_rows=[
        _make_results_row(
          pairs=_make_pairs(('9', ['Charlie']), ('1', ['Alfa'])),
          matchpoints='0.00',
        )
      ],
    )
  )

  row = traveller.boards[0].results[0]
  assert (row.north_south.number, row.east_west.number) == ('1', '9')
  assert row.east_west_matchpoints == 0.0


def test_a_row_naming_no_pairs_joins_to_nothing() -> None:
  # With no pair numbers there is nothing to join on, so the row takes no
  # East-West matchpoints rather than whichever other row is equally anonymous.
  traveller = parse_markup(
    _make_board(
      _make_panel(1),
      north_south_rows=[_make_results_row(matchpoints='2.00')],
      east_west_rows=[_make_results_row(matchpoints='1.00')],
    )
  )

  row = traveller.boards[0].results[0]
  assert row.north_south_matchpoints == 2.0
  assert row.east_west_matchpoints is None


def test_a_passed_out_board() -> None:
  # The page leaves the contract column blank and writes `PASS` where the score
  # goes, so the score column is the only thing telling a passed-out board apart
  # from one nobody played.
  traveller = parse_markup(
    _make_board(
      _make_panel(1),
      north_south_rows=[
        _make_results_row(
          score='PASS',
          matchpoints='1.00',
          pairs=_make_pairs(('1', ['Alfa']), ('3', ['Charlie'])),
        )
      ],
    )
  )

  row = traveller.boards[0].results[0]
  assert isinstance(row.resolution, Passout)
  assert row.score == 0


def test_a_row_the_page_records_no_contract_for() -> None:
  # A board the page has no result for: the contract and declarer cells are
  # blank and `NS` stands where the score goes. The row is kept — the pairs and
  # the fact of the non-result are part of the record.
  traveller = parse_markup(
    _make_board(
      _make_panel(1),
      north_south_rows=[
        _make_results_row(
          score='NS', pairs=_make_pairs(('1', ['Alfa']), ('3', ['Charlie']))
        )
      ],
    )
  )

  row = traveller.boards[0].results[0]
  assert row.resolution is None
  assert row.score is None
  assert row.north_south.number == '1'
  assert not row.issues


def test_a_score_no_result_of_the_contract_reaches_is_reported() -> None:
  # Every extra trick is worth strictly more, so a published score picks out one
  # result — and a score no result reaches means the two disagree. The row keeps
  # its pairs and its score and says what it could not resolve.
  spades = _make_glyph(Suit.SPADES)
  traveller = parse_markup(
    _make_board(
      _make_panel(1),
      north_south_rows=[
        _make_results_row(
          contract=f'4{spades}',
          declarer='N',
          score='421',
          pairs=_make_pairs(('1', ['Alfa']), ('3', ['Charlie'])),
        )
      ],
    )
  )

  row = traveller.boards[0].results[0]
  assert row.resolution is None
  assert row.score == 421
  assert row.north_south.number == '1'
  assert [issue.code for issue in row.issues] == ['unscorable_result']


# --- what could not be read ---


def test_a_page_holding_no_game_reports_an_issue() -> None:
  # A capture that yielded nothing is itself worth recording, so a page with no
  # board panels comes back as an empty traveller rather than as a refusal.
  traveller = parse_markup('<html><body></body></html>')

  assert traveller.boards == ()
  assert [issue.code for issue in traveller.issues] == ['no_board_panels']


def test_a_board_whose_results_table_is_missing_reports_the_lost_rows() -> None:
  # Every board on every capture seen has both tables, so a board with none
  # means the markup has moved and its rows would otherwise vanish quietly.
  traveller = parse_markup(_make_panel(1))

  board = traveller.boards[0]
  assert board.results == ()
  assert [issue.code for issue in board.issues] == ['no_results_table']


def test_a_dealer_contradicting_the_board_number_is_reported() -> None:
  # The dealer follows from the board number and is stored nowhere, so the
  # printed one is read only to be checked. Board 1 is North's deal.
  traveller = parse_markup(
    _make_board(
      _make_panel(1, labels='<span>Dlr: E</span><span>Vul: None</span>')
    )
  )

  assert [issue.code for issue in traveller.boards[0].issues] == [
    'dealer_contradicts_board_number'
  ]
