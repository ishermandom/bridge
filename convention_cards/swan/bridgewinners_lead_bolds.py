# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

"""Read a BridgeWinners card PDF's bold length-lead defaults.

On each length holding the pair leaves unmarked, BridgeWinners prints a default
lead in bold, computed from the pair's lead-convention checkboxes. Because the
bolds follow those checkboxes, they differ from card to card, and even between
one card's suit and notrump panels. Rather than reverse-engineer BridgeWinners'
rule, this module measures the bolds from the specific card's own PDF, via the
text layer's per-character font names.

Only the length holdings matter here: the ACBL card prints no bold defaults for
them, so a BridgeWinners bold is an agreement the converted card would otherwise
lose. The honor and interior holdings have printed bold defaults on both cards,
so the converter never needs to turn their bolds into circles.
"""

import ctypes
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pypdfium2
from bridgodex_key import BridgodexKey
from pypdfium2.raw import FPDFText_GetFontInfo

# The length holdings' Bridgodex keys, in print order within each panel.
_PLAIN_ROW = (
  'length_leads_xx',
  'length_leads_xxx',
  'length_leads_xxxx',
  'length_leads_xxxxx',
)
_HONOR_ROW = ('length_leads_Hxx', 'length_leads_Hxxx', 'length_leads_Hxxxx')
_PANELS = ('leads_vs_suits', 'leads_vs_nt')

# Characters on the same text row sit within this vertical tolerance.
_ROW_TOLERANCE = 3.0


@dataclass(frozen=True)
class Char:
  """One text-layer character: its glyph, position, and boldness."""

  text: str
  left: float
  center_y: float
  is_bold: bool


def measure_length_bolds(pdf_bytes: bytes) -> Mapping[BridgodexKey, int]:
  """Map each bolded length holding to its bold card's 1-based position.

  Raises:
    ValueError: if the PDF doesn't look like a BridgeWinners convention card,
      or a length holding has more than one bold card.
  """
  return length_bolds_from_chars(_extract_chars(pdf_bytes))


def _extract_chars(pdf_bytes: bytes) -> list[Char]:
  """Pull every non-blank character, with its position and boldness."""
  document = pypdfium2.PdfDocument(pdf_bytes)
  try:
    # The card is the PDF's first page — in every observed export, its only one.
    textpage = document[0].get_textpage()
    chars: list[Char] = []
    for index in range(textpage.count_chars()):
      text = textpage.get_text_range(index, 1)
      if not text.strip():
        continue
      left, bottom, _right, top = textpage.get_charbox(index)
      # pypdfium2's high-level text API doesn't expose a character's font, so
      # call the raw binding for the font name. The call also fills in font
      # flags, which this reader ignores.
      buffer = ctypes.create_string_buffer(128)
      flags = ctypes.c_int()
      FPDFText_GetFontInfo(
        textpage, index, buffer, len(buffer), ctypes.byref(flags)
      )
      font_name = buffer.value.decode('utf-8', 'replace')
      chars.append(Char(text, left, (bottom + top) / 2, 'Bold' in font_name))
    return chars
  finally:
    document.close()


def length_bolds_from_chars(
  chars: Sequence[Char],
) -> Mapping[BridgodexKey, int]:
  """Find the two length rows and read each holding's bold position.

  The plain row holds the 28 `x` cards of both panels' `xx xxx xxxx xxxxx` (14
  per panel); the honor row holds the 24 cards of `Hxx Hxxx Hxxxx` (12 per
  panel). Each row is recognized by its card count and split into holdings by
  those fixed sizes; the honor split also checks that each holding starts at its
  `H`.

  Raises:
    ValueError: if either row is missing or misshapen, or a holding has more
      than one bold card.
  """
  rows = _cluster_rows(chars)

  bolds: dict[BridgodexKey, int] = {}
  plain_row_found = False
  honor_row_found = False
  for row in rows:
    x_cards = [char for char in row if char.text == 'x']
    holding_cards = [char for char in row if char.text in 'Hx']
    # Equal counts mean the row carries no H's.
    if len(x_cards) == 28 and len(holding_cards) == 28:
      _read_plain_row(x_cards, bolds)
      plain_row_found = True
    # 24 cards, six of them H's: `Hxx Hxxx Hxxxx` in each panel.
    elif (
      len(holding_cards) == 24
      and sum(c.text == 'H' for c in holding_cards) == 6
    ):
      _read_honor_row(holding_cards, bolds)
      honor_row_found = True

  if not (plain_row_found and honor_row_found):
    raise ValueError(
      'PDF has no recognizable length-lead rows; is it a BridgeWinners'
      f' convention card? (xx through xxxxx row found: {plain_row_found},'
      f' Hxx through Hxxxx row found: {honor_row_found})'
    )
  return bolds


def _cluster_rows(chars: Sequence[Char]) -> list[list[Char]]:
  """Group characters into text rows by vertical position."""
  ordered = sorted(chars, key=lambda c: (-c.center_y, c.left))
  rows: list[list[Char]] = []
  for char in ordered:
    if rows and abs(rows[-1][0].center_y - char.center_y) < _ROW_TOLERANCE:
      rows[-1].append(char)
    else:
      rows.append([char])
  for row in rows:
    row.sort(key=lambda c: c.left)
  return rows


def _read_plain_row(
  cards: Sequence[Char], bolds: dict[BridgodexKey, int]
) -> None:
  """Split the 28 plain cards into 2/3/4/5 per panel and record bolds."""
  position = 0
  for panel in _PANELS:
    for key, size in zip(_PLAIN_ROW, (2, 3, 4, 5), strict=True):
      _record_holding(
        cards[position : position + size], BridgodexKey(panel, key), bolds
      )
      position += size


def _read_honor_row(
  cards: Sequence[Char], bolds: dict[BridgodexKey, int]
) -> None:
  """Split the 24 honor cards into 3/4/5 per panel and record bolds."""
  position = 0
  for panel in _PANELS:
    for key, size in zip(_HONOR_ROW, (3, 4, 5), strict=True):
      holding = cards[position : position + size]
      setting = BridgodexKey(panel, key)
      if holding[0].text != 'H' or any(c.text != 'x' for c in holding[1:]):
        found = ''.join(char.text for char in holding)
        raise ValueError(
          f'honor length row is misshapen at {setting}: expected an H and then'
          f" x's, found {found!r}"
        )
      _record_holding(holding, setting, bolds)
      position += size


def _record_holding(
  holding: Sequence[Char],
  setting: BridgodexKey,
  bolds: dict[BridgodexKey, int],
) -> None:
  """Record the holding's single bold position, if it has one."""
  positions = [i + 1 for i, char in enumerate(holding) if char.is_bold]
  if len(positions) > 1:
    raise ValueError(f'{setting} has {len(positions)} bold cards')
  if positions:
    bolds[setting] = positions[0]
