# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for joining a digitized sheet to the travellers of the same session."""

from collections.abc import Sequence

from session_analysis import board_rotation
from session_analysis.enums import (
  Direction,
  IssueSeverity,
  Penalty,
  Rank,
  Side,
  Strain,
  Suit,
)
from session_analysis.models import (
  Board,
  BoardNumber,
  CaptureReference,
  Card,
  Contract,
  Deal,
  Hand,
  Issue,
  Lead,
  Outcome,
  PairIdentity,
  Passout,
  PlayedContract,
  Resolution,
  Result,
  Schedule,
  Session,
)
from session_analysis.testing import provenance
from session_analysis.travellers import (
  Traveller,
  TravellerBoard,
  TravellerResult,
  TravellerSource,
)
from session_analysis.unreviewed.reconciliation import (
  build_enrichments,
  reconcile_session,
)

OUR_NAME = 'First Last'

# A deal whose seats hold visibly different suits, so a test can name a card and
# say which seat must have held it. Not a legal deal — thirteen cards to a hand
# is `deal_checks`' subject, and spelling four full hands here would bury what
# each test is actually about.
_NORTH_CARD = Card(rank=Rank.ACE, suit=Suit.SPADES)
_EAST_CARD = Card(rank=Rank.KING, suit=Suit.HEARTS)
_SOUTH_CARD = Card(rank=Rank.QUEEN, suit=Suit.DIAMONDS)
_WEST_CARD = Card(rank=Rank.JACK, suit=Suit.CLUBS)

_DEAL = Deal(
  hands={
    Direction.NORTH: Hand(cards=(_NORTH_CARD,)),
    Direction.EAST: Hand(cards=(_EAST_CARD,)),
    Direction.SOUTH: Hand(cards=(_SOUTH_CARD,)),
    Direction.WEST: Hand(cards=(_WEST_CARD,)),
  }
)


def _played(
  level: int = 4,
  strain: Strain = Strain.SPADES,
  declarer: Direction = Direction.NORTH,
  tricks_taken: int = 10,
) -> Resolution:
  """A played contract and its result."""
  return PlayedContract(
    contract=Contract(
      level=level, strain=strain, declarer=declarer, penalty=Penalty.NONE
    ),
    result=Result(tricks_taken=tricks_taken),
  )


def _pair(
  number: str, side: Side, *names: str, section: str | None = None
) -> PairIdentity:
  """A pair identity, named as much or as little as a source would give."""
  return PairIdentity(
    number=number, side=side, section=section, names=tuple(names)
  )


def _make_traveller(
  source: TravellerSource = TravellerSource.CLUB_HTML,
  *,
  path: str = 'club/game.html',
  boards: Sequence[TravellerBoard] = (),
) -> Traveller:
  """A traveller carrying the boards a test cares about."""
  return Traveller(
    source=source,
    reference=CaptureReference(path=path),
    event='A Club Game',
    boards=tuple(boards),
  )


def _our_board(
  number: int = 1,
  *,
  side: Side = Side.NORTH_SOUTH,
  our_names: Sequence[str] = ('First Last', 'Partner Name'),
  opponent_names: Sequence[str] = ('Other Player', 'Their Partner'),
  resolution: Resolution | None = None,
  matchpoints: float = 6.0,
  deal: Deal | None = None,
) -> TravellerBoard:
  """A traveller board holding one row, which our pair sat in.

  `side` decides which way round our pair sat, so a test can put us East-West
  without restating both identities.
  """
  us = _pair('6', side, *our_names)
  them = _pair(
    '4',
    Side.EAST_WEST if side is Side.NORTH_SOUTH else Side.NORTH_SOUTH,
    *opponent_names,
  )
  north_south, east_west = (
    (us, them) if side is Side.NORTH_SOUTH else (them, us)
  )
  return TravellerBoard(
    number=number,
    deal=deal,
    results=(
      TravellerResult(
        north_south=north_south,
        east_west=east_west,
        resolution=resolution if resolution else _played(),
        north_south_matchpoints=(
          matchpoints if side is Side.NORTH_SOUTH else 0.0
        ),
        east_west_matchpoints=(matchpoints if side is Side.EAST_WEST else 0.0),
      ),
    ),
  )


