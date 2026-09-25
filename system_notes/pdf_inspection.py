# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Read back what a rendered PDF contains.

Verifying a render asks three things of the finished file: what text landed on
each page, which page each heading is on, and which fonts it embedded. poppler's
`pdftotext` reads the text, and its `-layout` mode keeps column order and
running headers, so the result can serve as a golden. The PDF's outline — the
bookmarks WeasyPrint writes for every heading — gives each heading its page,
read through pypdf. `pdffonts` lists the fonts, and that list is where a silent
fallback to an unintended face shows itself.
"""

import re
import subprocess
from collections.abc import Mapping, Sequence, Set
from pathlib import Path

from pypdf import PdfReader
from pypdf.generic import Destination

# A PDF outline nests: a heading's subsections follow it as a sequence.
type Outline = Sequence[Destination | Outline]

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


def heading_pages(pdf: Path) -> Mapping[str, int]:
  """Map each heading's text to its 1-based page, from the PDF's bookmarks.

  Keyed by title, because a cross-reference cites a title rather than a number.
  Two headings sharing one would collide in the map, so the second raises rather
  than overwriting the first. That constraint is this map's, not the renderer's,
  which is content with duplicate titles: only the fixture, whose pages this
  reads in the page-reference test, has to avoid them.
  """
  reader = PdfReader(str(pdf))
  pages: dict[str, int] = {}

  def visit(entries: Outline) -> None:
    for entry in entries:
      if not isinstance(entry, Destination):
        visit(entry)
      elif entry.title is not None:
        page_index = reader.get_destination_page_number(entry)
        if page_index is None:
          raise ValueError(f'bookmark {entry.title!r} in {pdf} has no page')
        if entry.title in pages:
          raise ValueError(
            f'bookmark title {entry.title!r} appears twice in {pdf}; the '
            "unnumbered titles are this map's keys, so they must be unique"
          )
        pages[entry.title] = page_index + 1

  visit(reader.outline)
  return pages


def page_text_heights(pdf: Path) -> Sequence[float]:
  """Return, per page, the lowest text edge — the page's used height.

  Read from `pdftotext -bbox` word boxes, in points from the page's top. A page
  with no words measures 0. Text bounds miss any trailing margin or padding; a
  caller that needs such spacing counted must make it visible, as
  `print_layout`'s probe does with a sentinel line after each atom.
  """
  xml = _run_poppler(['pdftotext', '-bbox', str(pdf), '-'])
  bottom_edge = re.compile(r'yMax="(?P<y>[0-9.]+)"')
  heights = []
  for page in xml.split('<page ')[1:]:
    heights.append(
      max(
        (float(word.group('y')) for word in bottom_edge.finditer(page)),
        default=0.0,
      )
    )
  return heights


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
