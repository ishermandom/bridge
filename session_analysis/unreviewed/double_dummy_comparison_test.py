# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for setting a board's result beside what the deal allowed.

The comparison is pure, so those tests build their sessions and travellers in
memory. Reading the records back is the exception, and works over real files
under `tmp_path`: finding a session's travellers on disk is what it is for, so a
stream would test something else.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path

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
from session_analysis.notation import STRAINS_LOW_TO_HIGH
from session_analysis.private_paths import PrivateTree
from session_analysis.testing import provenance
from session_analysis.testing.deals import a_suit_to_each_seat, whole_suit
from session_analysis.travellers import (
  Traveller,
  TravellerBoard,
  TravellerSource,
)
from session_analysis.unreviewed.double_dummy_comparison import (
  ComparisonTotals,
  compare_boards,
  read_referenced_travellers,
  recap_of,
)

_CLUB_CAPTURE = 'club/D260629M.pbn'
_ACBL_CAPTURE = 'acbl_club/12345.html'


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


def _make_board(
  number: int,
  *,
  declarer: Direction,
  our_side: Side,
  strain: Strain,
  tricks_taken: int,
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
    opening_lead=(
      Lead(raw=f'{opening_lead.rank}{opening_lead.suit}', card=opening_lead)
      if opening_lead
      else None
    ),
  )


def _make_session(*boards: Board, travellers: tuple[str, ...] = ()) -> Session:
  """A digitized session naming the captures reconciliation consulted."""
  return Session(
    event='Monday Pairs',
    source=provenance.sheet_source(
      travellers=tuple(CaptureReference(path=path) for path in travellers)
    ),
    boards=boards,
  )


def _make_traveller_from(path: str, *boards: TravellerBoard) -> Traveller:
  """A traveller carrying whatever boards a test hands it."""
  return Traveller(
    source=TravellerSource.CLUB_PBN,
    reference=CaptureReference(path=path),
    event='Monday Pairs',
    boards=boards,
  )


def _make_traveller(
  board_number: int,
  *,
  declarer: Direction,
  strain: Strain,
  tricks: int | None,
  path: str = _CLUB_CAPTURE,
) -> Traveller:
  """A traveller stating one cell of its table and leaving the other nineteen.

  A published table holds all twenty cells and writes as `None` any it has
  nothing to say about, so the nineteen no test asserts on are built that way
  rather than left out. Passing `tricks=None` leaves all twenty unstated, which
  is how a source listing only its makeable contracts reads.
  """
  table: dict[Direction, dict[Strain, int | None]] = {
    seat: dict.fromkeys(STRAINS_LOW_TO_HIGH) for seat in Direction
  }
  table[declarer][strain] = tricks
  return _make_traveller_from(
    path, TravellerBoard(number=board_number, double_dummy_tricks=table)
  )


def _whole_deal(
  session: Session, travellers: Sequence[Traveller] = ()
) -> Mapping[int, int]:
  """What each board came to against the published table, where it could."""
  return {
    number: comparison.whole_deal
    for number, comparison in compare_boards(session, travellers).items()
    if comparison.whole_deal is not None
  }


def _after_lead(session: Session) -> Mapping[int, int]:
  """What each board came to against the deal after its lead, where it could."""
  return {
    number: comparison.after_lead
    for number, comparison in compare_boards(session, ()).items()
    if comparison.after_lead is not None
  }


# --- reading the published cell ---


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
    )
  )
  traveller = _make_traveller(
    5, declarer=Direction.WEST, strain=Strain.CLUBS, tricks=9
  )

  # Ten tricks taken where best play by both sides yields nine.
  assert _whole_deal(session, [traveller]) == {5: 1}


def test_a_result_short_of_the_double_dummy_compares_as_a_negative() -> None:
  session = _make_session(
    _make_board(
      5,
      declarer=Direction.NORTH,
      our_side=Side.NORTH_SOUTH,
      strain=Strain.NOTRUMP,
      tricks_taken=7,
    )
  )
  traveller = _make_traveller(
    5, declarer=Direction.NORTH, strain=Strain.NOTRUMP, tricks=9
  )

  assert _whole_deal(session, [traveller]) == {5: -2}


def test_a_cell_for_another_seat_is_not_read_for_this_declarer() -> None:
  session = _make_session(
    _make_board(
      5,
      declarer=Direction.WEST,
      our_side=Side.EAST_WEST,
      strain=Strain.CLUBS,
      tricks_taken=10,
    )
  )
  # The same strain, stated for the seat across the table rather than for ours.
  traveller = _make_traveller(
    5, declarer=Direction.EAST, strain=Strain.CLUBS, tricks=9
  )

  assert _whole_deal(session, [traveller]) == {}


