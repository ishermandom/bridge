# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Links that open a board in Bridge Solver Online, set up as the table had it.

A transcript's `DD` and `PLAY` columns say how a result compared with best play,
but not what best play was. Bridge Solver Online shows that: given a deal, it
works out what best play yields and lets the reader play the hand out card by
card. Its author's site, mirgo2.co.uk/bridgesolver, documents the parameters a
link to it may carry, so each board's link carries its whole deal and the reader
enters nothing.

Where the record states them, a link also names the table's contract and opening
lead, so that the solver opens on the position the lead left — the one `PLAY`
measures — rather than on the bare deal.

Everything a link carries is already on the board: the deal arrives from its
traveller at reconciliation, and the dealer and vulnerability come with the
board number's schedule.
"""

import urllib.parse
from collections.abc import Mapping

from session_analysis import notation
from session_analysis.enums import Direction, Penalty, Vulnerability
from session_analysis.models import Board, Deal, PlayedContract
from session_analysis.unreviewed import deal_checks

# The solver's page, at the address its documentation links.
_SOLVER_PAGE = 'https://dds.bridgewebs.com/bsol_standalone/ddummy.htm'

# The parameter carrying each seat's hand.
_HAND_PARAMETERS: Mapping[Direction, str] = {
  Direction.NORTH: 'north',
  Direction.EAST: 'east',
  Direction.SOUTH: 'south',
  Direction.WEST: 'west',
}

# A vulnerability as the solver spells one.
_VULNERABILITY_SPELLINGS: Mapping[Vulnerability, str] = {
  Vulnerability.NONE: 'None',
  Vulnerability.NORTH_SOUTH: 'NS',
  Vulnerability.EAST_WEST: 'EW',
  Vulnerability.BOTH: 'All',
}

# The mark a contract trails for its doubling, as the solver reads one.
_PENALTY_MARKS: Mapping[Penalty, str] = {
  Penalty.NONE: '',
  Penalty.DOUBLED: 'x',
  Penalty.REDOUBLED: 'xx',
}


def solver_link(board: Board) -> str | None:
  """A link opening `board` in the solver, or None without a deal to open.

  A board has none when no traveller reached it, and none the solver could use
  when its number went unread, since the number is what fixes the dealer and
  vulnerability. Nor is a deal `deal_checks` finds malformed linked: the solver
  would open hands that no table could have held.
  """
  schedule = board.number.schedule
  deal = board.deal
  if not deal or not schedule or deal_checks.find_deal_issues(deal):
    return None

  parameters = {
    'board': str(schedule.number),
    'dealer': schedule.dealer.value,
    'vul': _VULNERABILITY_SPELLINGS[schedule.vulnerability],
  }
  for seat, name in _HAND_PARAMETERS.items():
    parameters[name] = notation.written_hand(deal.hands[seat])
  parameters.update(_play_parameters(board, deal))
  return f'{_SOLVER_PAGE}?{urllib.parse.urlencode(parameters)}'


def _play_parameters(board: Board, deal: Deal) -> Mapping[str, str]:
  """The table's contract and opening lead, as far as the record states them.

  A board passed out, and one whose contract cell did not parse, name no
  contract and so add nothing. A lead goes in only beside the contract it was
  made against, and only where `deal_checks` finds it in the leader's hand —
  anywhere else, the sheet's lead, declarer or board number is wrong, and the
  solver would be asked to play a card the leader never held.
  """
  resolution = board.outcome.resolution if board.outcome else None
  if not isinstance(resolution, PlayedContract):
    return {}

  contract = resolution.contract
  penalty = _PENALTY_MARKS[contract.penalty]
  parameters = {
    'contract': f'{contract.level}{contract.strain.value}{penalty}',
    'declarer': contract.declarer.value,
  }
  lead = board.opening_lead.card if board.opening_lead else None
  if lead and not deal_checks.find_lead_issues(
    deal, declarer=contract.declarer, opening_lead=lead
  ):
    # Rank first, the order the solver reads a lead in.
    parameters['leadcard'] = f'{lead.rank.value}{lead.suit.value}'
  return parameters
