# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for translating what is written down into canonical values."""

import pytest

from session_analysis.enums import (
  Direction,
  IssueSeverity,
  Penalty,
  Rank,
  Side,
  Strain,
  Suit,
)
from session_analysis.models import Card
from session_analysis.notation import (
  NotationError,
  ResultNotation,
  board_schedule_issues,
  deal_from_hands,
  hand_from_holdings,
  par_contracts,
  tricks_taken,
  tricks_taken_from_par_result,
)
from session_analysis.travellers import DoubleDummyTricks

# A complete double-dummy table, for the par results recovered from one.
COMPLETE_TABLE: DoubleDummyTricks = {
  seat: dict.fromkeys(Strain, 9) for seat in Direction
}


def sheet(result: str, contract_level: int) -> int:
  """Read a result the sheet's way, spelled to keep the cases below readable."""
  return tricks_taken(
    result, contract_level=contract_level, written_as=ResultNotation.SHEET
  )


def traveller(result: str, contract_level: int) -> int:
  """Read a result a traveller's way."""
  return tricks_taken(
    result, contract_level=contract_level, written_as=ResultNotation.TRAVELLER
  )


# --- results: the sheet's notation ---


def test_making_exactly() -> None:
  # '4S +4' is ten tricks: a 4-level contract making with no overtricks.
  assert sheet('+4', 4) == 10


def test_making_with_overtricks() -> None:
  # '4S +6' is twelve tricks: four for the contract plus two overtricks.
  assert sheet('+6', 4) == 12


def test_making_every_trick() -> None:
  # '3N +7' is all thirteen tricks, the most possible.
  assert sheet('+7', 3) == 13


def test_overtricks_are_counted_from_book_not_the_contract() -> None:
  # '+N' is an absolute count from book, so the level does not change it: '+6'
  # is twelve tricks whether the contract was 4S (making two) or 6C (making
  # exactly).
  assert sheet('+6', 4) == 12
  assert sheet('+6', 6) == 12


# --- set contracts ---


def test_down_one() -> None:
  # '5H -1' is ten tricks: one short of the eleven the contract needed.
  assert sheet('-1', 5) == 10


def test_down_several() -> None:
  # '1N -2' is five tricks: two short of the seven the contract needed.
  assert sheet('-2', 1) == 5


def test_down_every_trick() -> None:
  # A 7-level contract '-13' is zero tricks: the whole contract lost.
  assert sheet('-13', 7) == 0


# --- transcription tolerance ---


@pytest.mark.parametrize(
  'dash',
  [
    chr(0x2D),  # hyphen-minus (ASCII)
    chr(0x2212),  # minus sign
    chr(0x2013),  # en dash
    chr(0x2014),  # em dash
    chr(0x2015),  # horizontal bar
  ],
)
def test_accepts_any_dash_glyph_as_a_minus(dash: str) -> None:
  # The sheet's minus may be any of several dash glyphs, all read alike.
  assert sheet(f'{dash}2', 1) == 5


def test_ignores_surrounding_whitespace() -> None:
  assert sheet(' +6 ', 4) == 12


# --- responsibility split ---


def test_translates_without_validating_semantics() -> None:
  # '+5' on a 6-level contract is a notational error — eleven tricks is really
  # down one, not a make — but the translator still computes it. Judging that
  # the notation is inconsistent is the validation pass's job, not this one's.
  assert sheet('+5', 6) == 11


@pytest.mark.parametrize('token', ['', '+', '5', 'x', '++6', '+-6'])
def test_malformed_token_raises(token: str) -> None:
  with pytest.raises(ValueError, match='malformed'):
    sheet(token, 4)


# --- the travellers' notation ---


def test_traveller_result_making_exactly() -> None:
  # '=' is the contract brought home with nothing to spare: ten tricks for a
  # 4-level contract.
  assert traveller('=', 4) == 10


def test_traveller_result_with_overtricks() -> None:
  # '+2' is two tricks beyond what the contract needed, so twelve.
  assert traveller('+2', 4) == 12


