# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for linking a board to Bridge Solver Online.

Most tests read a link back into its parameters and assert on the ones they
concern, since the order a link happens to list its parameters in is nothing the
solver reads.
"""

import urllib.parse
from collections.abc import Mapping

import pytest

from session_analysis.enums import (
  Direction,
  Penalty,
  Rank,
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
  Hand,
  Lead,
  Outcome,
  Passout,
  PlayedContract,
  Result,
  Schedule,
)
from session_analysis.testing.deals import a_deal_the_lead_decides
from session_analysis.unreviewed.solver_links import solver_link


def _make_number(
  number: int = 5,
  *,
  dealer: Direction = Direction.NORTH,
  vulnerability: Vulnerability = Vulnerability.NONE,
) -> BoardNumber:
  """A board-number cell that parsed, fixing the dealer and vulnerability."""
  return BoardNumber(
    raw=str(number),
    schedule=Schedule(
      number=number, dealer=dealer, vulnerability=vulnerability
    ),
  )


def _make_outcome(
  level: int,
  strain: Strain,
  declarer: Direction,
  penalty: Penalty = Penalty.NONE,
) -> Outcome:
  """A contract cell that parsed. The result is no part of the link."""
  return Outcome(
    raw=f'{level}{strain}{declarer}',
    resolution=PlayedContract(
      contract=Contract(
        level=level, strain=strain, declarer=declarer, penalty=penalty
      ),
      result=Result(tricks_taken=9),
    ),
  )


def _make_lead(rank: Rank, suit: Suit) -> Lead:
  """An opening-lead cell that parsed into a card."""
  return Lead(raw=f'{rank}{suit}', card=Card(rank=rank, suit=suit))


def _make_board(
  *,
  number: BoardNumber | None = None,
  deal: Deal | None = None,
  outcome: Outcome | None = None,
  opening_lead: Lead | None = None,
) -> Board:
  """A board carrying the cells a link is built from."""
  return Board(
    number=number or _make_number(),
    deal=deal,
    outcome=outcome,
    opening_lead=opening_lead,
  )


def _parameters_of(link: str | None) -> Mapping[str, str]:
  """The parameters a link carries, each by its name."""
  assert link
  return dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(link).query))


# --- the deal ---


def test_a_link_opens_the_solver_s_page() -> None:
  link = solver_link(_make_board(deal=a_deal_the_lead_decides()))

  assert link
  assert link.startswith(
    'https://dds.bridgewebs.com/bsol_standalone/ddummy.htm?'
  )


def test_a_link_carries_every_hand() -> None:
  parameters = _parameters_of(
    solver_link(_make_board(deal=a_deal_the_lead_decides()))
  )

  # North holds no heart, which the solver reads as nothing between two dots.
  assert parameters['north'] == 'AKQJ..AKQJ.AKQJT'
  assert parameters['east'] == '76.8765432.76.43'
  assert parameters['south'] == 'T98.T9.T98.98765'
  assert parameters['west'] == '5432.AKQJ.5432.2'


def test_a_link_carries_the_board_number_dealer_and_vulnerability() -> None:
  board = _make_board(
    number=_make_number(
      7, dealer=Direction.SOUTH, vulnerability=Vulnerability.BOTH
    ),
    deal=a_deal_the_lead_decides(),
  )

  parameters = _parameters_of(solver_link(board))

  assert parameters['board'] == '7'
  assert parameters['dealer'] == 'S'
  # The solver spells both sides vulnerable as `All`.
  assert parameters['vul'] == 'All'


@pytest.mark.parametrize(
  ('vulnerability', 'spelling'),
  [
    (Vulnerability.NONE, 'None'),
    (Vulnerability.NORTH_SOUTH, 'NS'),
    (Vulnerability.EAST_WEST, 'EW'),
  ],
)
def test_each_vulnerability_is_spelled_as_the_solver_reads_it(
  vulnerability: Vulnerability, spelling: str
) -> None:
  board = _make_board(
    number=_make_number(vulnerability=vulnerability),
    deal=a_deal_the_lead_decides(),
  )

  assert _parameters_of(solver_link(board))['vul'] == spelling


# --- the table's contract and lead ---


def test_a_link_carries_the_contract_its_declarer_and_the_lead() -> None:
  # West, on lead against South, holds the two of spades.
  board = _make_board(
    deal=a_deal_the_lead_decides(),
    outcome=_make_outcome(3, Strain.NOTRUMP, Direction.SOUTH),
    opening_lead=_make_lead(Rank.TWO, Suit.SPADES),
  )

  parameters = _parameters_of(solver_link(board))

  assert parameters['contract'] == '3NT'
  assert parameters['declarer'] == 'S'
  assert parameters['leadcard'] == '2S'


@pytest.mark.parametrize(
  ('penalty', 'contract'),
  [(Penalty.DOUBLED, '4Sx'), (Penalty.REDOUBLED, '4Sxx')],
)
def test_a_doubled_contract_trails_the_solver_s_mark(
  penalty: Penalty, contract: str
) -> None:
  board = _make_board(
    deal=a_deal_the_lead_decides(),
    outcome=_make_outcome(4, Strain.SPADES, Direction.SOUTH, penalty),
  )

  assert _parameters_of(solver_link(board))['contract'] == contract


def test_a_lead_the_leader_never_held_is_left_out() -> None:
  # West is on lead against South, but North holds the ace of spades.
  board = _make_board(
    deal=a_deal_the_lead_decides(),
    outcome=_make_outcome(3, Strain.NOTRUMP, Direction.SOUTH),
    opening_lead=_make_lead(Rank.ACE, Suit.SPADES),
  )

  parameters = _parameters_of(solver_link(board))

  # The contract still sets the solver up; only the impossible card is dropped.
  assert parameters['contract'] == '3NT'
  assert 'leadcard' not in parameters


def test_a_lead_with_no_contract_to_lead_against_is_left_out() -> None:
  board = _make_board(
    deal=a_deal_the_lead_decides(),
    opening_lead=_make_lead(Rank.TWO, Suit.SPADES),
  )

  parameters = _parameters_of(solver_link(board))

  assert 'contract' not in parameters
  assert 'leadcard' not in parameters


def test_a_passed_out_board_opens_on_the_bare_deal() -> None:
  board = _make_board(
    deal=a_deal_the_lead_decides(),
    outcome=Outcome(raw='PASS', resolution=Passout()),
  )

  parameters = _parameters_of(solver_link(board))

  assert 'contract' not in parameters
  assert 'declarer' not in parameters


# --- boards with nothing to link ---


def test_a_board_no_traveller_reached_has_no_link() -> None:
  assert solver_link(_make_board(deal=None)) is None


def test_a_board_whose_number_went_unread_has_no_link() -> None:
  board = _make_board(
    number=BoardNumber(raw='1?'), deal=a_deal_the_lead_decides()
  )

  assert solver_link(board) is None


def test_a_malformed_deal_has_no_link() -> None:
  # Every seat dealt the same one card.
  hand = Hand(cards=(Card(rank=Rank.ACE, suit=Suit.SPADES),))
  board = _make_board(deal=Deal(hands=dict.fromkeys(Direction, hand)))

  assert solver_link(board) is None
