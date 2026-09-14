# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

"""Measure where each text blank's printed rule sits, for `rule_positions.py`.

Reads the rules from the card's own drawing instructions rather than from a
render, so each value is exact to the table's 0.01pt rounding. The card prints
its rules two ways:

- **Underscore rules**: rows of `_` characters. A rule's top is the top of its
  underscores' tight character boxes, from the PDF's text layer.
- **Line-art rules**: stroked lines. A rule's top is its centerline plus half
  its stroke width. The line's bounding box won't do: it pads the stroke,
  overstating the top by up to half a point.

Under each text field, samples taken across the field look for the topmost rule
edge near the field's bottom edge. The printed entries replace the table in
`rule_positions.py`.

Usage, run from `convention_cards/`:
    python3 -m renderer.measure_rule_positions
"""

import ctypes
import math
import re
import statistics
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from io import BytesIO

import pypdfium2
import pypdfium2.raw as pdfium

from renderer.geometry import FieldKind, load_card_fields
from renderer.private_paths import discover_private_assets

# A position on the card page: (x, y), measured in points.
_Position = tuple[float, float]

# How far above and below a field's bottom edge to look for its rule, in points:
# the form's rectangles sit within about a point of their rules.
_SEARCH_REACH = 2.0

# Where across a field to sample, as fractions of its width.
_SAMPLE_FRACTIONS = (0.2, 0.35, 0.5, 0.65, 0.8)

# How closely one rule's samples must agree, in points. Some rules tilt slightly
# — the V1NT panel's rise ~0.1pt across a field — so the median stands for the
# rule.
_MAX_SAMPLE_SPREAD = 0.25

# The shape a drawn line needs to count as a rule, in points: at least this
# long, and rising or falling at most this much from end to end — well above the
# V1NT panel's tilt, well below any box's side.
_MIN_RULE_LENGTH = 1.0
_MAX_RULE_RISE = 0.5

# How far a curve's control points may stray from its chord, in points, for the
# curve to count as a straight line.
_STRAIGHTNESS_TOLERANCE = 0.01

# How closely neighboring underscores' tops must agree to form one rule, in
# points.
_RUN_TOP_TOLERANCE = 0.01


@dataclass(frozen=True)
class _Rule:
  """One printed rule's top edge, spanning x from `left` to `right`.

  The edge runs straight from `top_at_left` to `top_at_right`; on a level rule
  the two are equal.
  """

  left: float
  right: float
  top_at_left: float
  top_at_right: float

  def top_at(self, x: float) -> float:
    """The edge's height at `x`, which must lie within the rule's span."""
    if self.top_at_left == self.top_at_right:
      return self.top_at_left
    share = (x - self.left) / (self.right - self.left)
    return self.top_at_left + share * (self.top_at_right - self.top_at_left)


