# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for the integrity checks a traveller-supplied deal makes possible."""

from collections.abc import Sequence

import pytest

from session_analysis.enums import Direction, Rank, Suit
from session_analysis.models import Card, Deal, Hand, Issue
from session_analysis.unreviewed.deal_checks import (
  find_deal_issues,
  find_lead_issues,
)

# The four thirteen-card holdings a well-formed deal divides the pack into,
# written as rank letters per suit so a test can say what it changes.
_WELL_FORMED = {
  Direction.NORTH: {'S': 'AKQ', 'H': 'AKQ', 'D': 'AKQ', 'C': 'AKQJ'},
  Direction.EAST: {'S': 'JT9', 'H': 'JT9', 'D': 'JT9', 'C': 'T987'},
  Direction.SOUTH: {'S': '8765', 'H': '876', 'D': '876', 'C': '654'},
  Direction.WEST: {'S': '432', 'H': '5432', 'D': '5432', 'C': '32'},
}


def _hand(holdings: dict[str, str]) -> Hand:
  """A hand from one holding per suit, spelled as rank letters."""
  return Hand(
    cards=tuple(
      Card(rank=Rank(rank), suit=Suit(suit))
      for suit, ranks in holdings.items()
      for rank in ranks
    )
  )


def _make_deal(**replacements: dict[str, str]) -> Deal:
  """The well-formed deal, with named seats' holdings replaced.

  Seats are named by their `Direction` value (`N`, `E`, `S`, `W`); a seat mapped
  to an empty dict is dropped from the deal entirely.
  """
  holdings = dict(_WELL_FORMED)
  for seat, replacement in replacements.items():
    holdings[Direction(seat)] = replacement
  return Deal(
    hands={seat: _hand(cards) for seat, cards in holdings.items() if cards}
  )


def _codes(issues: Sequence[Issue]) -> list[str]:
  """The codes of a run of issues, for asserting on what was reported."""
  return [issue.code for issue in issues]


# --- deal well-formedness ---


def test_well_formed_deal_reports_nothing() -> None:
  assert find_deal_issues(_make_deal()) == ()


def test_hand_short_of_thirteen_cards_is_reported() -> None:
  # North drops the club jack, leaving twelve.
  issues = find_deal_issues(
    _make_deal(N={'S': 'AKQ', 'H': 'AKQ', 'D': 'AKQ', 'C': 'AKQ'})
  )

  assert _codes(issues) == ['malformed_deal']
  assert '12 cards' in issues[0].message
  assert 'north' in issues[0].message


def test_card_dealt_to_two_seats_is_reported() -> None:
  # West's spade four becomes the ace, which North also holds. Every hand still
  # holds thirteen, so the doubled card is the only fault in the deal.
  issues = find_deal_issues(
    _make_deal(W={'S': 'A32', 'H': '5432', 'D': '5432', 'C': '32'})
  )

  assert _codes(issues) == ['malformed_deal']
  assert 'AS' in issues[0].message


def test_absent_seat_is_reported() -> None:
  issues = find_deal_issues(_make_deal(E={}))

  assert _codes(issues) == ['malformed_deal']
  assert 'east' in issues[0].message


def test_every_fault_in_one_deal_is_reported_together() -> None:
  # East is gone and South is a card short: two independent faults.
  issues = find_deal_issues(
    _make_deal(E={}, S={'S': '8765', 'H': '876', 'D': '876', 'C': '65'})
  )

  assert len(issues) == 2


# --- the opening lead against the deal ---


def test_lead_from_the_hand_on_lead_reports_nothing() -> None:
  # North declares, so East is on lead; East holds the spade jack.
  issues = find_lead_issues(
    _make_deal(),
    declarer=Direction.NORTH,
    opening_lead=Card(rank=Rank.JACK, suit=Suit.SPADES),
  )

  assert issues == ()


def test_lead_from_the_wrong_hand_is_reported() -> None:
  # North declares, so East is on lead — but the spade ace is North's own.
  issues = find_lead_issues(
    _make_deal(),
    declarer=Direction.NORTH,
    opening_lead=Card(rank=Rank.ACE, suit=Suit.SPADES),
  )

  assert _codes(issues) == ['lead_not_in_leader_hand']
  assert 'AS' in issues[0].message
  # Names both halves of the contradiction, so a reviewer can see which to fix.
  assert 'east' in issues[0].message
  assert 'north' in issues[0].message


@pytest.mark.parametrize(
  ('declarer', 'leader_card'),
  [
    (Direction.NORTH, Card(rank=Rank.JACK, suit=Suit.SPADES)),
    (Direction.EAST, Card(rank=Rank.EIGHT, suit=Suit.SPADES)),
    (Direction.SOUTH, Card(rank=Rank.FOUR, suit=Suit.SPADES)),
    (Direction.WEST, Card(rank=Rank.ACE, suit=Suit.SPADES)),
  ],
)
def test_the_seat_on_lead_is_declarers_left_hand_opponent(
  declarer: Direction, leader_card: Card
) -> None:
  # Play moves clockwise, so each declarer is led to by the next seat round.
  assert (
    find_lead_issues(_make_deal(), declarer=declarer, opening_lead=leader_card)
    == ()
  )


def test_lead_is_not_checked_when_the_leading_seat_has_no_hand() -> None:
  # East is on lead against North and states no hand; the absent seat is
  # `find_deal_issues`'s to report, so this does not flag the same fault twice.
  issues = find_lead_issues(
    _make_deal(E={}),
    declarer=Direction.NORTH,
    opening_lead=Card(rank=Rank.ACE, suit=Suit.SPADES),
  )

  assert issues == ()