def test_a_cell_the_source_left_unstated_is_not_compared() -> None:
  session = _make_session(
    _make_board(
      5,
      declarer=Direction.WEST,
      our_side=Side.EAST_WEST,
      strain=Strain.CLUBS,
      tricks_taken=5,
    )
  )
  # The club's HTML lists the makeable contracts alone, so it says nothing at
  # all about a declarer held under seven tricks.
  traveller = _make_traveller(
    5, declarer=Direction.WEST, strain=Strain.CLUBS, tricks=None
  )

  assert _whole_deal(session, [traveller]) == {}


def test_a_traveller_publishing_no_analysis_leaves_a_board_uncompared() -> None:
  session = _make_session(
    _make_board(
      5,
      declarer=Direction.WEST,
      our_side=Side.EAST_WEST,
      strain=Strain.CLUBS,
      tricks_taken=10,
    )
  )
  traveller = _make_traveller_from(
    _CLUB_CAPTURE, TravellerBoard(number=5, double_dummy_tricks=None)
  )

  assert _whole_deal(session, [traveller]) == {}


def test_a_board_no_traveller_records_is_not_compared() -> None:
  session = _make_session(
    _make_board(
      5,
      declarer=Direction.WEST,
      our_side=Side.EAST_WEST,
      strain=Strain.CLUBS,
      tricks_taken=10,
    )
  )
  traveller = _make_traveller(
    6, declarer=Direction.WEST, strain=Strain.CLUBS, tricks=9
  )

  assert _whole_deal(session, [traveller]) == {}


def test_a_session_with_no_travellers_compares_nothing() -> None:
  session = _make_session(
    _make_board(
      5,
      declarer=Direction.WEST,
      our_side=Side.EAST_WEST,
      strain=Strain.CLUBS,
      tricks_taken=10,
    )
  )

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
    )
  )
  traveller = _make_traveller(
    5, declarer=Direction.WEST, strain=Strain.CLUBS, tricks=10
  )

  # West declared against us and took two tricks fewer than best play allows.
  # That is two tricks our way, so it counts up rather than down.
  assert _whole_deal(session, [traveller]) == {5: 2}


def test_the_opponents_beating_the_count_runs_against_us() -> None:
  session = _make_session(
    _make_board(
      5,
      declarer=Direction.WEST,
      our_side=Side.NORTH_SOUTH,
      strain=Strain.CLUBS,
      tricks_taken=11,
    )
  )
  traveller = _make_traveller(
    5, declarer=Direction.WEST, strain=Strain.CLUBS, tricks=10
  )

  # The overtrick is theirs, so the same surplus that would read as our gain
  # when we declare reads as our loss when we defend.
  assert _whole_deal(session, [traveller]) == {5: -1}


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
    )
  )
  traveller = _make_traveller(
    5, declarer=Direction.WEST, strain=Strain.CLUBS, tricks=9
  )

  # Without our pair there is no telling whether West was us, and so no telling
  # which way the sign runs — half of those would read backwards.
  assert _whole_deal(session, [traveller]) == {}


# --- what leaves the comparison nothing to work from ---


def test_a_board_passed_out_is_not_compared() -> None:
  session = _make_session(
    Board(
      number=_make_number(5),
      outcome=Outcome(raw='PASSED OUT', resolution=Passout()),
      our_pair=PairIdentity(number='3', side=Side.EAST_WEST),
    )
  )
  traveller = _make_traveller(
    5, declarer=Direction.WEST, strain=Strain.CLUBS, tricks=9
  )

  # A board nobody played has no declarer and no strain to look a cell up by.
  assert _whole_deal(session, [traveller]) == {}


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
    )
  )
  traveller = _make_traveller(
    5, declarer=Direction.WEST, strain=Strain.CLUBS, tricks=9
  )

  assert _whole_deal(session, [traveller]) == {}


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
    )
  )
  traveller = _make_traveller(
    5, declarer=Direction.WEST, strain=Strain.CLUBS, tricks=9
  )

  # Without a number there is no traveller row the board could be matched to.
  assert _whole_deal(session, [traveller]) == {}


# --- more than one source ---


def test_two_sources_stating_the_same_cell_compare_the_board() -> None:
  session = _make_session(
    _make_board(
      5,
      declarer=Direction.WEST,
      our_side=Side.EAST_WEST,
      strain=Strain.CLUBS,
      tricks_taken=10,
    )
  )
  travellers = [
    _make_traveller(
      5,
      declarer=Direction.WEST,
      strain=Strain.CLUBS,
      tricks=9,
      path=_CLUB_CAPTURE,
    ),
    _make_traveller(
      5,
      declarer=Direction.WEST,
      strain=Strain.CLUBS,
      tricks=9,
      path=_ACBL_CAPTURE,
    ),
  ]

  assert _whole_deal(session, travellers) == {5: 1}