def measure_rule_tops(base_pdf: bytes) -> dict[str, float]:
  """Measure the rule top under every text field that has one.

  Values are the rule's top-edge y, in points in the card page's coordinates,
  rounded to 0.01pt. A field with no rule under any sample is left out.

  Raises:
    ValueError: if a field's samples are partial or disagree, which means
      something other than a lone rule sits under it.
  """
  fields = load_card_fields(BytesIO(base_pdf))
  document = pypdfium2.PdfDocument(base_pdf)
  try:
    page = document[0]
    rules = _line_art_rules(page) + _underscore_rules(page)
  finally:
    document.close()

  rule_tops: dict[str, float] = {}
  for field in fields.values():
    if field.kind is not FieldKind.TEXT:
      continue
    # Only rules near the field's bottom edge can answer its samples. A tilted
    # rule's left end may sit up to its rise away from where a sample crosses
    # it, hence the extra reach.
    nearby = [
      rule
      for rule in rules
      if abs(rule.top_at_left - field.bottom) <= _SEARCH_REACH + _MAX_RULE_RISE
    ]
    samples = [
      _rule_top_at(nearby, field.left + field.width * fraction, field.bottom)
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


def _rule_top_at(
  rules: Sequence[_Rule], x: float, bottom: float
) -> float | None:
  """The topmost rule edge crossing `x` within reach of a field's `bottom`.

  None means no rule crosses there.
  """
  tops = [rule.top_at(x) for rule in rules if rule.left <= x <= rule.right]
  return max(
    (top for top in tops if abs(top - bottom) <= _SEARCH_REACH), default=None
  )


def _underscore_rules(page: pypdfium2.PdfPage) -> list[_Rule]:
  """Each run of neighboring underscores at one height, as one rule.

  Taking whole runs rather than single characters bridges a quirk in O.t.1's
  rule: it ends in a separate text object drawing two underscores stretched
  about nine times wide, which the text layer reports as a single underscore
  boxed over only the second.

  Raises:
    ValueError: if the extracted text doesn't line up one-to-one with the text
      layer's characters, so character boxes can't be matched to characters.
  """
  textpage = page.get_textpage()
  count = textpage.count_chars()
  text = textpage.get_text_range(0, count)
  if len(text) != count:
    raise ValueError(
      f'text layer holds {count} characters but extracts as {len(text)}'
    )

  runs: list[list[tuple[float, float, float, float]]] = []
  continues_run = False
  for index, character in enumerate(text):
    if character != '_':
      continues_run = False
      continue
    box = textpage.get_charbox(index, loose=False)
    # A box is (left, bottom, right, top).
    if continues_run and abs(box[3] - runs[-1][-1][3]) <= _RUN_TOP_TOLERANCE:
      runs[-1].append(box)
    else:
      runs.append([box])
    continues_run = True

  rules = []
  for run in runs:
    top = max(box[3] for box in run)
    left = min(box[0] for box in run)
    right = max(box[2] for box in run)
    rules.append(_Rule(left, right, top_at_left=top, top_at_right=top))
  return rules


def _line_art_rules(page: pypdfium2.PdfPage) -> list[_Rule]:
  """Each stroked, nearly level straight line on the page, as a rule."""
  rules = []
  for path in page.get_objects(filter=[pdfium.FPDF_PAGEOBJ_PATH]):
    if not _is_stroked(path):
      continue
    matrix = _page_matrix(path)
    # The card draws its rules unrotated, so only the matrix's vertical scale
    # sizes how far the stroke reaches above its centerline.
    half_width = _stroke_width(path) * abs(matrix.d) / 2
    for (x1, y1), (x2, y2) in _straight_segments(path, matrix):
      if abs(x2 - x1) < _MIN_RULE_LENGTH or abs(y2 - y1) > _MAX_RULE_RISE:
        continue
      (left, left_y), (right, right_y) = sorted([(x1, y1), (x2, y2)])
      rules.append(
        _Rule(left, right, left_y + half_width, right_y + half_width)
      )
  return rules


def _page_matrix(page_object: pypdfium2.PdfObject) -> pypdfium2.PdfMatrix:
  """The matrix mapping an object's own coordinates onto the page.

  An object inside a form object — where the card keeps its artwork — is placed
  by the form's matrix too, and so on outward.
  """
  matrix = page_object.get_matrix()
  container = page_object.container
  while container is not None:
    matrix = matrix.multiply(container.get_matrix())
    container = container.container
  return matrix


def _straight_segments(
  path: pypdfium2.PdfObject, matrix: pypdfium2.PdfMatrix
) -> Iterator[tuple[_Position, _Position]]:
  """Each straight piece of a path, as its endpoints in page coordinates.

  A line-to draws from the current position to its own. A cubic Bézier arrives
  as three positions — two control points, then its end — and counts as straight
  when its control points sit on its chord: the V1NT panel draws its rules that
  way.

  Raises:
    ValueError: if the path holds a segment of unknown type.
  """
  segments = list(_segment_positions(path, matrix))
  current: _Position | None = None
  index = 0
  while index < len(segments):
    kind, position = segments[index]
    controls: tuple[_Position, ...]
    if kind == pdfium.FPDF_SEGMENT_MOVETO:
      current = position
      index += 1
      continue
    if kind == pdfium.FPDF_SEGMENT_LINETO:
      controls, end = (), position
      index += 1
    elif kind == pdfium.FPDF_SEGMENT_BEZIERTO:
      controls = (position, segments[index + 1][1])
      end = segments[index + 2][1]
      index += 3
    else:
      raise ValueError(f'path segment {index} has unknown type {kind}')
    if current is not None and _is_straight(current, controls, end):
      yield current, end
    current = end


def _segment_positions(
  path: pypdfium2.PdfObject, matrix: pypdfium2.PdfMatrix
) -> Iterator[tuple[int, _Position]]:
  """Each of a path's segments, as its type and its position on the page.

  Raises:
    PdfiumError: if PDFium can't read the path.
  """
  count = pdfium.FPDFPath_CountSegments(path)
  if count < 0:
    raise pypdfium2.PdfiumError('PDFium could not count path segments')
  for index in range(count):
    segment = pdfium.FPDFPath_GetPathSegment(path, index)
    x, y = ctypes.c_float(), ctypes.c_float()
    if not pdfium.FPDFPathSegment_GetPoint(segment, x, y):
      raise pypdfium2.PdfiumError(f'PDFium could not read path segment {index}')
    kind = pdfium.FPDFPathSegment_GetType(segment)
    yield kind, matrix.on_point(x.value, y.value)


def _is_straight(
  start: _Position, controls: Sequence[_Position], end: _Position
) -> bool:
  """Whether every control point lies on the line through `start` and `end`."""
  (x1, y1), (x2, y2) = start, end
  length = math.hypot(x2 - x1, y2 - y1)
  if not length:
    return all(control == start for control in controls)
  # The cross product's magnitude over the chord's length is the control point's
  # distance from the chord's line.
  return all(
    abs((x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)) / length
    <= _STRAIGHTNESS_TOLERANCE
    for x, y in controls
  )


def _is_stroked(path: pypdfium2.PdfObject) -> bool:
  """Whether the path is drawn with a stroke, rather than only filled.

  Raises:
    PdfiumError: if PDFium can't read the path's draw mode.
  """
  fill_mode, stroke = ctypes.c_int(), ctypes.c_int()
  if not pdfium.FPDFPath_GetDrawMode(path, fill_mode, stroke):
    raise pypdfium2.PdfiumError('PDFium could not read a path draw mode')
  return bool(stroke.value)


def _stroke_width(path: pypdfium2.PdfObject) -> float:
  """The path's stroke width, in its own coordinates.

  Raises:
    PdfiumError: if PDFium can't read the stroke width.
  """
  width = ctypes.c_float()
  if not pdfium.FPDFPageObj_GetStrokeWidth(path, width):
    raise pypdfium2.PdfiumError('PDFium could not read a stroke width')
  return width.value


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
