# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Bounded value sets for the bridge domain.

String-valued so they serialize directly to and from the canonical JSON. This
module holds the shared vocabulary; more sets join it as the models that use
them arrive.
"""

import enum


class Direction(enum.StrEnum):
  """A seat at the table — and so a dealer or declarer."""

  NORTH = 'N'
  EAST = 'E'
  SOUTH = 'S'
  WEST = 'W'


class Vulnerability(enum.StrEnum):
  """Which side is vulnerable on a board."""

  NONE = 'none'
  NORTH_SOUTH = 'NS'
  EAST_WEST = 'EW'
  BOTH = 'both'
