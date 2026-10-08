# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for totalling a session by role, by seat, and as a whole.

Summarizing is pure, so every test builds its boards and travellers in memory.
The double-dummy counts are handed in already made, as the transcript hands
them: how they are made is `double_dummy_comparison`'s to test, and what is
tested here is how they are added up.
"""

from collections.abc import Mapping, Sequence
from decimal import Decimal

from session_analysis.enums import (
  Direction,
  Penalty,
  Side,
  Strain,
  Vulnerability,
)
from session_analysis.models import (
  Board,
  BoardNumber,
  CaptureReference,
  Contract,
  Outcome,
  PairIdentity,
  Passout,
  PlayedContract,
  Result,
  Schedule,
)
from session_analysis.travellers import (
  Traveller,
  TravellerBoard,
  TravellerResult,
  TravellerSource,
)
from session_analysis.unreviewed.double_dummy_comparison import (
  BoardComparison,
)
from session_analysis.unreviewed.session_summary import (
  SessionSummary,
  Totals,
  summarize,
)


def _make_board(
  number: int,
  *,
  declarer: Direction,
  matchpoints: float | None = None,
  section: str | None = None,
) -> Board:
  """A board we sat East-West on, played in a contract by `declarer`.

  The contract and result are fixed, at values nothing here asserts on: which
  side declared is all the grouping reads from them.
  """
  return Board(
    number=BoardNumber(
      raw=str(number),
      schedule=Schedule(
        number=number,
        dealer=Direction.NORTH,
        vulnerability=Vulnerability.NONE,
      ),
    ),
    outcome=Outcome(
      raw=f'4S{declarer}',
      resolution=PlayedContract(
        contract=Contract(
          level=4, strain=Strain.SPADES, declarer=declarer, penalty=Penalty.NONE
        ),
        result=Result(tricks_taken=10),
      ),
    ),
    matchpoints=matchpoints,
    our_pair=PairIdentity(number='3', side=Side.EAST_WEST, section=section),
  )


def _make_row(
  north_south: float, east_west: float, *, section: str | None = None
) -> TravellerResult:
  """One table's result on a board, scored for each side."""
  return TravellerResult(
    north_south=PairIdentity(
      number='1', side=Side.NORTH_SOUTH, section=section
    ),
    east_west=PairIdentity(number='2', side=Side.EAST_WEST, section=section),
    north_south_matchpoints=north_south,
    east_west_matchpoints=east_west,
  )


def _make_traveller(*boards: TravellerBoard) -> Traveller:
  """A traveller carrying whatever boards a test hands it."""
  return Traveller(
    source=TravellerSource.CLUB_HTML,
    reference=CaptureReference(path='club/260629.html'),
    event='Monday Pairs',
    boards=boards,
  )


def _scored_out_of(top: float, *board_numbers: int) -> Traveller:
  """A traveller whose every board was scored on the same top."""
  return _make_traveller(
    *(
      TravellerBoard(number=number, results=(_make_row(top, 0),))
      for number in board_numbers
    )
  )


def _summarize(
  *boards: Board,
  travellers: Sequence[Traveller] = (),
  comparisons: Mapping[int, BoardComparison] | None = None,
) -> SessionSummary:
  """The summary of some boards, with no travellers or counts unless given."""
  return summarize(boards, travellers, comparisons or {})


# --- grouping by role and seat ---


def test_a_board_we_declared_goes_under_the_seat_that_declared() -> None:
  summary = _summarize(_make_board(1, declarer=Direction.WEST))

  assert summary.declaring == {Direction.WEST: Totals(boards=1)}
  assert not summary.defending


def test_a_board_we_defended_goes_under_the_seat_that_led() -> None:
  # North declaring puts East, on North's left, on lead.
  summary = _summarize(_make_board(1, declarer=Direction.NORTH))

  assert summary.defending == {Direction.EAST: Totals(boards=1)}
  assert not summary.declaring


def test_the_seats_are_every_one_we_declared_or_led_from() -> None:
  summary = _summarize(
    # South declaring puts West on lead.
    _make_board(1, declarer=Direction.SOUTH),
    _make_board(2, declarer=Direction.EAST),
  )

  # In the order they sit round, however the boards fell.
  assert summary.seats == (Direction.EAST, Direction.WEST)


def test_a_passed_out_board_counts_only_toward_the_whole_session() -> None:
  passed_out = _make_board(2, declarer=Direction.EAST).model_copy(
    update={'outcome': Outcome(raw='---', resolution=Passout())}
  )

  summary = _summarize(_make_board(1, declarer=Direction.EAST), passed_out)

  # No declarer means no seat of ours to put it under.
  assert summary.unplaced == 1
  assert summary.whole_session.boards == 2
  assert summary.declaring == {Direction.EAST: Totals(boards=1)}


