# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

# Minimal stubs for fontTools.pens.basePen: only the interface a glyph's `draw`
# takes, and the drawing calls this repo makes on a pen.

class AbstractPen:
  def moveTo(self, pt: tuple[float, float]) -> None: ...
  def lineTo(self, pt: tuple[float, float]) -> None: ...
  def closePath(self) -> None: ...
