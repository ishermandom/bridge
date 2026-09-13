# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

"""Measure where each text blank's printed rule sits, for `rule_positions.py`.

Renders the blank base card at 1200 dpi, where one pixel is 0.06pt. Under each
text field, it scans a few pixel columns downward for the rule's top edge,
refining that edge to a fraction of a pixel from its antialiasing. The printed
entries replace the table in `rule_positions.py`.

The results are close but inexact. Checked against the card's own geometry, the
32 rules drawn as lines measure exact to the table's 0.01pt rounding, while the
115 printed as rows of underscore characters measure up to 0.04pt off —
presumably because the renderer places glyph edges less faithfully than line
edges. That is about a third of a 600-dpi printer dot.

Exact values would come from the PDF's geometry rather than a render:

- **Underscore rules**: the tops of the underscores' tight character boxes, from
  pypdfium2's `PdfTextPage.get_charbox(index, loose=False)`.
- **Drawn rules**: the line's centerline — its path's segment points
  (`FPDFPath_GetPathSegment`, `FPDFPathSegment_GetPoint`) mapped through the
  object's matrix — plus half its stroke width (`FPDFPageObj_GetStrokeWidth`).
  The path object's bounding box won't do: it pads the stroke, overstating the
  top by up to half a point.

Usage, run from `convention_cards/`:
    python3 -m renderer.measure_rule_positions
"""

import re
import statistics
import sys
from io import BytesIO

import pypdfium2
from PIL import Image

from renderer.geometry import CARD_HEIGHT, FieldKind, load_card_fields
from renderer.private_paths import discover_private_assets

_SCALE = 1200 / 72

# How far above and below a field's bottom edge to look for its rule: the form's
# rectangles sit within about a point of their rules.
_SEARCH_REACH = 2.0

# Where across a field to sample, as fractions of its width.
_SAMPLE_FRACTIONS = (0.2, 0.35, 0.5, 0.65, 0.8)

# How closely one rule's samples must agree. Some rules tilt slightly — the V1NT
# panel's rise ~0.1pt across a field — so the median stands for the rule.
_MAX_SAMPLE_SPREAD = 0.25

# Grayscale pixel values, 0 black to 255 white: at or above `_PAPER` a pixel is
# blank paper, and a rule's interior is at least as dark as `_INK`.
_PAPER = 250
_INK = 200

# How many pixels below a rule's first touched row to look for its interior: a
# rule is about 0.44pt thick, some seven pixels.
_INTERIOR_DEPTH = 6


def measure_rule_tops(base_pdf: bytes) -> dict[str, float]:
  """Measure the rule top under every text field that has one.

  Values are the rule's top-edge y, in points in the card page's coordinates,
  rounded to 0.01pt. A field with no ink under any sample has no rule and is
  left out.

  Raises:
    ValueError: if a field's samples are partial or disagree, which means
      something other than a lone rule sits under it.
  """
  fields = load_card_fields(BytesIO(base_pdf))
  image = _render_grayscale(base_pdf)
  pixels = image.tobytes()

  rule_tops: dict[str, float] = {}
  for field in fields.values():
    if field.kind is not FieldKind.TEXT:
      continue
    samples = [
      _rule_top_at(
        pixels, image.width, field.left + field.width * fraction, field.bottom
      )
      for fraction in _SAMPLE_FRACTIONS
    ]
    found = [sample for sample in samples if sample is not None]
    if not found:
      continue
    if (
      len(found) < len(samples) or max(found) - min(found) > _MAX_SAMPLE_SPREAD
    ):
      raise ValueError(
        f'field {field.name!r} has ambiguous rule samples {samples}'
      )
    rule_tops[field.name] = round(statistics.median(found), 2)
  return rule_tops


def _render_grayscale(base_pdf: bytes) -> Image.Image:
  """Rasterize the blank card's page, form widgets off, as grayscale."""
  document = pypdfium2.PdfDocument(base_pdf)
  try:
    page = document[0].render(scale=_SCALE, may_draw_forms=False)
    return page.to_pil().convert('L')
  finally:
    document.close()


def _rule_top_at(
  pixels: bytes, width: int, x: float, bottom: float
) -> float | None:
  """The top edge of the first ink in one column near a field's bottom edge.

  `pixels` holds the grayscale raster row by row, `width` pixels to a row; `x`
  and `bottom` are in points. None means the column is blank there.
  """
  column = int(x * _SCALE)
  first_row = int((CARD_HEIGHT - (bottom + _SEARCH_REACH)) * _SCALE)
  last_row = int((CARD_HEIGHT - (bottom - _SEARCH_REACH)) * _SCALE)

  for row in range(first_row, last_row):
    value = pixels[row * width + column]
    if value >= _PAPER:
      continue
    interior = min(
      pixels[below * width + column]
      for below in range(row, row + _INTERIOR_DEPTH)
    )
    if interior > _INK:
      continue
    # An edge pixel's darkness is the share of it the rule covers, so the edge
    # sits that share up from the pixel's bottom.
    coverage = (255 - value) / (255 - interior)
    return CARD_HEIGHT - (row + 1 - coverage) / _SCALE
  return None


def _natural_order(name: str) -> list[str | int]:
  """Sort key ordering field numbers numerically: `1C.t.2` before `1C.t.10`."""
  return [
    int(part) if part.isdigit() else part for part in re.split(r'(\d+)', name)
  ]


def main() -> int:
  """Print the measured table's entries, ready to paste into the module."""
  base_pdf = discover_private_assets().base_acbl_card_pdf.read_bytes()
  rule_tops = measure_rule_tops(base_pdf)
  for name in sorted(rule_tops, key=_natural_order):
    print(f"  '{name}': {rule_tops[name]:.2f},")
  return 0


if __name__ == '__main__':
  sys.exit(main())
