# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

# Minimal stubs for WeasyPrint: only the surface this repo calls. See the
# README two levels up before extending.

class HTML:
  def __init__(self, *, string: str) -> None: ...
  def write_pdf(self, target: str) -> None: ...
