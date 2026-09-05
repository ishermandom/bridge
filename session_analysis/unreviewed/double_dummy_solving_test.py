# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for solving a deal for the tricks an opening lead leaves behind.

A double-dummy count is not something a test can assert by restating the search
— that would only check the solver against itself. So every deal here is one
whose answer can be reasoned out in a sentence, and each test carries that
reasoning beside the number. What they are really testing is the adaptation: a
seat, a strain, a rank or a leader wired up wrongly moves these answers a long
way, because the deals are built so that everything turns on who holds what.

The deals these tests use, and the reasoning their answers rest on, are in
`testing.deals`.
"""

import pytest

from session_analysis.enums import Direction, Rank, Strain, Suit
from session_analysis.models import Card
from session_analysis.testing.deals import (
  a_deal_the_lead_decides,
  a_suit_to_each_seat,
)
from session_analysis.unreviewed.double_dummy_solving import tricks_after_lead


def test_the_hand_holding_every_trump_takes_every_trick() -> None:
  tricks = tricks_after_lead(
    a_suit_to_each_seat(),
    declarer=Direction.NORTH,
    strain=Strain.SPADES,
    opening_lead=Card(rank=Rank.TWO, suit=Suit.HEARTS),
  )

  # North declares in spades holding all thirteen of them. East, on lead, has
  # only hearts; North alone can ruff, wins the trick, and then runs the trumps
  # nobody else holds a card of.
  assert tricks == 13


def test_a_declarer_whose_side_holds_no_trump_takes_none() -> None:
  tricks = tricks_after_lead(
    a_suit_to_each_seat(),
    declarer=Direction.EAST,
    strain=Strain.SPADES,
    opening_lead=Card(rank=Rank.TWO, suit=Suit.DIAMONDS),
  )

  # The same deal played from the other side: East declares in spades while
  # North holds every one. South leads a diamond, North ruffs it away, and the
  # trumps run for the defenders instead.
  assert tricks == 0


def test_the_strain_changes_what_the_same_deal_yields() -> None:
  tricks = tricks_after_lead(
    a_suit_to_each_seat(),
    declarer=Direction.NORTH,
    strain=Strain.NOTRUMP,
    opening_lead=Card(rank=Rank.TWO, suit=Suit.HEARTS),
  )

  # North declaring the deal above took all thirteen with spades as trumps. In
  # notrump nothing ruffs, so East simply cashes the hearts nobody can beat.
  assert tricks == 0


def test_a_ten_is_led_by_the_letter_the_solver_reads() -> None:
  tricks = tricks_after_lead(
    a_suit_to_each_seat(),
    declarer=Direction.NORTH,
    strain=Strain.NOTRUMP,
    opening_lead=Card(rank=Rank.TEN, suit=Suit.HEARTS),
  )

  # The canonical ten is `T` on both sides of the adaptation, where the sheet
  # writes two characters. A ten spelled `10` would leave the solver reading a
  # hand of twelve cards and a stray one, so this would raise rather than
  # answer.
  assert tricks == 0


def test_the_card_led_changes_what_remains_of_the_deal() -> None:
  held = tricks_after_lead(
    a_deal_the_lead_decides(),
    declarer=Direction.SOUTH,
    strain=Strain.NOTRUMP,
    opening_lead=Card(rank=Rank.ACE, suit=Suit.HEARTS),
  )
  given = tricks_after_lead(
    a_deal_the_lead_decides(),
    declarer=Direction.SOUTH,
    strain=Strain.NOTRUMP,
    opening_lead=Card(rank=Rank.TWO, suit=Suit.SPADES),
  )

  # West's four hearts are the defense's only winners anywhere, and only a
  # heart lead cashes them, North being void and discarding. Any other lead
  # puts North in to run thirteen winners the defense never interrupts. Nothing
  # about the deal changes between the two calls but the card led.
  assert held == 9
  assert given == 13


def test_a_lead_the_leading_hand_does_not_hold_is_refused() -> None:
  # West holds the clubs, and it is East on lead against North. The solver is
  # given a precondition rather than a check, so an impossible position is an
  # error from it rather than a number that means nothing. `DDSError` is a
  # `RuntimeError`, and naming the base keeps the library's private module out
  # of this test.
  with pytest.raises(RuntimeError):
    tricks_after_lead(
      a_suit_to_each_seat(),
      declarer=Direction.NORTH,
      strain=Strain.NOTRUMP,
      opening_lead=Card(rank=Rank.TWO, suit=Suit.CLUBS),
    )
