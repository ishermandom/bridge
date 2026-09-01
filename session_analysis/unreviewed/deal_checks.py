# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Integrity checks that become possible once a traveller supplies the deal.

A sheet records no deal at all, so nothing here can run before reconciliation.
Once the deal arrives, two things become checkable that the sheet alone could
never settle: whether the deal is well formed, and whether the opening lead the
sheet records could have come from the hand that was on lead.

The lead check is the more interesting of the two, because it is the only one
that reads both records at once. The lead is sheet-only and the deal is
traveller-only, so a violation implicates the lead, the declarer, or the board
numbering, and none of the three is presumed at fault — the check reports the
contradiction and leaves the judgment to a person. travellers.md
`#reconciliation` also counts it as a swap signal that owes nothing to the
traveller's own result rows, which is what makes it worth having alongside them.

Both checks report rather than raise, in the same discipline the capture parsers
hold to: a malformed deal is a thing to surface on the board, not a reason to
lose the board.
"""

import collections
from collections.abc import Iterable, Sequence

from session_analysis import issue_reporting
from session_analysis.enums import Direction, IssueSeverity
from session_analysis.models import Card, Deal, Issue

# A deal states four hands of thirteen distinct cards. A source that prints
# otherwise has been misread, or prints a deal that was never dealt; either way
# the board's analysis rests on it, so the finding ranks high.
_MALFORMED_DEAL = issue_reporting.Failure(
  'malformed_deal', IssueSeverity.HIGH, 'deal'
)

# The sheet and the traveller contradict each other outright here, so this ranks
# alongside a malformed deal rather than below it.
_LEAD_NOT_ON_LEAD = issue_reporting.Failure(
  'lead_not_in_leader_hand', IssueSeverity.HIGH, 'opening_lead'
)

# Every code this module attaches, for a caller that rewrites its findings
# rather than adding to them — reconciliation re-runs over a session it already
# checked, and a second run should not leave a second copy of each finding.
CODES = frozenset({_MALFORMED_DEAL.code, _LEAD_NOT_ON_LEAD.code})

_HAND_SIZE = 13


def _spell(card: Card) -> str:
  """A card as rank-then-suit (`AS`), for an issue message."""
  return f'{card.rank}{card.suit}'


def _spell_all(cards: Iterable[Card]) -> str:
  """A run of cards, sorted so one message reads the same on every run."""
  return ', '.join(sorted(_spell(card) for card in cards))


def find_deal_issues(deal: Deal) -> Sequence[Issue]:
  """Return what is malformed about a deal, empty when it is well formed.

  Checks the three ways a deal can fail to be one: a seat with no hand, a hand
  that does not hold thirteen cards, and a card dealt more than once. The
  three are reported together rather than short-circuiting, because they
  diagnose different mistakes and a caller reading one wants the others too.

  A deal missing a seat entirely still has its remaining hands checked — the
  point is to say everything wrong with the deal in one pass.
  """
  issues: list[Issue] = []

  absent_seats = tuple(seat for seat in Direction if seat not in deal.hands)
  if absent_seats:
    named = ', '.join(seat.name.lower() for seat in absent_seats)
    issues.append(_MALFORMED_DEAL.issue(f'deal states no hand for {named}'))

  for seat, hand in deal.hands.items():
    if len(hand.cards) != _HAND_SIZE:
      issues.append(
        _MALFORMED_DEAL.issue(
          f'{seat.name.lower()} holds {len(hand.cards)} cards, not '
          f'{_HAND_SIZE}: {_spell_all(hand.cards)}'
        )
      )

  # Counted across the whole deal rather than per hand, so that a card in two
  # hands and a card twice in one are both caught. The size check above sees
  # neither: a hand can repeat a card and still hold thirteen of them.
  dealt = collections.Counter(
    card for hand in deal.hands.values() for card in hand.cards
  )
  repeated = tuple(card for card, count in dealt.items() if count > 1)
  if repeated:
    issues.append(
      _MALFORMED_DEAL.issue(f'dealt more than once: {_spell_all(repeated)}')
    )

  return tuple(issues)


def find_lead_issues(
  deal: Deal, *, declarer: Direction, opening_lead: Card
) -> Sequence[Issue]:
  """Return an issue when the opening lead is not in the leader's hand.

  The opening lead comes from declarer's left-hand opponent, so the card the
  sheet records must be one that seat held. When it is not, the two records
  contradict each other and the message names both halves — which seat was on
  lead and what it actually held — so a reviewer can see at a glance whether the
  lead, the declarer, or the board number is the thing that is wrong.

  A deal that states no hand for the leading seat yields no issue: that gap is
  `find_deal_issues`'s to report, and repeating it here would flag one mistake
  twice.
  """
  leader = declarer.left_hand_opponent
  hand = deal.hands.get(leader)
  if not hand:
    return ()

  if opening_lead in hand.cards:
    return ()

  return (
    _LEAD_NOT_ON_LEAD.issue(
      f'{_spell(opening_lead)} was led against {declarer.name.lower()}, but '
      f'{leader.name.lower()} was on lead holding {_spell_all(hand.cards)}'
    ),
  )