def test_traveller_result_going_down() -> None:
  # '-4' is four short of the ten the contract needed, so six.
  assert traveller('-4', 4) == 6


def test_the_sheet_writes_no_made_exactly_token() -> None:
  # '=' belongs to the travellers alone: a sheet counts its makes from book and
  # has no token for making with nothing to spare.
  with pytest.raises(ValueError, match='malformed'):
    sheet('=', 4)


def test_traveller_result_accepts_a_unicode_minus() -> None:
  # The club's HTML writes its minus as a Unicode minus sign rather than an
  # ASCII hyphen. Named by code point, as `glyphs` names the set it belongs to —
  # the two are indistinguishable on the page.
  minus_sign = chr(0x2212)
  assert traveller(f'{minus_sign}2', 4) == 8


@pytest.mark.parametrize('token', ['', '+', '5', 'x', '==', '+-1'])
def test_malformed_traveller_token_raises(token: str) -> None:
  with pytest.raises(ValueError, match='malformed'):
    traveller(token, 4)


# --- reading a hand ---


def test_spaced_and_unspaced_holdings_read_alike() -> None:
  spaced = hand_from_holdings(['A K Q', 'A K 3', 'A K 4', 'A K Q 2'])
  unspaced = hand_from_holdings(['AKQ', 'AK3', 'AK4', 'AKQ2'])
  assert spaced == unspaced


def test_a_ten_written_in_full() -> None:
  # The ACBL surfaces and the club's HTML print a ten as two characters; the
  # canonical rank is one.
  hand = hand_from_holdings(['A 10 9', '', '', ''])
  assert hand.cards[1] == Card(rank=Rank.TEN, suit=Suit.SPADES)


def test_a_ten_written_as_one_character() -> None:
  # The PBN writes the same card as `T`.
  assert hand_from_holdings(['AT9', '', '', '']) == hand_from_holdings(
    ['A 10 9', '', '', '']
  )


@pytest.mark.parametrize('void', ['', '-', '—', '-----', '  '])
def test_every_spelling_of_a_void(void: str) -> None:
  # Sources mark an empty suit with nothing, one dash, an em dash, or — in
  # ACBL's data — a run of them.
  hand = hand_from_holdings([void, 'A K Q', '', ''])
  assert [card.suit for card in hand.cards] == [Suit.HEARTS] * 3


def test_each_holding_takes_its_suit_from_its_position() -> None:
  # The argument order *is* the suit order — nothing in a holding says which
  # suit it is, so a caller reordering them would silently mislabel every card.
  hand = hand_from_holdings(['A', 'K', 'Q', 'J'])
  assert [(card.rank, card.suit) for card in hand.cards] == [
    (Rank.ACE, Suit.SPADES),
    (Rank.KING, Suit.HEARTS),
    (Rank.QUEEN, Suit.DIAMONDS),
    (Rank.JACK, Suit.CLUBS),
  ]


def test_an_unreadable_rank_names_the_suit_it_was_in() -> None:
  with pytest.raises(NotationError, match='hearts'):
    hand_from_holdings(['AKQ', 'AKX', '', ''])


def test_the_wrong_number_of_holdings_is_refused() -> None:
  with pytest.raises(NotationError, match='4 suit holdings'):
    hand_from_holdings(['AKQ', 'AKJ', 'AK'])


# --- assembling a deal ---


def test_a_deal_needs_every_seat() -> None:
  hand = hand_from_holdings(['A', '', '', ''])
  with pytest.raises(NotationError, match='W'):
    deal_from_hands(
      dict.fromkeys((Direction.NORTH, Direction.EAST, Direction.SOUTH), hand)
    )


def test_a_malformed_deal_is_still_assembled() -> None:
  # Well-formedness is reconciliation's check, so a deal that repeats a card
  # parses rather than being refused here — nothing is thrown away.
  hand = hand_from_holdings(['A', '', '', ''])
  deal = deal_from_hands(dict.fromkeys(Direction, hand))
  assert len(deal.hands) == 4


# --- par contracts ---


