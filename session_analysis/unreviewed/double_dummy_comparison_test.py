# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for setting a board's result beside what the deal allowed.

The comparison is pure, reading nothing but the session it is handed, so these
tests build their sessions in memory.
"""

from collections.abc import Mapping

from session_analysis.enums import (
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
  Board,
  BoardNumber,
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
from session_analysis.testing.deals import a_suit_to_each_seat, whole_suit
from session_analysis.unreviewed.double_dummy_comparison import compare_boards


def _make_number(number: int) -> BoardNumber:
  """A board-number cell that parsed.

  Only the number is read here, so the dealer and vulnerability it also fixes
  are left at a constant.
  """
  return BoardNumber(
    raw=str(number),
    schedule=Schedule(
      number=number,
      dealer=Direction.NORTH,
      vulnerability=Vulnerability.NONE,
    ),
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


def _make_board(
  number: int,
  *,
  declarer: Direction,
  our_side: Side,
  strain: Strain,
  tricks_taken: int,
  table: SolvedDoubleDummyTricks | None = None,
  deal: Deal | None = None,
  opening_lead: Card | None = None,
) -> Board:
  """A board whose contract cell parsed into a contract and its result.

  `our_side` fills the `side` field of `our_pair`, which is the part the
  comparison reads: which side we sat is what says whether the declarer was us,
  and so which way the sign runs. The level and our pair number are fixed, at
  values no test asserts on.
  """
  return Board(
    number=_make_number(number),
    outcome=Outcome(
      raw=f'4{strain}{declarer}',
      resolution=PlayedContract(
        contract=Contract(
          level=4, strain=strain, declarer=declarer, penalty=Penalty.NONE
        ),
        result=Result(tricks_taken=tricks_taken),
      ),
    ),
    our_pair=PairIdentity(number='3', side=our_side),
    deal=deal,
    solved_double_dummy_tricks=table,
    opening_lead=(
      Lead(raw=f'{opening_lead.rank}{opening_lead.suit}', card=opening_lead)
      if opening_lead
      else None
    ),
  )


def _make_session(*boards: Board) -> Session:
  """A digitized session holding the boards a test cares about."""
  return Session(
    event='Monday Pairs', source=provenance.sheet_source(), boards=boards
  )


def _whole_deal(session: Session) -> Mapping[int, int]:
  """What each board came to against its solved table, where it could."""
  return {
    number: comparison.whole_deal
    for number, comparison in compare_boards(session).items()
    if comparison.whole_deal is not None
  }


def _after_lead(session: Session) -> Mapping[int, int]:
  """What each board came to against the deal after its lead, where it could."""
  return {
    number: comparison.after_lead
    for number, comparison in compare_boards(session).items()
    if comparison.after_lead is not None
  }


# --- reading the board's table ---


def test_a_result_is_compared_with_the_cell_for_its_declarer_and_strain() -> (
  None
):
  session = _make_session(
    _make_board(
      5,
      declarer=Direction.WEST,
      our_side=Side.EAST_WEST,
      strain=Strain.CLUBS,
      tricks_taken=10,
      table=_make_table(declarer=Direction.WEST, strain=Strain.CLUBS, tricks=9),
    )
  )

  # Ten tricks taken where best play by both sides yields nine.
  assert _whole_deal(session) == {5: 1}


def test_a_result_short_of_the_double_dummy_compares_as_a_negative() -> None:
  session = _make_session(
    _make_board(
      5,
      declarer=Direction.NORTH,
      our_side=Side.NORTH_SOUTH,
      strain=Strain.NOTRUMP,
      tricks_taken=7,
      table=_make_table(
        declarer=Direction.NORTH, strain=Strain.NOTRUMP, tricks=9
      ),
    )
  )

  assert _whole_deal(session) == {5: -2}


def test_the_cell_read_is_the_declarers_and_not_the_partners() -> None:
  table = {seat: dict.fromkeys(Strain, 0) for seat in Direction}
  table[Direction.WEST][Strain.CLUBS] = 9
  # The same strain across the table yields a different count, as it can when
  # the opening lead comes from the other side.
  table[Direction.EAST][Strain.CLUBS] = 5
  session = _make_session(
    _make_board(
      5,
      declarer=Direction.WEST,
      our_side=Side.EAST_WEST,
      strain=Strain.CLUBS,
      tricks_taken=10,
      table=table,
    )
  )

  assert _whole_deal(session) == {5: 1}


def test_a_board_carrying_no_table_is_not_compared_with_one() -> None:
  session = _make_session(
    _make_board(
      5,
      declarer=Direction.WEST,
      our_side=Side.EAST_WEST,
      strain=Strain.CLUBS,
      tricks_taken=10,
    )
  )

  # No traveller reached the board, or its deal was too malformed to solve.
  assert _whole_deal(session) == {}


# --- which side the count belongs to ---


def test_the_opponents_falling_short_of_the_count_is_our_gain() -> None:
  session = _make_session(
    _make_board(
      5,
      declarer=Direction.WEST,
      our_side=Side.NORTH_SOUTH,
      strain=Strain.CLUBS,
      tricks_taken=8,
      table=_make_table(
        declarer=Direction.WEST, strain=Strain.CLUBS, tricks=10
      ),
    )
  )

  # West declared against us and took two tricks fewer than best play allows.
  # That is two tricks our way, so it counts up rather than down.
  assert _whole_deal(session) == {5: 2}


def test_the_opponents_beating_the_count_runs_against_us() -> None:
  session = _make_session(
    _make_board(
      5,
      declarer=Direction.WEST,
      our_side=Side.NORTH_SOUTH,
      strain=Strain.CLUBS,
      tricks_taken=11,
      table=_make_table(
        declarer=Direction.WEST, strain=Strain.CLUBS, tricks=10
      ),
    )
  )

  # The overtrick is theirs, so the same surplus that would read as our gain
  # when we declare reads as our loss when we defend.
  assert _whole_deal(session) == {5: -1}


def test_a_board_reconciliation_never_placed_us_on_is_not_compared() -> None:
  session = _make_session(
    Board(
      number=_make_number(5),
      outcome=Outcome(
        raw='4CW',
        resolution=PlayedContract(
          contract=Contract(
            level=4,
            strain=Strain.CLUBS,
            declarer=Direction.WEST,
            penalty=Penalty.NONE,
          ),
          result=Result(tricks_taken=10),
        ),
      ),
      solved_double_dummy_tricks=_make_table(
        declarer=Direction.WEST, strain=Strain.CLUBS, tricks=9
      ),
    )
  )

  # Without our pair there is no telling whether West was us, and so no telling
  # which way the sign runs — half of those would read backwards.
  assert _whole_deal(session) == {}


# --- what leaves the comparison nothing to work from ---


def test_a_board_passed_out_is_not_compared() -> None:
  session = _make_session(
    Board(
      number=_make_number(5),
      outcome=Outcome(raw='PASSED OUT', resolution=Passout()),
      our_pair=PairIdentity(number='3', side=Side.EAST_WEST),
      solved_double_dummy_tricks=_make_table(
        declarer=Direction.WEST, strain=Strain.CLUBS, tricks=9
      ),
    )
  )

  # A board nobody played has no declarer and no strain to look a cell up by.
  assert _whole_deal(session) == {}


def test_a_contract_cell_that_did_not_parse_is_not_compared() -> None:
  session = _make_session(
    Board(
      number=_make_number(5),
      outcome=Outcome(
        raw='4?W+1',
        issues=(
          Issue(
            code='unparseable_contract',
            severity=IssueSeverity.HIGH,
            message="could not parse contract: '4?W+1'",
          ),
        ),
      ),
      our_pair=PairIdentity(number='3', side=Side.EAST_WEST),
      solved_double_dummy_tricks=_make_table(
        declarer=Direction.WEST, strain=Strain.CLUBS, tricks=9
      ),
    )
  )

  assert _whole_deal(session) == {}


def test_a_board_whose_number_went_unread_is_not_compared() -> None:
  session = _make_session(
    Board(
      number=BoardNumber(raw='S'),
      outcome=Outcome(
        raw='4CW',
        resolution=PlayedContract(
          contract=Contract(
            level=4,
            strain=Strain.CLUBS,
            declarer=Direction.WEST,
            penalty=Penalty.NONE,
          ),
          result=Result(tricks_taken=10),
        ),
      ),
      our_pair=PairIdentity(number='3', side=Side.EAST_WEST),
      solved_double_dummy_tricks=_make_table(
        declarer=Direction.WEST, strain=Strain.CLUBS, tricks=9
      ),
    )
  )

  # Comparisons are keyed by board number, so a board without one has nowhere to
  # file its comparison.
  assert _whole_deal(session) == {}


# --- the count after the lead actually made ---

# East is on lead against North and holds only hearts; a heart is therefore the
# one legal lead, and North still takes all thirteen after it.
_A_HEART = Card(rank=Rank.TWO, suit=Suit.HEARTS)


def test_the_play_is_counted_from_the_position_the_lead_left() -> None:
  session = _make_session(
    _make_board(
      5,
      declarer=Direction.NORTH,
      our_side=Side.NORTH_SOUTH,
      strain=Strain.SPADES,
      tricks_taken=11,
      deal=a_suit_to_each_seat(),
      opening_lead=_A_HEART,
    )
  )

  # We declared and took eleven where the position after the lead still held all
  # thirteen, so the play cost us two.
  assert _after_lead(session) == {5: -2}


def test_the_same_board_defended_counts_the_shortfall_our_way() -> None:
  session = _make_session(
    _make_board(
      5,
      declarer=Direction.NORTH,
      our_side=Side.EAST_WEST,
      strain=Strain.SPADES,
      tricks_taken=11,
      deal=a_suit_to_each_seat(),
      opening_lead=_A_HEART,
    )
  )

  # The board above from the other side of the table: the two tricks declarer
  # let slip are two tricks our way.
  assert _after_lead(session) == {5: 2}


def test_the_count_after_the_lead_needs_no_table() -> None:
  session = _make_session(
    _make_board(
      5,
      declarer=Direction.NORTH,
      our_side=Side.NORTH_SOUTH,
      strain=Strain.SPADES,
      tricks_taken=13,
      deal=a_suit_to_each_seat(),
      opening_lead=_A_HEART,
    )
  )

  # The deal alone is solved from the lead on, so a board carrying no table
  # still gets this count.
  assert _after_lead(session) == {5: 0}


def test_a_board_carrying_no_deal_is_not_compared() -> None:
  session = _make_session(
    _make_board(
      5,
      declarer=Direction.NORTH,
      our_side=Side.NORTH_SOUTH,
      strain=Strain.SPADES,
      tricks_taken=11,
      opening_lead=_A_HEART,
    )
  )

  # A sheet records no deal, so a board that reconciliation has not reached has
  # nothing to solve.
  assert _after_lead(session) == {}


def test_a_board_whose_lead_went_unrecorded_is_not_compared() -> None:
  session = _make_session(
    _make_board(
      5,
      declarer=Direction.NORTH,
      our_side=Side.NORTH_SOUTH,
      strain=Strain.SPADES,
      tricks_taken=11,
      deal=a_suit_to_each_seat(),
    )
  )

  assert _after_lead(session) == {}


def test_a_lead_the_leading_hand_does_not_hold_is_not_compared() -> None:
  session = _make_session(
    _make_board(
      5,
      declarer=Direction.NORTH,
      our_side=Side.NORTH_SOUTH,
      strain=Strain.SPADES,
      tricks_taken=11,
      deal=a_suit_to_each_seat(),
      opening_lead=Card(rank=Rank.TWO, suit=Suit.CLUBS),
    )
  )

  # East was on lead holding only hearts, so a club says the lead, the declarer
  # or the board number is wrong. `deal_checks` reports which; this leaves the
  # board uncompared rather than solving an impossible position.
  assert _after_lead(session) == {}


def test_a_malformed_deal_is_not_compared() -> None:
  session = _make_session(
    _make_board(
      5,
      declarer=Direction.NORTH,
      our_side=Side.NORTH_SOUTH,
      strain=Strain.SPADES,
      tricks_taken=11,
      deal=Deal(hands={Direction.NORTH: whole_suit(Suit.SPADES)}),
      opening_lead=_A_HEART,
    )
  )

  # Three seats hold no hand at all, which `deal_checks` reports; solving it
  # would only raise.
  assert _after_lead(session) == {}
