# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for the non-raising validation pass.

The pass operates on a fully built `Board`, so these tests hand-construct boards
— legal ones asserting a clean result, and deliberately broken ones asserting
the exact issue — with no OCR or parser involved. Small builder helpers keep
each case down to the one field it exercises.

Passes are usually not written on the sheet, so the auctions here mostly omit
them; a `by_opponents` flag on each call (the sheet's circle convention) carries
the side information the legality checks need in their place.
"""

from collections.abc import Sequence

from session_analysis.enums import (
  CallKind,
  Direction,
  Penalty,
  Rank,
  Strain,
  Suit,
  Vulnerability,
)
from session_analysis.models import (
  AuctionEntry,
  Board,
  BoardNumber,
  Call,
  Card,
  Contract,
  Lead,
  Outcome,
  Passout,
  PlayedContract,
  Result,
  Schedule,
)
from session_analysis.validation import find_issues, validate_board

# --- builders ---


def _make_bid(
  level: int, strain: Strain, by_opponents: bool = False
) -> AuctionEntry:
  return AuctionEntry(
    raw=f'{level}{strain.value}',
    call=Call(kind=CallKind.BID, level=level, strain=strain),
    by_opponents=by_opponents,
  )


def _make_pass() -> AuctionEntry:
  return AuctionEntry(raw='p', call=Call(kind=CallKind.PASS))


def _make_double(by_opponents: bool = False) -> AuctionEntry:
  return AuctionEntry(
    raw='x', call=Call(kind=CallKind.DOUBLE), by_opponents=by_opponents
  )


def _make_redouble(by_opponents: bool = False) -> AuctionEntry:
  return AuctionEntry(
    raw='xx', call=Call(kind=CallKind.REDOUBLE), by_opponents=by_opponents
  )


def _make_unresolved_call() -> AuctionEntry:
  # A token the parser could not understand: no call, only the raw text.
  return AuctionEntry(raw='??')


def _make_lead() -> Lead:
  return Lead(raw='AoS', card=Card(rank=Rank.ACE, suit=Suit.SPADES))


def _make_played(
  level: int,
  strain: Strain,
  declarer: Direction,
  tricks: int,
  penalty: Penalty = Penalty.NONE,
) -> Outcome:
  return Outcome(
    raw=f'{level}{strain.value}{declarer.value}',
    resolution=PlayedContract(
      contract=Contract(
        level=level, strain=strain, declarer=declarer, penalty=penalty
      ),
      result=Result(tricks_taken=tricks),
    ),
  )


def _make_passout() -> Outcome:
  return Outcome(raw='all pass', resolution=Passout())


def _make_board(
  *,
  auction: Sequence[AuctionEntry] = (),
  outcome: Outcome | None = None,
  opening_lead: Lead | None = None,
) -> Board:
  # The board number and its schedule are irrelevant to validation now that the
  # declarer is not derived; a resolved one keeps the board realistic.
  return Board(
    number=BoardNumber(
      raw='1',
      schedule=Schedule(
        number=1, dealer=Direction.NORTH, vulnerability=Vulnerability.NONE
      ),
    ),
    auction=tuple(auction),
    outcome=outcome,
    opening_lead=opening_lead,
  )


def _codes(board: Board) -> set[str]:
  return {issue.code for issue in find_issues(board)}


# A legal, fully transcribed board reused as the clean baseline: 1NT opened and
# raised to 3NT (partner's bids, so neither is circled), a lead, and a matching
# contract cell. No passes are written, as on a real sheet.
def _make_legal_board() -> Board:
  return _make_board(
    auction=[_make_bid(1, Strain.NOTRUMP), _make_bid(3, Strain.NOTRUMP)],
    outcome=_make_played(3, Strain.NOTRUMP, Direction.NORTH, tricks=9),
    opening_lead=_make_lead(),
  )


# --- a legal board is clean ---


def test_legal_board_has_no_issues() -> None:
  assert find_issues(_make_legal_board()) == ()


def test_passed_out_board_is_clean() -> None:
  # A passout is a `Passout` outcome with no auction and no lead — never four
  # written passes, which the sheet would not record.
  assert find_issues(_make_board(outcome=_make_passout())) == ()


# --- content well-formedness ---


def test_unresolved_call_is_flagged() -> None:
  board = _make_board(
    auction=[_make_bid(1, Strain.CLUBS), _make_unresolved_call()]
  )
  assert _codes(board) == {'unresolved_call'}


def test_unresolved_lead_is_flagged() -> None:
  board = _make_board(opening_lead=Lead(raw='??'))
  assert _codes(board) == {'unresolved_lead'}


def test_unresolved_contract_is_flagged() -> None:
  board = _make_board(outcome=Outcome(raw='4?N', resolution=None))
  assert _codes(board) == {'unresolved_contract'}


def test_contract_level_out_of_range_is_flagged() -> None:
  board = _make_legal_board().model_copy(
    update={
      'outcome': _make_played(8, Strain.SPADES, Direction.NORTH, tricks=13)
    }
  )
  assert 'contract_level_out_of_range' in _codes(board)


def test_tricks_out_of_range_is_flagged() -> None:
  board = _make_legal_board().model_copy(
    update={
      'outcome': _make_played(4, Strain.SPADES, Direction.NORTH, tricks=14)
    }
  )
  assert 'tricks_out_of_range' in _codes(board)


# --- transcription completeness ---


def test_played_board_without_a_lead_is_flagged() -> None:
  board = _make_board(
    auction=[_make_bid(4, Strain.SPADES)],
    outcome=_make_played(4, Strain.SPADES, Direction.NORTH, tricks=10),
  )
  assert 'lead_missing' in _codes(board)


def test_played_board_without_an_auction_is_flagged() -> None:
  board = _make_board(
    outcome=_make_played(4, Strain.SPADES, Direction.NORTH, tricks=10),
    opening_lead=_make_lead(),
  )
  assert 'auction_missing' in _codes(board)


def test_unresolved_contract_does_not_prompt_for_lead_or_auction() -> None:
  # With the contract cell unresolved we can't tell a played board from a
  # passout, so the completeness prompts stay quiet.
  board = _make_board(outcome=Outcome(raw='4?N', resolution=None))
  assert _codes(board) == {'unresolved_contract'}


# --- auction legality: rank monotonicity ---


def test_descending_bid_rank_is_flagged() -> None:
  board = _make_board(
    auction=[_make_bid(2, Strain.SPADES), _make_bid(2, Strain.HEARTS)]
  )
  assert 'auction_rank_not_increasing' in _codes(board)


def test_repeated_bid_is_flagged() -> None:
  # Equal rank is illegal too: a bid must strictly outrank the one before it.
  board = _make_board(
    auction=[_make_bid(2, Strain.HEARTS), _make_bid(2, Strain.HEARTS)]
  )
  assert 'auction_rank_not_increasing' in _codes(board)


def test_ascending_bids_without_written_passes_are_clean() -> None:
  # Rank is judged over the recorded bids alone; the omitted passes between them
  # are irrelevant.
  board = _make_board(
    auction=[
      _make_bid(1, Strain.CLUBS),
      _make_bid(1, Strain.HEARTS),
      _make_bid(2, Strain.DIAMONDS),
    ]
  )
  assert find_issues(board) == ()


def test_intervening_written_pass_does_not_advance_rank() -> None:
  # A pass that does happen to be written must not be read as lowering the rank.
  board = _make_board(
    auction=[
      _make_bid(1, Strain.CLUBS),
      _make_pass(),
      _make_bid(2, Strain.CLUBS),
    ]
  )
  assert 'auction_rank_not_increasing' not in _codes(board)


# --- auction legality: double and redouble ---


def test_double_of_the_opponents_bid_is_clean() -> None:
  board = _make_board(
    auction=[_make_bid(1, Strain.HEARTS), _make_double(by_opponents=True)]
  )
  assert find_issues(board) == ()


def test_double_not_following_a_bid_is_flagged() -> None:
  board = _make_board(auction=[_make_double(by_opponents=True)])
  assert _codes(board) == {'double_without_bid'}


def test_double_of_own_side_is_flagged() -> None:
  # Both calls are ours (uncircled): you cannot double your partner's bid.
  board = _make_board(
    auction=[_make_bid(1, Strain.HEARTS), _make_double(by_opponents=False)]
  )
  assert _codes(board) == {'double_by_wrong_side'}


def test_double_skips_an_intervening_written_pass() -> None:
  board = _make_board(
    auction=[
      _make_bid(1, Strain.HEARTS),
      _make_pass(),
      _make_double(by_opponents=True),
    ]
  )
  assert find_issues(board) == ()


def test_redouble_of_a_double_is_clean() -> None:
  board = _make_board(
    auction=[
      _make_bid(1, Strain.HEARTS),
      _make_double(by_opponents=True),
      _make_redouble(by_opponents=False),
    ]
  )
  assert find_issues(board) == ()


def test_redouble_not_following_a_double_is_flagged() -> None:
  board = _make_board(
    auction=[_make_bid(1, Strain.HEARTS), _make_redouble(by_opponents=False)]
  )
  assert _codes(board) == {'redouble_without_double'}


def test_redouble_by_the_doubling_side_is_flagged() -> None:
  # The redouble must come from the doubled side, not the side that doubled.
  board = _make_board(
    auction=[
      _make_bid(1, Strain.HEARTS),
      _make_double(by_opponents=True),
      _make_redouble(by_opponents=True),
    ]
  )
  assert _codes(board) == {'redouble_by_wrong_side'}


# --- auction legality: contract cross-checks ---


def test_contract_disagreeing_with_last_bid_is_flagged() -> None:
  # The auction ends 3NT, but the contract cell reads 4S.
  board = _make_board(
    auction=[_make_bid(1, Strain.NOTRUMP), _make_bid(3, Strain.NOTRUMP)],
    outcome=_make_played(4, Strain.SPADES, Direction.NORTH, tricks=10),
    opening_lead=_make_lead(),
  )
  assert 'contract_not_last_bid' in _codes(board)


def test_last_bid_matches_contract_across_omitted_passes() -> None:
  # A contested auction with no written passes still lines up with the contract.
  board = _make_board(
    auction=[
      _make_bid(1, Strain.HEARTS),
      _make_bid(2, Strain.DIAMONDS, by_opponents=True),
      _make_bid(4, Strain.HEARTS),
    ],
    outcome=_make_played(4, Strain.HEARTS, Direction.NORTH, tricks=10),
    opening_lead=_make_lead(),
  )
  assert find_issues(board) == ()


def test_penalty_disagreeing_with_the_auction_is_flagged() -> None:
  # The auction ends in a double, but the contract cell records no penalty.
  board = _make_board(
    auction=[_make_bid(3, Strain.NOTRUMP), _make_double(by_opponents=True)],
    outcome=_make_played(3, Strain.NOTRUMP, Direction.NORTH, tricks=9),
    opening_lead=_make_lead(),
  )
  assert 'contract_penalty_mismatch' in _codes(board)


def test_doubled_contract_with_omitted_trailing_passes_is_clean() -> None:
  # The double is the last written token — its trailing passes are omitted — yet
  # the penalty still reads as doubled.
  board = _make_board(
    auction=[_make_bid(3, Strain.NOTRUMP), _make_double(by_opponents=True)],
    outcome=_make_played(
      3, Strain.NOTRUMP, Direction.NORTH, tricks=9, penalty=Penalty.DOUBLED
    ),
    opening_lead=_make_lead(),
  )
  assert find_issues(board) == ()


def test_passout_cell_with_bids_is_flagged() -> None:
  board = _make_board(
    auction=[_make_bid(1, Strain.CLUBS)], outcome=_make_passout()
  )
  assert 'passout_has_bids' in _codes(board)


def test_contract_cell_with_a_bidless_auction_is_flagged() -> None:
  # A written pass but no bid, against a contract cell that names a contract.
  board = _make_board(
    auction=[_make_pass()],
    outcome=_make_played(4, Strain.SPADES, Direction.NORTH, tricks=10),
    opening_lead=_make_lead(),
  )
  assert 'contract_without_bid' in _codes(board)


# --- a hole in the auction suppresses the legality checks ---


def test_unresolved_token_suppresses_auction_legality() -> None:
  # A descending pair of bids would fail monotonicity, but the hole between them
  # makes the sequence untrustworthy, so only the unresolved token is reported.
  board = _make_board(
    auction=[
      _make_bid(3, Strain.SPADES),
      _make_unresolved_call(),
      _make_bid(2, Strain.HEARTS),
    ]
  )
  assert _codes(board) == {'unresolved_call'}


# --- annotation onto the frozen model ---


def test_validate_board_annotates_a_copy_leaving_the_original_frozen() -> None:
  board = _make_board(outcome=Outcome(raw='4?N', resolution=None))
  validated = validate_board(board)
  # The original is untouched (frozen); the copy carries the found issue.
  assert board.issues == ()
  assert {issue.code for issue in validated.issues} == {'unresolved_contract'}