def _sheet_board(
  number: int = 1,
  *,
  resolution: Resolution | None = None,
  lead: Card | None = None,
) -> Board:
  """One row of a digitized sheet, with its number resolved."""
  return Board(
    number=BoardNumber(
      raw=str(number),
      schedule=Schedule(
        number=number,
        dealer=board_rotation.dealer_for_board(number),
        vulnerability=board_rotation.vulnerability_for_board(number),
      ),
    ),
    outcome=Outcome(raw='', resolution=resolution if resolution else _played()),
    opening_lead=(
      Lead(raw=f'{lead.rank}{lead.suit}', card=lead) if lead else None
    ),
  )


def _make_session(boards: Sequence[Board]) -> Session:
  """A digitized session carrying the rows a test cares about."""
  return Session(
    event='A Club Game',
    source=provenance.sheet_source(path='scan.jpg', content_hash='hash'),
    boards=tuple(boards),
  )


def _codes(issues: Sequence[Issue]) -> list[str]:
  """The codes of a run of issues, for asserting on what was reported."""
  return [issue.code for issue in issues]


# --- finding our row ---


def test_our_row_is_found_when_we_sat_north_south() -> None:
  travellers = [_make_traveller(boards=[_our_board(side=Side.NORTH_SOUTH)])]

  enrichments = build_enrichments(travellers, our_name=OUR_NAME).value

  assert enrichments[1].our_pair == _pair(
    '6', Side.NORTH_SOUTH, 'First Last', 'Partner Name'
  )
  assert enrichments[1].opponents == _pair(
    '4', Side.EAST_WEST, 'Other Player', 'Their Partner'
  )


def test_our_row_is_found_when_we_sat_east_west() -> None:
  travellers = [_make_traveller(boards=[_our_board(side=Side.EAST_WEST)])]

  enrichments = build_enrichments(travellers, our_name=OUR_NAME).value

  assert enrichments[1].our_pair == _pair(
    '6', Side.EAST_WEST, 'First Last', 'Partner Name'
  )
  assert enrichments[1].matchpoints == 6.0


def test_our_direction_may_differ_between_boards_of_one_session() -> None:
  # A one-winner movement sits one pair both ways over a session, so the side is
  # read per board rather than fixed for the whole traveller.
  travellers = [
    _make_traveller(
      boards=[
        _our_board(1, side=Side.NORTH_SOUTH),
        _our_board(2, side=Side.EAST_WEST),
      ]
    )
  ]

  enrichments = build_enrichments(travellers, our_name=OUR_NAME).value

  first, second = enrichments[1].our_pair, enrichments[2].our_pair
  assert first and second
  assert first.side is Side.NORTH_SOUTH
  assert second.side is Side.EAST_WEST


def test_a_surname_alone_matches_the_configured_full_name() -> None:
  # A club recap whose standings could not be read prints board-row surnames.
  travellers = [
    _make_traveller(boards=[_our_board(our_names=('Last', 'Partner'))])
  ]

  enrichments = build_enrichments(travellers, our_name='First Last').value

  assert enrichments[1].our_pair is not None


def test_name_matching_ignores_case_and_spacing() -> None:
  travellers = [
    _make_traveller(boards=[_our_board(our_names=('FIRST  LAST', 'Partner'))])
  ]

  enrichments = build_enrichments(travellers, our_name='First Last').value

  assert enrichments[1].our_pair is not None


def test_a_different_player_sharing_our_surname_does_not_match() -> None:
  # `Other Last` is a namesake, not us. Matching a bare surname against every
  # printed full name would claim them, so a full name must match in full.
  travellers = [
    _make_traveller(boards=[_our_board(our_names=('Other Last', 'Partner'))])
  ]

  read = build_enrichments(travellers, our_name='First Last')

  assert read.value[1].our_pair is None
  assert _codes(read.value[1].issues) == ['our_row_not_found']