# --- matchpoints ---


def test_the_percentage_is_the_matchpoints_over_the_sum_of_tops() -> None:
  summary = _summarize(
    _make_board(1, declarer=Direction.EAST, matchpoints=6),
    _make_board(2, declarer=Direction.EAST, matchpoints=2),
    travellers=[_scored_out_of(8, 1, 2)],
  )

  # Eight of a possible sixteen.
  assert summary.whole_session.percentage == 50


def test_a_bottom_board_is_scored_rather_than_left_out() -> None:
  summary = _summarize(
    _make_board(1, declarer=Direction.EAST, matchpoints=0),
    travellers=[_scored_out_of(8, 1)],
  )

  assert summary.whole_session.scored == 1
  assert summary.whole_session.percentage == 0


def test_a_board_with_no_top_sits_out_of_the_matchpoints() -> None:
  summary = _summarize(
    _make_board(1, declarer=Direction.EAST, matchpoints=6),
    _make_board(2, declarer=Direction.EAST, matchpoints=2),
    # Only board one was captured, so board two has no top to score against.
    travellers=[_scored_out_of(8, 1)],
  )

  assert summary.whole_session.boards == 2
  assert summary.whole_session.scored == 1
  assert summary.whole_session.percentage == 75


def test_a_group_nothing_scored_has_no_percentage() -> None:
  summary = _summarize(_make_board(1, declarer=Direction.EAST))

  assert summary.whole_session.percentage is None


# --- the top ---


def test_the_top_is_what_a_row_s_two_scores_add_up_to() -> None:
  traveller = _make_traveller(
    TravellerBoard(number=1, results=(_make_row(5, 3),))
  )

  summary = _summarize(
    _make_board(1, declarer=Direction.EAST), travellers=[traveller]
  )

  assert summary.tops == (Decimal(8),)


def test_only_the_rows_in_our_section_set_the_top() -> None:
  # Section B is smaller and outnumbers ours on this traveller, so a top read
  # from every row alike would be B's three rather than our eight.
  traveller = _make_traveller(
    TravellerBoard(
      number=1,
      results=(
        _make_row(8, 0, section='A'),
        _make_row(3, 0, section='B'),
        _make_row(2, 1, section='B'),
      ),
    )
  )

  summary = _summarize(
    _make_board(1, declarer=Direction.EAST, section='A'),
    travellers=[traveller],
  )

  assert summary.tops == (Decimal(8),)


def test_an_adjusted_row_does_not_move_the_top() -> None:
  # Average-plus to both sides adds up to more than the top.
  traveller = _make_traveller(
    TravellerBoard(
      number=1,
      results=(_make_row(8, 0), _make_row(4, 4), _make_row(4.8, 4.8)),
    )
  )

  summary = _summarize(
    _make_board(1, declarer=Direction.EAST), travellers=[traveller]
  )

  assert summary.tops == (Decimal(8),)


def test_two_totals_tied_for_most_common_name_no_top() -> None:
  traveller = _make_traveller(
    TravellerBoard(number=1, results=(_make_row(8, 0), _make_row(4.8, 4.8)))
  )

  summary = _summarize(
    _make_board(1, declarer=Direction.EAST, matchpoints=6),
    travellers=[traveller],
  )

  assert not summary.tops
  assert summary.whole_session.scored == 0


def test_a_board_played_fewer_times_brings_a_top_of_its_own() -> None:
  traveller = _make_traveller(
    TravellerBoard(number=1, results=(_make_row(8, 0),)),
    TravellerBoard(number=2, results=(_make_row(7, 0),)),
  )

  summary = _summarize(
    _make_board(1, declarer=Direction.EAST),
    _make_board(2, declarer=Direction.EAST),
    travellers=[traveller],
  )

  assert summary.tops == (Decimal(7), Decimal(8))


# --- the double-dummy counts ---


def test_the_counts_total_across_a_role() -> None:
  summary = _summarize(
    _make_board(1, declarer=Direction.EAST),
    _make_board(2, declarer=Direction.WEST),
    comparisons={
      1: BoardComparison(whole_deal=1, after_lead=-1),
      2: BoardComparison(whole_deal=2, after_lead=0),
    },
  )

  assert summary.declaring_total == Totals(
    boards=2, compared=2, whole_deal=3, after_lead=-1
  )


def test_a_board_carrying_only_one_count_sits_out_of_the_counts() -> None:
  summary = _summarize(
    _make_board(1, declarer=Direction.EAST),
    comparisons={1: BoardComparison(whole_deal=1, after_lead=None)},
  )

  # Totalling the two counts over different boards would leave them
  # incomparable, so the board sits out of both rather than one.
  assert summary.whole_session == Totals(boards=1)
