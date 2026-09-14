# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

# Minimal stubs for pypdfium2's raw PDFium bindings: only the calls this
# repo makes. The helper objects (e.g. PdfTextPage) convert themselves to
# raw handles via ctypes, so they pass directly as the handle arguments.

import ctypes

from . import PdfObject, PdfTextPage

FPDF_PAGEOBJ_PATH: int
FPDF_SEGMENT_LINETO: int
FPDF_SEGMENT_BEZIERTO: int
FPDF_SEGMENT_MOVETO: int

# An opaque handle to one segment of a path object.
class FPDF_PATHSEGMENT: ...

# Each out-parameter below takes a ctypes value, which ctypes passes by
# reference on its own.
def FPDFPath_CountSegments(path: PdfObject) -> int: ...
def FPDFPath_GetPathSegment(
  path: PdfObject, index: int
) -> FPDF_PATHSEGMENT: ...
def FPDFPathSegment_GetPoint(
  segment: FPDF_PATHSEGMENT, x: ctypes.c_float, y: ctypes.c_float
) -> int: ...
def FPDFPathSegment_GetType(segment: FPDF_PATHSEGMENT) -> int: ...
def FPDFPath_GetDrawMode(
  path: PdfObject, fillmode: ctypes.c_int, stroke: ctypes.c_int
) -> int: ...
def FPDFPageObj_GetStrokeWidth(
  page_object: PdfObject, width: ctypes.c_float
) -> int: ...
def FPDFText_GetFontInfo(
  text_page: PdfTextPage,
  index: int,
  buffer: ctypes.Array[ctypes.c_char],
  buflen: int,
  flags: object,
) -> int: ...