def test_a_board_naming_us_twice_is_reported_rather_than_guessed_at() -> None:
  ambiguous = TravellerBoard(
    number=1,
    results=(
      TravellerResult(
        north_south=_pair('6', Side.NORTH_SOUTH, 'First Last', 'Partner'),
        east_west=_pair('4', Side.EAST_WEST, 'Other', 'Player'),
        resolution=_played(),
      ),
      TravellerResult(
        north_south=_pair('7', Side.NORTH_SOUTH, 'First Last', 'Someone'),
        east_west=_pair('5', Side.EAST_WEST, 'Another', 'Player'),
        resolution=_played(),
      ),
    ),
  )

  read = build_enrichments(
    [_make_traveller(boards=[ambiguous])], our_name=OUR_NAME
  )

  assert read.value[1].our_pair is None
  # Reported against the board rather than the session, so that an ambiguity on
  # a board the sheet never played rides an enrichment nothing consults.
  assert _codes(read.value[1].issues) == [
    'our_row_ambiguous',
    'our_row_not_found',
  ]
  assert read.issues == ()
  # A board that named us twice is not one that named us nowhere: reporting it
  # as one would send a reviewer hunting a misspelling that is not there, and
  # would put the whole capture in doubt as the wrong session's.
  assert 'several' in read.value[1].issues[1].message


def test_a_traveller_naming_us_nowhere_is_reported_on_the_session() -> None:
  travellers = [
    _make_traveller(boards=[_our_board(our_names=('Someone Else', 'Partner'))])
  ]

  read = build_enrichments(travellers, our_name=OUR_NAME)

  assert 'traveller_never_names_us' in _codes(read.issues)


def test_a_board_nobody_played_is_not_reported_as_missing_us() -> None:
  # A hand record lists every board dealt and no results at all; a board with no
  # rows names nobody, which is not the same as failing to find us.
  hand_record = _make_traveller(
    TravellerSource.CLUB_PBN,
    path='club/game.pbn',
    boards=[TravellerBoard(number=1, deal=_DEAL)],
  )

  read = build_enrichments([hand_record], our_name=OUR_NAME)

  assert read.issues == ()
  assert read.value[1].issues == ()
  assert read.value[1].deal == _DEAL


# --- merging two sources ---


def test_two_sources_agreeing_merge_without_complaint() -> None:
  travellers = [
    _make_traveller(TravellerSource.CLUB_HTML, boards=[_our_board()]),
    _make_traveller(
      TravellerSource.ACBL_CLUB, path='acbl/1.html', boards=[_our_board()]
    ),
  ]

  read = build_enrichments(travellers, our_name=OUR_NAME)

  assert read.value[1].issues == ()
  assert read.value[1].matchpoints == 6.0


def test_a_surname_source_and_a_full_name_source_merge_to_full_names() -> None:
  # The same pair written at two levels of detail is one pair, not a
  # disagreement — so the fuller spelling wins and nothing is reported.
  travellers = [
    _make_traveller(
      TravellerSource.CLUB_HTML,
      boards=[_our_board(our_names=('Last', 'Partner'))],
    ),
    _make_traveller(
      TravellerSource.ACBL_CLUB,
      path='acbl/1.html',
      boards=[_our_board(our_names=('First Last', 'Some Partner'))],
    ),
  ]

  read = build_enrichments(travellers, our_name=OUR_NAME)

  merged_pair = read.value[1].our_pair
  assert merged_pair
  assert merged_pair.names == ('First Last', 'Some Partner')
  assert read.value[1].issues == ()


def test_sources_naming_different_pair_numbers_disagree() -> None:
  travellers = [
    _make_traveller(TravellerSource.CLUB_HTML, boards=[_our_board()]),
    _make_traveller(
      TravellerSource.ACBL_CLUB,
      path='acbl/1.html',
      boards=[
        TravellerBoard(
          number=1,
          results=(
            TravellerResult(
              # The same players, seated as a different pair number.
              north_south=_pair(
                '9', Side.NORTH_SOUTH, 'First Last', 'Partner Name'
              ),
              east_west=_pair(
                '4', Side.EAST_WEST, 'Other Player', 'Their Partner'
              ),
              resolution=_played(),
            ),
          ),
        )
      ],
    ),
  ]

  read = build_enrichments(travellers, our_name=OUR_NAME)

  assert read.value[1].our_pair is None
  assert 'traveller_sources_disagree' in _codes(read.value[1].issues)


