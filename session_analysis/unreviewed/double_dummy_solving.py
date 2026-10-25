# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Solving a deal double-dummy: whole, and from one particular opening lead.

A double-dummy table states what best play by both sides yields, and best play
by the defense includes its choice of lead — so a table answers what the *best*
lead holds declarer to and nothing about any other. A source may publish that
table, but not always in full, so `solve_table` solves all twenty cells from the
deal. The lead actually made leaves a different position, and finding what that
position yields is a search no table can stand in for. `tricks_after_lead` runs
that search.

It is the project's only seam onto a double-dummy solver. Everything else states
the question in this project's own terms — a `Deal`, a `Direction`, a `Strain`,
a `Card` — and this module alone knows how the solver spells them. Keeping the
adaptation in one place is what makes the solver replaceable: `endplay` bundles
Bo Haglund's double-dummy solver and is the only Python package that ships it in
a usable form today, but it is a thin wrapper around a copy of that solver
frozen at an old release, so the day may come to swap the package out.

The count that comes back is declarer's, as a published table's cells are, so
the two compare directly and their difference is what the opening lead cost.
"""

import functools
from collections.abc import Mapping

import endplay.dds
import endplay.types

from session_analysis import notation
from session_analysis.enums import Direction, Strain
from session_analysis.models import (
  Card,
  Deal,
  SolvedDoubleDummyTricks,
)

_SOLVER_SEATS: Mapping[Direction, endplay.types.Player] = {
  Direction.NORTH: endplay.types.Player.north,
  Direction.EAST: endplay.types.Player.east,
  Direction.SOUTH: endplay.types.Player.south,
  Direction.WEST: endplay.types.Player.west,
}

_SOLVER_STRAINS: Mapping[Strain, endplay.types.Denom] = {
  Strain.CLUBS: endplay.types.Denom.clubs,
  Strain.DIAMONDS: endplay.types.Denom.diamonds,
  Strain.HEARTS: endplay.types.Denom.hearts,
  Strain.SPADES: endplay.types.Denom.spades,
  Strain.NOTRUMP: endplay.types.Denom.nt,
}

# The seats a written deal names in turn. The order is the notation's rather
# than ours, so it is spelled out here instead of taken from the enum's own
# declaration order.
_WRITTEN_SEATS = (
  Direction.NORTH,
  Direction.EAST,
  Direction.SOUTH,
  Direction.WEST,
)


def solve_table(deal: Deal) -> SolvedDoubleDummyTricks:
  """Every declarer's tricks in every strain, with best play by both sides.

  Args:
    deal: the four hands, which must be well formed — four seats, thirteen
      cards each, no card twice.

  Returns:
    All twenty cells, keyed by declarer and then by strain. Each assumes the
    defense's best opening lead, as a published table's cells do, so the two
    compare cell for cell.

  Raises:
    KeyError: if the deal states no hand for some seat.
    endplay._dds.DDSError: if the deal is malformed.

  `deal_checks.find_deal_issues` establishes the precondition and reports why it
  fails, which is why this raises rather than repeating the check.
  """
  return _solved_table(_written_deal(deal))


@functools.cache
def _solved_table(written_deal: str) -> SolvedDoubleDummyTricks:
  """The table `solve_table` returns, solved once per written deal.

  The same deal can reach the solver many times in one process — a session
  captured in two formats, or the tests parsing their few sample captures over
  and over — and each solve takes tens of milliseconds to give the same answer.

  Every caller shares the one table, read-only so that no caller can change what
  the others see. The return type, `SolvedDoubleDummyTricks`, is a nested
  read-only `Mapping`, so the type checker rejects any write to the table.
  """
  table = endplay.dds.calc_dd_table(endplay.types.Deal(written_deal))

  # The solver's table, like its play analysis, comes back untyped, so each
  # count is converted at this boundary rather than travelling on unchecked.
  return {
    seat: {
      strain: int(table[solver_strain, solver_seat])
      for strain, solver_strain in _SOLVER_STRAINS.items()
    }
    for seat, solver_seat in _SOLVER_SEATS.items()
  }


def tricks_after_lead(
  deal: Deal,
  *,
  declarer: Direction,
  strain: Strain,
  opening_lead: Card,
) -> int:
  """Declarer's tricks with best play by both sides after that opening lead.

  Args:
    deal: the four hands, which must be well formed — four seats, thirteen
      cards each, no card twice.
    declarer: the seat that played the contract. Who leads follows from it,
      being the seat to its left.
    strain: what the contract was played in.
    opening_lead: the card actually led, which must be in the leading hand.

  Returns:
    How many of the thirteen tricks declarer takes, counting from the position
    the lead leaves rather than from the start of the deal.

  Raises:
    KeyError: if the deal states no hand for some seat.
    endplay._dds.DDSError: if the deal is malformed or the lead is not in the
      leading hand.

  Both preconditions are established, and reported as issues, by
  `deal_checks.find_deal_issues` and `deal_checks.find_lead_issues`.
  `tricks_after_lead` raises rather than repeating those checks, so that a
  caller which skipped them hears about it instead of receiving a number that
  means nothing.
  """
  position = endplay.types.Deal(
    _written_deal(deal), first=_SOLVER_SEATS[declarer.left_hand_opponent]
  )
  position.trump = _SOLVER_STRAINS[strain]

  # The solver reports the position before the first card and after each one, so
  # a single lead comes back as two counts and the second is the one wanted.
  # Unpacking rather than indexing is what holds it to two: any other number of
  # counts would mean this adaptation has misread the solver's contract, and the
  # unpacking then fails loudly instead of quietly taking the wrong one.
  _, after_lead = endplay.dds.analyse_play(
    position, [_written_card(opening_lead)]
  )
  # The solver's result type carries no element annotation, so the count arrives
  # untyped. Converting narrows it here, at the one boundary this project has
  # onto the library, rather than letting an unchecked value travel on as though
  # it had been verified.
  return int(after_lead)


def _written_deal(deal: Deal) -> str:
  """The deal as the solver spells one: four hands, from North clockwise.

  Each hand is spelled the way a PBN deal writes one, which the solver reads.
  """
  hands = ' '.join(
    notation.written_hand(deal.hands[seat]) for seat in _WRITTEN_SEATS
  )
  return f'N:{hands}'


def _written_card(card: Card) -> str:
  """A card as the solver spells one: its suit, then its rank."""
  # Both halves are already the letters the solver reads — a ten is `T` on both
  # sides — so the spelling is a concatenation rather than a translation.
  return f'{card.suit.value}{card.rank.value}'
