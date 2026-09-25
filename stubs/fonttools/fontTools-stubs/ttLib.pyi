# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

# Minimal stubs for fontTools.ttLib: only the surface this repo calls. The
# `Literal` overloads give each table lookup its own shape, so exactly the
# attributes the real tables carry type-check — an unlisted table tag is a
# type error until its shape is added here.

from os import PathLike
from typing import Literal, overload

class _HeadTable:
  unitsPerEm: int

class _OS2Table:
  sCapHeight: int

class _Glyph:
  yMax: int

class _GlyfTable:
  def __getitem__(self, glyph_name: str) -> _Glyph: ...

class _HmtxTable:
  # A glyph's advance width and left side bearing, in font units.
  def __getitem__(self, glyph_name: str) -> tuple[int, int]: ...

class TTFont:
  def __init__(self, file: str | PathLike[str]) -> None: ...
  @overload
  def __getitem__(self, tag: Literal['glyf']) -> _GlyfTable: ...
  @overload
  def __getitem__(self, tag: Literal['head']) -> _HeadTable: ...
  @overload
  def __getitem__(self, tag: Literal['hmtx']) -> _HmtxTable: ...
  @overload
  def __getitem__(self, tag: Literal['OS/2']) -> _OS2Table: ...
  def getBestCmap(self) -> dict[int, str]: ...
