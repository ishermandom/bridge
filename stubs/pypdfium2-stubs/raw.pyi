# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

# Minimal stubs for pypdfium2's raw PDFium bindings: only the calls this
# repo makes. The helper objects (e.g. PdfTextPage) convert themselves to
# raw handles via ctypes, so they pass directly as the handle arguments.

import ctypes

from . import PdfTextPage

def FPDFText_GetFontInfo(
  text_page: PdfTextPage,
  index: int,
  buffer: ctypes.Array[ctypes.c_char],
  buflen: int,
  flags: object,
) -> int: ...
