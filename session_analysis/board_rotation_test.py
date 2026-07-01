# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for the dealer and vulnerability schedule."""

import pytest

from session_analysis.board_rotation import (
  dealer_for_board,
  vulnerability_for_board,
)
from session_analysis.enums import Direction, Vulnerability

# The standard schedule for a full sixteen-board cycle — (board, dealer,
# vulnerability) — as printed in the scoresheet's Dlr/Vul column.
_SCHEDULE = (
  (1, Direction.NORTH, Vulnerability.NONE),
  (2, Direction.EAST, Vulnerability.NORTH_SOUTH),
  (3, Direction.SOUTH, Vulnerability.EAST_WEST),
  (4, Direction.WEST, Vulnerability.BOTH),
  (5, Direction.NORTH, Vulnerability.NORTH_SOUTH),
  (6, Direction.EAST, Vulnerability.EAST_WEST),
  (7, Direction.SOUTH, Vulnerability.BOTH),
  (8, Direction.WEST, Vulnerability.NONE),
  (9, Direction.NORTH, Vulnerability.EAST_WEST),
  (10, Direction.EAST, Vulnerability.BOTH),
  (11, Direction.SOUTH, Vulnerability.NONE),
  (12, Direction.WEST, Vulnerability.NORTH_SOUTH),
  (13, Direction.NORTH, Vulnerability.BOTH),
  (14, Direction.EAST, Vulnerability.NONE),
  (15, Direction.SOUTH, Vulnerability.NORTH_SOUTH),
  (16, Direction.WEST, Vulnerability.EAST_WEST),
)

# --- the standard schedule ---


@pytest.mark.parametrize(('board_number', 'dealer', 'vulnerability'), _SCHEDULE)
def test_board_matches_the_standard_schedule(
  board_number: int, dealer: Direction, vulnerability: Vulnerability
) -> None:
  assert dealer_for_board(board_number) == dealer
  assert vulnerability_for_board(board_number) == vulnerability


# --- the schedule repeats every sixteen boards ---


def test_dealer_repeats_after_sixteen_boards() -> None:
  # Board 17 deals like board 1, board 33 like board 1 again.
  assert dealer_for_board(17) == dealer_for_board(1)
  assert dealer_for_board(33) == dealer_for_board(1)


def test_vulnerability_repeats_after_sixteen_boards() -> None:
  assert vulnerability_for_board(17) == vulnerability_for_board(1)
  assert vulnerability_for_board(33) == vulnerability_for_board(1)
