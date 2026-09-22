# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Read back what a rendered PDF contains.

Verifying a render asks two things of the finished file: what text landed on
each page, and which fonts it embedded. poppler's `pdftotext` reads the text,
and its `-layout` mode keeps column order and running headers, so the result can
serve as a golden. `pdffonts` lists the fonts, and that list is where a silent
fallback to an unintended face shows itself.
"""

import re
import subprocess
from collections.abc import Sequence, Set
from pathlib import Path

# WeasyPrint names an embedded font `Family-Style`, and one face can carry
# several styles: a bold italic arrives as `-Bold-Italic`. Strip the suffix and
# the family is what remains.
STYLE_SUFFIX = re.compile(r'(?:-(?:Bold|Italic|BoldItalic))+$')


def _run_poppler(command: Sequence[str]) -> str:
  """Run one poppler tool, returning its stdout."""
  return subprocess.run(
    command, capture_output=True, text=True, encoding='utf-8', check=True
  ).stdout


def extract_text(pdf: Path) -> str:
  """Return the PDF's text, laid out as on the page (`pdftotext -layout`)."""
  return _run_poppler(['pdftotext', '-layout', str(pdf), '-'])


def embedded_font_families(pdf: Path) -> Set[str]:
  """Return the embedded fonts' family names, styles and subset tags dropped."""
  # Source Sans 3 reports a trailing comma after its name, which is no part of
  # the family.
  return frozenset(
    STYLE_SUFFIX.sub('', name.rstrip(',')) for name in embedded_font_names(pdf)
  )


def embedded_font_names(pdf: Path) -> Set[str]:
  """Return the embedded fonts' names, without their subset prefixes.

  `pdffonts` prints a fixed-width table whose first column holds the font name
  as `ABCDEF+Name`. The six-letter prefix marks a subset and changes from render
  to render, so this drops it. A name can carry spaces, so this slices each row
  at the header's `type` column rather than splitting on whitespace.
  """
  listing = _run_poppler(['pdffonts', str(pdf)]).splitlines()
  header, _underline, *rows = listing
  name_column_width = header.index('type')
  names = set()
  for row in rows:
    name = row[:name_column_width].strip()
    names.add(name.split('+')[-1])
  return frozenset(names)
