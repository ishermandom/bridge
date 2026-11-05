# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

# Minimal stubs for fontTools.pens.ttGlyphPen: only the surface this repo calls.

from fontTools.pens.basePen import AbstractPen
from fontTools.ttLib import _Glyph

class TTGlyphPen(AbstractPen):
  # The glyph set resolves components; None suits outlines drawn from scratch.
  def __init__(self, glyphSet: None) -> None: ...
  def glyph(self) -> _Glyph: ...
