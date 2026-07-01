# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Compute the dealer and vulnerability fixed to each board number.

In duplicate bridge a board's dealer and vulnerability aren't a property of the
session — they follow a standard schedule keyed only to the board number, so
they're computed rather than read from the sheet (see spec.md). The schedule
repeats every sixteen boards.
"""

from session_analysis.enums import Direction, Vulnerability

# Dealer steps through the seats by board number — board 1 North, 2 East, and so
# on — repeating every four boards.
_DEALERS = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)

# Vulnerability steps through this sequence within each block of four boards;
# each successive block starts one step further along it, so the whole schedule
# repeats every sixteen boards.
_VULNERABILITY_CYCLE = (
  Vulnerability.NONE,
  Vulnerability.NORTH_SOUTH,
  Vulnerability.EAST_WEST,
  Vulnerability.BOTH,
)


def dealer_for_board(board_number: int) -> Direction:
  """Return the dealer for a board from its number (1-indexed)."""
  return _DEALERS[(board_number - 1) % 4]


def vulnerability_for_board(board_number: int) -> Vulnerability:
  """Return the vulnerability for a board from its number (1-indexed).

  Within each block of four boards the vulnerability steps through the cycle
  none / NS / EW / both; each successive block starts one step further along, so
  the pattern repeats every sixteen boards.
  """
  position_in_block = (board_number - 1) % 4
  block = ((board_number - 1) // 4) % 4
  return _VULNERABILITY_CYCLE[(position_in_block + block) % 4]