def test_sources_disagreeing_on_what_we_played_leave_it_unfilled() -> None:
  travellers = [
    _make_traveller(
      TravellerSource.CLUB_HTML, boards=[_our_board(resolution=_played())]
    ),
    _make_traveller(
      TravellerSource.ACBL_CLUB,
      path='acbl/1.html',
      boards=[_our_board(resolution=_played(level=3))],
    ),
  ]

  read = build_enrichments(travellers, our_name=OUR_NAME)

  # No silent tiebreak: neither candidate is taken.
  assert read.value[1].resolution is None
  assert 'traveller_sources_disagree' in _codes(read.value[1].issues)


def test_a_hand_record_supplies_the_deal_a_recap_lacks() -> None:
  # The club publishes a PBN listing every board dealt with no play, and an HTML
  # recap covering the boards reached. The two contribute different fields of
  # one board rather than contradicting each other.
  travellers = [
    _make_traveller(
      TravellerSource.CLUB_PBN,
      path='club/game.pbn',
      boards=[TravellerBoard(number=1, deal=_DEAL)],
    ),
    _make_traveller(TravellerSource.CLUB_HTML, boards=[_our_board()]),
  ]

  read = build_enrichments(travellers, our_name=OUR_NAME)

  assert read.value[1].deal == _DEAL
  assert read.value[1].matchpoints == 6.0
  assert read.value[1].issues == ()


def test_two_captures_of_one_source_both_contribute() -> None:
  # The club's PBNs come in two kinds — a hand record with no play, and one
  # carrying every table's results — and both parse as the same source. Merging
  # keyed on the source alone would let whichever came second displace the
  # first.
  travellers = [
    _make_traveller(
      TravellerSource.CLUB_PBN,
      path='club/hands.pbn',
      boards=[TravellerBoard(number=1, deal=_DEAL)],
    ),
    _make_traveller(
      TravellerSource.CLUB_PBN,
      path='club/results.pbn',
      boards=[_our_board()],
    ),
  ]

  read = build_enrichments(travellers, our_name=OUR_NAME)

  assert read.value[1].deal == _DEAL
  assert read.value[1].matchpoints == 6.0
  assert read.value[1].issues == ()


def test_a_disagreement_names_the_capture_not_just_its_source() -> None:
  travellers = [
    _make_traveller(
      TravellerSource.CLUB_PBN,
      path='club/first.pbn',
      boards=[_our_board(resolution=_played(level=3))],
    ),
    _make_traveller(
      TravellerSource.CLUB_PBN,
      path='club/second.pbn',
      boards=[_our_board(resolution=_played(level=4))],
    ),
  ]

  read = build_enrichments(travellers, our_name=OUR_NAME)

  message = read.value[1].issues[0].message
  assert 'club/first.pbn' in message
  assert 'club/second.pbn' in message


# --- cross-checks against the sheet ---


def test_an_agreeing_sheet_and_traveller_raise_nothing() -> None:
  session = reconcile_session(
    _make_session([_sheet_board()]),
    [_make_traveller(boards=[_our_board()])],
    our_name=OUR_NAME,
  )

  assert session.boards[0].issues == ()


def test_a_disagreeing_contract_is_reported() -> None:
  session = reconcile_session(
    _make_session([_sheet_board(resolution=_played(level=3))]),
    [_make_traveller(boards=[_our_board(resolution=_played(level=4))])],
    our_name=OUR_NAME,
  )

  assert _codes(session.boards[0].issues) == ['sheet_contract_disagreement']


def test_a_disagreeing_declarer_is_reported_on_its_own() -> None:
  # The declarer is checked apart from the rest of the contract: the validator
  # cannot check it at all, and neither record is authoritative about it.
  session = reconcile_session(
    _make_session([_sheet_board(resolution=_played(declarer=Direction.SOUTH))]),
    [
      _make_traveller(
        boards=[_our_board(resolution=_played(declarer=Direction.NORTH))]
      )
    ],
    our_name=OUR_NAME,
  )

  assert _codes(session.boards[0].issues) == ['sheet_declarer_disagreement']