def test_a_seat_level_par_yields_one_contract() -> None:
  contracts = par_contracts(
    level=4,
    strain=Strain.SPADES,
    penalty=Penalty.NONE,
    declarer=Direction.NORTH,
    stated_tricks=10,
    double_dummy_tricks=None,
  )
  assert [contract.contract.declarer for contract in contracts] == [
    Direction.NORTH
  ]


def test_a_side_level_par_expands_to_both_seats() -> None:
  # Both seats of the side reach the score, so the side expands rather than
  # leaving every reader to handle a declarer that is not a seat.
  contracts = par_contracts(
    level=4,
    strain=Strain.SPADES,
    penalty=Penalty.NONE,
    declarer=Side.EAST_WEST,
    stated_tricks=10,
    double_dummy_tricks=None,
  )
  assert [contract.contract.declarer for contract in contracts] == [
    Direction.EAST,
    Direction.WEST,
  ]


def test_an_omitted_result_comes_from_the_double_dummy_table() -> None:
  # ACBL writes no result at all when par makes exactly, so the trick count is
  # declarer's makeable tricks in the strain.
  contracts = par_contracts(
    level=3,
    strain=Strain.NOTRUMP,
    penalty=Penalty.NONE,
    declarer=Direction.SOUTH,
    stated_tricks=None,
    double_dummy_tricks=COMPLETE_TABLE,
  )
  assert contracts[0].result.tricks_taken == 9


def test_an_omitted_result_with_no_table_to_recover_it_from() -> None:
  with pytest.raises(NotationError, match='states no result'):
    par_contracts(
      level=3,
      strain=Strain.NOTRUMP,
      penalty=Penalty.NONE,
      declarer=Direction.SOUTH,
      stated_tricks=None,
      double_dummy_tricks=None,
    )


# --- par result tokens ---


def test_par_result_tokens() -> None:
  assert tricks_taken_from_par_result('=', 4) == 10
  assert tricks_taken_from_par_result('+1', 4) == 11
  assert tricks_taken_from_par_result('-5', 6) == 7


def test_an_absent_par_result_is_not_a_failure() -> None:
  # A source that states no result reports None, for recovery to fill in.
  assert tricks_taken_from_par_result('', 4) is None


def test_an_unreadable_par_result() -> None:
  with pytest.raises(NotationError, match='rubbish'):
    tricks_taken_from_par_result('rubbish', 4)


# --- the schedule cross-check ---


def test_a_dealer_matching_the_schedule_reports_nothing() -> None:
  assert not board_schedule_issues(
    board_number=1, dealer=Direction.NORTH, vulnerability='None'
  )


def test_a_dealer_contradicting_the_schedule_is_reported() -> None:
  # A contradiction most likely means the board number was read off the wrong
  # part of the capture, which nothing else would catch — so it ranks high.
  issues = board_schedule_issues(
    board_number=1, dealer=Direction.EAST, vulnerability='None'
  )
  assert [issue.code for issue in issues] == ['dealer_contradicts_board_number']
  assert issues[0].severity == IssueSeverity.HIGH
  assert 'E' in issues[0].message


@pytest.mark.parametrize(
  ('board_number', 'printed'),
  [(1, 'None'), (2, 'N-S'), (3, 'E-W'), (4, 'Both'), (4, 'All')],
)
def test_every_spelling_of_a_vulnerability(
  board_number: int, printed: str
) -> None:
  # Each source spells the same value its own way, so the comparison drops the
  # punctuation and the case rather than branching per source.
  assert not board_schedule_issues(
    board_number=board_number, dealer=None, vulnerability=printed
  )


def test_a_vulnerability_contradicting_the_schedule_is_reported() -> None:
  issues = board_schedule_issues(
    board_number=1, dealer=None, vulnerability='Both'
  )
  assert [issue.code for issue in issues] == [
    'vulnerability_contradicts_board_number'
  ]


def test_both_contradictions_are_reported_together() -> None:
  # Neither check short-circuits the other: a board read from the wrong place
  # usually gets both wrong, and seeing both is the stronger signal.
  issues = board_schedule_issues(
    board_number=1, dealer=Direction.EAST, vulnerability='Both'
  )
  assert len(issues) == 2
