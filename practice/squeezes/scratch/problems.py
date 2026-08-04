# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Problem model: fixed declarer-side cards plus a family of defender layouts.

A problem deliberately does not pin down the defenders' hands. It carries every
layout the position intends to pose, and the play engine holds declarer to a
line that works against all of them — the quantum-defenders model, see
../spec.md #quantum-defenders.
"""

from __future__ import annotations

from dataclasses import dataclass

from cards import Card, Seat


@dataclass(frozen=True)
class Layout:
  """One way the defenders' cards might lie."""

  west: frozenset[Card]
  east: frozenset[Card]


@dataclass(frozen=True)
class Problem:
  """An ending to play out: visible hands, a layout family, a trick target.

  Notrump only for now; `target_tricks` counts declarer-side tricks from this
  position to the end. Every layout must deal the same combined set of defender
  cards — the family varies only in how those cards divide between West and
  East.
  """

  north: frozenset[Card]
  south: frozenset[Card]
  layouts: tuple[Layout, ...]
  leader: Seat
  target_tricks: int

  def __post_init__(self) -> None:
    """Reject internally inconsistent problems loudly at construction."""
    if not self.layouts:
      raise ValueError('a problem needs at least one layout')

    hand_size = len(self.north)
    defender_pool = self.layouts[0].west | self.layouts[0].east
    for layout in self.layouts:
      sizes = (len(self.south), len(layout.west), len(layout.east))
      if any(size != hand_size for size in sizes):
        raise ValueError(
          f'unbalanced hands: North has {hand_size} cards, '
          f'South/West/East have {sizes}'
        )
      if layout.west & layout.east:
        raise ValueError(
          f'West and East overlap in a layout: {layout.west & layout.east}'
        )
      if layout.west | layout.east != defender_pool:
        raise ValueError(
          'layouts deal different defender card pools: '
          f'{layout.west | layout.east} vs {defender_pool}'
        )

    if defender_pool & (self.north | self.south):
      raise ValueError(
        f'defender cards overlap declarer side: '
        f'{defender_pool & (self.north | self.south)}'
      )
    if not 1 <= self.target_tricks <= hand_size:
      raise ValueError(
        f'target of {self.target_tricks} tricks is impossible with '
        f'{hand_size}-card hands'
      )