def test_a_disagreeing_trick_count_is_reported() -> None:
  session = reconcile_session(
    _make_session([_sheet_board(resolution=_played(tricks_taken=9))]),
    [_make_traveller(boards=[_our_board(resolution=_played(tricks_taken=10))])],
    our_name=OUR_NAME,
  )

  assert _codes(session.boards[0].issues) == ['sheet_result_disagreement']


def test_a_passout_against_a_played_contract_is_reported() -> None:
  session = reconcile_session(
    _make_session([_sheet_board(resolution=Passout())]),
    [_make_traveller(boards=[_our_board(resolution=_played())])],
    our_name=OUR_NAME,
  )

  assert _codes(session.boards[0].issues) == ['sheet_play_disagreement']


# --- enrichment ---


def test_the_reconciled_subset_is_copied_onto_the_board() -> None:
  session = reconcile_session(
    _make_session([_sheet_board()]),
    [_make_traveller(boards=[_our_board(deal=_DEAL)])],
    our_name=OUR_NAME,
  )

  board = session.boards[0]
  assert board.deal == _DEAL
  assert board.matchpoints == 6.0
  assert board.our_pair is not None
  assert board.opponents is not None


def test_the_captures_consulted_are_recorded_on_the_session() -> None:
  session = reconcile_session(
    _make_session([_sheet_board()]),
    [
      _make_traveller(TravellerSource.CLUB_HTML, path='club/game.html'),
      _make_traveller(TravellerSource.ACBL_CLUB, path='acbl/1.html'),
    ],
    our_name=OUR_NAME,
  )

  assert [reference.path for reference in session.source.travellers] == [
    'club/game.html',
    'acbl/1.html',
  ]


def test_a_sheet_board_no_traveller_covers_is_reported() -> None:
  session = reconcile_session(
    _make_session([_sheet_board(number=7)]),
    [_make_traveller(boards=[_our_board(number=1)])],
    our_name=OUR_NAME,
  )

  assert _codes(session.boards[0].issues) == ['board_not_in_travellers']


def test_an_unreadable_board_number_cannot_be_joined() -> None:
  unreadable = Board(number=BoardNumber(raw='?'), outcome=Outcome(raw=''))

  session = reconcile_session(
    _make_session([unreadable]),
    [_make_traveller(boards=[_our_board()])],
    our_name=OUR_NAME,
  )

  assert _codes(session.boards[0].issues) == ['board_not_in_travellers']
  assert session.boards[0].deal is None


def test_the_lead_is_checked_against_the_traveller_supplied_deal() -> None:
  # North declares, so East is on lead — but the card led is North's own.
  session = reconcile_session(
    _make_session(
      [
        _sheet_board(
          resolution=_played(declarer=Direction.NORTH), lead=_NORTH_CARD
        )
      ]
    ),
    [
      _make_traveller(
        boards=[
          _our_board(resolution=_played(declarer=Direction.NORTH), deal=_DEAL)
        ]
      )
    ],
    our_name=OUR_NAME,
  )

  assert 'lead_not_in_leader_hand' in _codes(session.boards[0].issues)


# --- swap detection ---


def test_two_rows_filled_in_the_wrong_order_are_suggested_as_a_swap() -> None:
  # The sheet's row 1 holds board 2's play and vice versa.
  session = reconcile_session(
    _make_session(
      [
        _sheet_board(1, resolution=_played(level=3)),
        _sheet_board(2, resolution=_played(level=4)),
      ]
    ),
    [
      _make_traveller(
        boards=[
          _our_board(1, resolution=_played(level=4)),
          _our_board(2, resolution=_played(level=3)),
        ]
      )
    ],
    our_name=OUR_NAME,
  )

  assert 'likely_row_swap' in _codes(session.boards[0].issues)
  assert 'likely_row_swap' in _codes(session.boards[1].issues)


def test_rows_in_the_right_order_are_not_suggested_as_a_swap() -> None:
  session = reconcile_session(
    _make_session(
      [
        _sheet_board(1, resolution=_played(level=3)),
        _sheet_board(2, resolution=_played(level=4)),
      ]
    ),
    [
      _make_traveller(
        boards=[
          _our_board(1, resolution=_played(level=3)),
          _our_board(2, resolution=_played(level=4)),
        ]
      )
    ],
    our_name=OUR_NAME,
  )

  assert 'likely_row_swap' not in _codes(session.boards[0].issues)