def test_a_source_stating_the_cell_answers_where_another_is_silent() -> None:
  session = _make_session(
    _make_board(
      5,
      declarer=Direction.WEST,
      our_side=Side.EAST_WEST,
      strain=Strain.CLUBS,
      tricks_taken=6,
    )
  )
  travellers = [
    _make_traveller(
      5,
      declarer=Direction.WEST,
      strain=Strain.CLUBS,
      tricks=None,
      path=_CLUB_CAPTURE,
    ),
    _make_traveller(
      5,
      declarer=Direction.WEST,
      strain=Strain.CLUBS,
      tricks=5,
      path=_ACBL_CAPTURE,
    ),
  ]

  # Silence is not a disagreement: a source that declined to state the cell
  # leaves the one that stated it to answer.
  assert _whole_deal(session, travellers) == {5: 1}


def test_two_sources_contradicting_each_other_leave_a_board_uncompared() -> (
  None
):
  session = _make_session(
    _make_board(
      5,
      declarer=Direction.WEST,
      our_side=Side.EAST_WEST,
      strain=Strain.CLUBS,
      tricks_taken=10,
    )
  )
  travellers = [
    _make_traveller(
      5,
      declarer=Direction.WEST,
      strain=Strain.CLUBS,
      tricks=9,
      path=_CLUB_CAPTURE,
    ),
    _make_traveller(
      5,
      declarer=Direction.WEST,
      strain=Strain.CLUBS,
      tricks=10,
      path=_ACBL_CAPTURE,
    ),
  ]

  # Nothing picks a winner between two records, so the board goes uncompared.
  assert _whole_deal(session, travellers) == {}


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

  # We declared and took eleven where the position after the lead still held
  # all thirteen, so the play cost us two.
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


def test_this_comparison_needs_no_traveller_of_its_own() -> None:
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

  # Reconciliation wrote the deal onto the board, so the solved count is
  # available where the published table's cell might not be — and this takes no
  # travellers at all, unlike the comparison against that table.
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


# --- the session recap ---

# North holds every spade, so a spade contract declared by North or South takes
# all thirteen whatever is led, and one declared by East or West takes none.
# `testing.deals` argues both.
_A_DIAMOND = Card(rank=Rank.TWO, suit=Suit.DIAMONDS)
_A_CLUB = Card(rank=Rank.TWO, suit=Suit.CLUBS)
_A_SPADE = Card(rank=Rank.TWO, suit=Suit.SPADES)


def _spades_board(
  number: int,
  *,
  declarer: Direction,
  tricks_taken: int,
  opening_lead: Card,
) -> Board:
  """A board of the reasoned deal, played in spades, with us North-South."""
  return _make_board(
    number,
    declarer=declarer,
    our_side=Side.NORTH_SOUTH,
    strain=Strain.SPADES,
    tricks_taken=tricks_taken,
    deal=a_suit_to_each_seat(),
    opening_lead=opening_lead,
  )


def test_our_declared_boards_group_by_which_of_us_declared() -> None:
  session = _make_session(
    # East leads a heart against North; West leads a club against South. Either
    # way the count after the lead is all thirteen.
    _spades_board(
      1, declarer=Direction.NORTH, tricks_taken=11, opening_lead=_A_HEART
    ),
    _spades_board(
      2, declarer=Direction.SOUTH, tricks_taken=13, opening_lead=_A_CLUB
    ),
  )
  travellers = [
    _make_traveller(
      1, declarer=Direction.NORTH, strain=Strain.SPADES, tricks=9
    ),
    _make_traveller(
      2, declarer=Direction.SOUTH, strain=Strain.SPADES, tricks=9
    ),
  ]

  recap = recap_of(compare_boards(session, travellers))

  # North took eleven against a published nine and a solved thirteen; South
  # took thirteen against the same nine and thirteen.
  assert recap.declaring.by_seat == {
    Direction.NORTH: ComparisonTotals(boards=1, whole_deal=2, after_lead=-2),
    Direction.SOUTH: ComparisonTotals(boards=1, whole_deal=4, after_lead=0),
  }
  assert not recap.defending.by_seat


def test_our_defended_boards_group_by_which_of_us_led() -> None:
  session = _make_session(
    # East declaring puts South on lead, holding the diamonds; West declaring
    # puts North on lead, holding the spades.
    _spades_board(
      1, declarer=Direction.EAST, tricks_taken=2, opening_lead=_A_DIAMOND
    ),
    _spades_board(
      2, declarer=Direction.WEST, tricks_taken=1, opening_lead=_A_SPADE
    ),
  )
  travellers = [
    _make_traveller(1, declarer=Direction.EAST, strain=Strain.SPADES, tricks=1),
    _make_traveller(2, declarer=Direction.WEST, strain=Strain.SPADES, tricks=1),
  ]

  recap = recap_of(compare_boards(session, travellers))

  # Neither opponent can reach a trump, so the solved count is none for both,
  # and each took more than that, which runs against us. Against the published
  # count, the board we led from North came out even and the one from South a
  # trick down.
  assert recap.defending.by_seat == {
    Direction.NORTH: ComparisonTotals(boards=1, whole_deal=0, after_lead=-1),
    Direction.SOUTH: ComparisonTotals(boards=1, whole_deal=-1, after_lead=-2),
  }
  assert not recap.declaring.by_seat


