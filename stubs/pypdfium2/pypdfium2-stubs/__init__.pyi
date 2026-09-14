# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

# Minimal stubs for pypdfium2: only the surface this repo calls. See the
# README two levels up before extending.

from collections.abc import Iterator, Sequence
from os import PathLike

from PIL import Image

class PdfiumError(Exception): ...

class PdfBitmap:
  def to_pil(self) -> Image.Image: ...

class PdfMatrix:
  a: float
  b: float
  c: float
  d: float
  e: float
  f: float
  def multiply(self, other: PdfMatrix) -> PdfMatrix: ...
  def on_point(self, x: float, y: float) -> tuple[float, float]: ...

class PdfObject:
  type: int
  # The form object this one sits inside, or None for one directly on the page.
  container: PdfObject | None
  def get_matrix(self) -> PdfMatrix: ...

class PdfTextPage:
  def count_chars(self) -> int: ...
  def get_text_range(self, index: int = 0, count: int = -1) -> str: ...
  def get_charbox(
    self, index: int, loose: bool = False
  ) -> tuple[float, float, float, float]: ...

class PdfPage:
  def get_width(self) -> float: ...
  def get_height(self) -> float: ...
  def render(
    self,
    scale: float = 1,
    rotation: int = 0,
    crop: tuple[float, float, float, float] = (0, 0, 0, 0),
    may_draw_forms: bool = True,
  ) -> PdfBitmap: ...
  def get_textpage(self) -> PdfTextPage: ...
  def get_objects(
    self, filter: Sequence[int] | None = None, max_depth: int = 15
  ) -> Iterator[PdfObject]: ...

class PdfDocument:
  def __init__(self, input: bytes | str | PathLike[str]) -> None: ...
  def __len__(self) -> int: ...
  def __getitem__(self, index: int) -> PdfPage: ...
  def close(self) -> None: ...
