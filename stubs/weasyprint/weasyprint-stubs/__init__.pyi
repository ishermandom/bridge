# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

# Minimal stubs for WeasyPrint: only the surface this repo calls. See the
# README two levels up before extending.

class Document:
  pages: list[object]
  def write_pdf(self, target: str) -> None: ...

class HTML:
  def __init__(self, *, string: str) -> None: ...
  def render(self) -> Document: ...
  def write_pdf(self, target: str) -> None: ...
