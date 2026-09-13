# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

"""The name of one setting in a Bridgodex card export.

An export nests its values as `settings` -> section -> key -> value, and a key
name can recur across sections (both lead panels have a `length_leads_xx`), so a
setting is named by its section and key together.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class BridgodexKey:
  """One setting: its section, and its key within that section."""

  section: str
  key: str

  def __str__(self) -> str:
    """The dotted form messages use, e.g. `majors.drury_2c`."""
    return f'{self.section}.{self.key}'