def test_a_declarer_the_traveller_has_wrong_does_not_shift_a_row() -> None:
  # The declarer is the field travellers most often get wrong, so it is left out
  # of the swap signal: counting it would dock the correctly-placed pairing and
  # could hand the suggestion to a coincidentally-matching neighbour.
  session = reconcile_session(
    _make_session(
      [
        _sheet_board(1, resolution=_played(declarer=Direction.SOUTH)),
        _sheet_board(2, resolution=_played(level=3)),
      ]
    ),
    [
      _make_traveller(
        boards=[
          _our_board(1, resolution=_played(declarer=Direction.NORTH)),
          _our_board(2, resolution=_played(level=3)),
        ]
      )
    ],
    our_name=OUR_NAME,
  )

  # The declarer mismatch is still reported — it is just not read as a swap.
  assert 'sheet_declarer_disagreement' in _codes(session.boards[0].issues)
  assert 'likely_row_swap' not in _codes(session.boards[0].issues)


def test_two_boards_played_identically_produce_no_suggestion() -> None:
  # Nothing in either record distinguishes them, so suggesting a swap would be
  # guessing rather than reporting.
  session = reconcile_session(
    _make_session([_sheet_board(1), _sheet_board(2)]),
    [_make_traveller(boards=[_our_board(1), _our_board(2)])],
    our_name=OUR_NAME,
  )

  assert 'likely_row_swap' not in _codes(session.boards[0].issues)
  assert 'likely_row_swap' not in _codes(session.boards[1].issues)


# --- graceful degradation ---


def test_a_session_with_no_travellers_passes_through_unenriched() -> None:
  sheet = _make_session([_sheet_board(1), _sheet_board(2)])

  session = reconcile_session(sheet, [], our_name=OUR_NAME)

  assert session == sheet


def test_withdrawing_the_last_traveller_takes_its_enrichment_with_it() -> None:
  # A capture found to be the wrong session's is dropped and the join re-run.
  # What it supplied has to go with it, or the record keeps asserting a deal and
  # an opponent nothing now supports.
  sheet = _make_session([_sheet_board()])
  enriched = reconcile_session(
    sheet,
    [_make_traveller(boards=[_our_board(deal=_DEAL)])],
    our_name=OUR_NAME,
  )
  assert enriched.boards[0].deal == _DEAL

  withdrawn = reconcile_session(enriched, [], our_name=OUR_NAME)

  assert withdrawn == sheet


def test_a_traveller_covering_none_of_our_boards_leaves_the_sheet() -> None:
  session = reconcile_session(
    _make_session([_sheet_board(number=1)]),
    [_make_traveller(boards=[_our_board(number=9)])],
    our_name=OUR_NAME,
  )

  # The board keeps its own content and simply gains a note that it went
  # unenriched; nothing about the sheet is dropped.
  assert session.boards[0].outcome is not None
  assert session.boards[0].deal is None
  assert _codes(session.boards[0].issues) == ['board_not_in_travellers']


# --- re-running the join ---


def test_a_second_run_rewrites_its_findings_rather_than_repeating_them() -> (
  None
):
  # A later traveller is taken in by running the whole join again, over the
  # session the last run produced.
  sheet = _make_session([_sheet_board(number=7)])
  travellers = [_make_traveller(boards=[_our_board(number=1)])]

  once = reconcile_session(sheet, travellers, our_name=OUR_NAME)
  twice = reconcile_session(once, travellers, our_name=OUR_NAME)

  assert twice == once


def test_a_second_run_keeps_what_earlier_stages_found() -> None:
  parsed = _make_session([_sheet_board(number=1)])
  earlier = Issue(
    code='unreadable_cell', severity=IssueSeverity.LOW, message='a smudge'
  )
  parsed = parsed.model_copy(
    update={
      'boards': (parsed.boards[0].model_copy(update={'issues': (earlier,)}),)
    }
  )
  travellers = [_make_traveller(boards=[_our_board(number=1)])]

  session = reconcile_session(parsed, travellers, our_name=OUR_NAME)
  again = reconcile_session(session, travellers, our_name=OUR_NAME)

  assert again.boards[0].issues == (earlier,)
