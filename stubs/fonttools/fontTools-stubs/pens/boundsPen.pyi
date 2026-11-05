# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

# Minimal stubs for fontTools.pens.boundsPen: only the surface this repo calls.

from collections.abc import Mapping

from fontTools.pens.basePen import AbstractPen

class BoundsPen(AbstractPen):
  # The extent of the outlines drawn so far, as (xMin, yMin, xMax, yMax) in font
  # units, or None while nothing drawn has carried ink.
  bounds: tuple[float, float, float, float] | None
  def __init__(self, glyphSet: Mapping[str, object]) -> None: ...
