# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Deals whose double-dummy answers can be reasoned out rather than computed.

A double-dummy count is not something a test can assert by restating the search
— that would only check a solver against itself. What a test can do is use a
deal contrived so that its answers follow from a sentence or two, and assert
those. This module holds the two such deals the suites share, so that the
reasoning behind each is written down once.

`a_suit_to_each_seat` deals every seat one whole suit: North the spades, East
the hearts, South the diamonds, West the clubs. Two consequences carry every
test that uses it.

- **With spades as trumps, North takes all thirteen.** Whoever is on lead holds
  none, North alone can ruff, and once in, North runs the trumps nobody else
  holds a card of. Played from the other side — East declaring in spades — the
  same reasoning gives East none of them.
- **In notrump, the hand on lead takes all thirteen.** Nothing ruffs, so the
  leader simply cashes a suit no one else holds a card of, and declarer takes
  none.

That deal is nothing like a real one, which is the point twice over: a seat or a
strain wired up wrongly moves its answers a long way rather than a little, and
three suits of every hand are void, so voids are exercised throughout. What it
cannot show is a lead mattering — every lead against it comes to the same count
— so `a_deal_the_lead_decides` sits beside it for that, argued the same way.
"""

from session_analysis.enums import Direction, Rank, Suit
from session_analysis.models import Card, Deal, Hand


def _hand(spades: str, hearts: str, diamonds: str, clubs: str) -> Hand:
  """A hand written suit by suit, each spelled in ranks from the top down."""
  return Hand(
    cards=tuple(
      Card(rank=Rank(rank), suit=suit)
      for suit, ranks in (
        (Suit.SPADES, spades),
        (Suit.HEARTS, hearts),
        (Suit.DIAMONDS, diamonds),
        (Suit.CLUBS, clubs),
      )
      for rank in ranks
    )
  )


def whole_suit(suit: Suit) -> Hand:
  """Every card of one suit, which is a whole hand in `a_suit_to_each_seat`."""
  return Hand(cards=tuple(Card(rank=rank, suit=suit) for rank in Rank))


def a_suit_to_each_seat() -> Deal:
  """North holds the spades, East the hearts, South the diamonds, West the
  clubs."""
  return Deal(
    hands={
      Direction.NORTH: whole_suit(Suit.SPADES),
      Direction.EAST: whole_suit(Suit.HEARTS),
      Direction.SOUTH: whole_suit(Suit.DIAMONDS),
      Direction.WEST: whole_suit(Suit.CLUBS),
    }
  )


def a_deal_the_lead_decides() -> Deal:
  """A deal where the opening lead is worth four tricks and nothing else is.

  North holds thirteen winners and not one heart: the top four spades, the top
  four diamonds, and the top five clubs. West holds the ace to the jack of
  hearts, which are the defense's only winners anywhere. South declares
  notrump, putting West on lead, and everything turns on that one card.

  - **A heart lead holds South to nine.** West cashes four heart tricks while
    North, void, discards four of the winners it will never get back.
  - **Any other lead lets South take all thirteen.** North wins the trick and
    runs its winners, and since North never leads a heart the defense is never
    on lead again.

  So the published cell for South in notrump is nine — the least West's leads
  can hold declarer to — while a spade led leaves thirteen. That gap is what a
  test of the solved count needs, and it is there without any source having to
  misstate anything.
  """
  return Deal(
    hands={
      Direction.NORTH: _hand('AKQJ', '', 'AKQJ', 'AKQJT'),
      Direction.EAST: _hand('76', '8765432', '76', '43'),
      Direction.SOUTH: _hand('T98', 'T9', 'T98', '98765'),
      Direction.WEST: _hand('5432', 'AKQJ', '5432', '2'),
    }
  )
