# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Name the interchangeable glyph variants a transcribed sheet may use.

A handwritten sheet — and the vision model transcribing it — renders some
characters many ways: a minus, whether it marks a set contract or strikes out a
passed-out cell, can arrive as an ASCII hyphen, a Unicode minus sign, an en
dash, an em dash, and more. This module names those variants once, so every
reader treats them alike rather than each pattern re-listing the set and
drifting out of step. See spec.md (Notation and normalization).
"""

# Every dash glyph a sheet may use interchangeably for a minus or a strike-
# through. Named by code point, not literal: several are visually
# indistinguishable, so the code point keeps the set reviewable. A novel form is
# a one-line addition here that every consumer picks up at once.
DASHES = ''.join(
  chr(code_point)
  for code_point in (
    0x2D,  # hyphen-minus (ASCII)
    0x2010,  # hyphen
    0x2011,  # non-breaking hyphen
    0x2012,  # figure dash
    0x2013,  # en dash
    0x2014,  # em dash
    0x2015,  # horizontal bar
    0x2212,  # minus sign
  )
)