def test_the_whole_session_totals_every_row() -> None:
  session = _make_session(
    _spades_board(
      1, declarer=Direction.NORTH, tricks_taken=11, opening_lead=_A_HEART
    ),
    _spades_board(
      2, declarer=Direction.EAST, tricks_taken=2, opening_lead=_A_DIAMOND
    ),
  )
  travellers = [
    _make_traveller(
      1, declarer=Direction.NORTH, strain=Strain.SPADES, tricks=9
    ),
    _make_traveller(2, declarer=Direction.EAST, strain=Strain.SPADES, tricks=1),
  ]

  recap = recap_of(compare_boards(session, travellers))

  # One board declared and one defended, added across both halves.
  assert recap.whole_session == ComparisonTotals(
    boards=2, whole_deal=1, after_lead=-4
  )


def test_a_board_carrying_only_one_count_sits_out_of_the_recap() -> None:
  session = _make_session(
    _spades_board(
      1, declarer=Direction.NORTH, tricks_taken=11, opening_lead=_A_HEART
    )
  )

  recap = recap_of(compare_boards(session, []))

  # The deal solves, but no traveller states a cell, so the two totals would
  # cover different boards. The board sits out rather than making them
  # incomparable.
  assert recap.whole_session == ComparisonTotals(
    boards=0, whole_deal=0, after_lead=0
  )
  assert recap.partly_compared == 1


# --- reading the records a session names ---


def _store(tree: PrivateTree, path: str, traveller: Traveller) -> None:
  """Write a traveller's record where the store files one."""
  record = tree.traveller_records / f'{path}.json'
  record.parent.mkdir(parents=True, exist_ok=True)
  record.write_text(traveller.model_dump_json())


def test_only_the_travellers_a_session_names_are_read(tmp_path: Path) -> None:
  tree = PrivateTree(tmp_path)
  _store(
    tree,
    _CLUB_CAPTURE,
    _make_traveller(
      5,
      declarer=Direction.WEST,
      strain=Strain.CLUBS,
      tricks=9,
      path=_CLUB_CAPTURE,
    ),
  )
  _store(
    tree,
    'club/D260706M.pbn',
    _make_traveller(
      5,
      declarer=Direction.WEST,
      strain=Strain.CLUBS,
      tricks=9,
      path='club/D260706M.pbn',
    ),
  )
  session = _make_session(travellers=(_CLUB_CAPTURE,))

  read = read_referenced_travellers(tree, session)

  # The other week's capture is stored too, and numbers its boards the same way;
  # naming the captures is what keeps it out of this session's comparison.
  assert [one.reference.path for one in read.value] == [_CLUB_CAPTURE]
  assert not read.issues


def test_a_session_naming_no_travellers_reads_nothing(tmp_path: Path) -> None:
  read = read_referenced_travellers(PrivateTree(tmp_path), _make_session())

  assert not read.value
  assert not read.issues


def test_a_record_a_session_names_but_nothing_stored_is_reported(
  tmp_path: Path,
) -> None:
  session = _make_session(travellers=(_CLUB_CAPTURE,))

  read = read_referenced_travellers(PrivateTree(tmp_path), session)

  assert not read.value
  assert [issue.code for issue in read.issues] == [
    'unreadable_traveller_record'
  ]


def test_a_record_that_no_longer_parses_is_reported_and_stepped_over(
  tmp_path: Path,
) -> None:
  tree = PrivateTree(tmp_path)
  stale = tree.traveller_records / f'{_ACBL_CAPTURE}.json'
  stale.parent.mkdir(parents=True)
  stale.write_text('{"source": "who knows"}')
  _store(
    tree,
    _CLUB_CAPTURE,
    _make_traveller(
      5,
      declarer=Direction.WEST,
      strain=Strain.CLUBS,
      tricks=9,
      path=_CLUB_CAPTURE,
    ),
  )
  session = _make_session(travellers=(_ACBL_CAPTURE, _CLUB_CAPTURE))

  read = read_referenced_travellers(tree, session)

  # The readable record still supplies its comparisons; only the stale one is
  # set aside.
  assert [one.reference.path for one in read.value] == [_CLUB_CAPTURE]
  assert 'holds no traveller record' in read.issues[0].message
