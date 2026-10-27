# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Rewrite the stored session records for scans read as delivered.

A record's `source.image` held a `frame`: the corner quad its scan was dewarped
by, and the geometry resolved in the dewarped image. The scan is now read as
delivered (spec.md `#scan-read-as-delivered`), so the record holds `geometry`
alone, in the scan's own pixels. This rewrites every record in the private tree
to that shape:

- **A record framed by its page's own corners** — ingested with the dewarp
  skipped — already has its geometry in the scan's pixels, and keeps it.
- **A record whose hash names no archived scan** — a model comparison's answer
  key, whose provenance is a stand-in — keeps its geometry as it is.
- **Every other record** has its geometry measured again on the archived scan.
  Its rows and footer are mapped back through the quad onto the scan, and
  `resolve_sheet_geometry` finds the printed rules from there, taking the
  record's own row count. No model call is made.

By default it is a dry run, printing what each record would become; `--write`
rewrites the records in place, serialized as ingest writes them. Run it once, in
the same step that lands the change removing `source_quad`: code from before
that change cannot read a rewritten record, and code from after it cannot read
an old one.
"""

import argparse
import hashlib
import json
import pathlib
import statistics
from collections.abc import Sequence

from PIL import Image

from session_analysis.frozen_model import FrozenModel
from session_analysis.models import Session
from session_analysis.private_paths import PrivateTree, discover_private_tree
from session_analysis.unreviewed.rule_grid import SheetGeometryError
from session_analysis.unreviewed.scan_decoding import DecodedScan, decode_scan
from session_analysis.unreviewed.sheet_geometry import (
  BoardPanel,
  Box,
  SheetGeometry,
  resolve_sheet_geometry,
)

# A re-measured row whose center moved this far from where the record had it, in
# row pitches, would be a different row; the record is refused rather than
# rewritten. Across the archive the largest move was 0.40 of a pitch, on the
# sheet the dewarp had tilted most.
_MAXIMUM_ROW_SHIFT_IN_PITCHES = 0.5


class _MigrationError(Exception):
  """Raised when a record cannot be migrated safely."""


class _Point(FrozenModel):
  """A stored quad corner, in scan pixels."""

  x: float
  y: float


class _Quad(FrozenModel):
  """The stored corner quad a scan was dewarped by."""

  top_left: _Point
  bottom_left: _Point
  bottom_right: _Point
  top_right: _Point


class _Frame(FrozenModel):
  """A record's `frame`: the quad, and the geometry in the dewarped image."""

  geometry: SheetGeometry
  source_quad: _Quad


class _OldSheetImage(FrozenModel):
  """A record's `source.image` in the shape this migrates from."""

  path: str
  content_hash: str
  page: int = 1
  frame: _Frame


def main() -> None:
  """Rewrite, or report on, every stored record that still holds a frame."""
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument(
    '--write',
    action='store_true',
    help='rewrite the records in place (default: report only)',
  )
  parser.add_argument(
    '--private-tree',
    type=pathlib.Path,
    help="a copy of the private tree to work on (default: this checkout's)",
  )
  args = parser.parse_args()

  tree = (
    PrivateTree(args.private_tree)
    if args.private_tree
    else discover_private_tree()
  )
  for record_path in sorted(tree.root.rglob('*.json')):
    # A link to a record — as a model comparison's answer key can be — is
    # migrated through the record it points at, and reported there.
    if record_path.is_symlink():
      continue
    record = json.loads(record_path.read_text())
    if not _holds_a_frame(record):
      continue
    try:
      migrated, summary = _migrated(record, tree)
    except (_MigrationError, SheetGeometryError) as error:
      raise SystemExit(f'{record_path}: {error}') from error
    print(f'{record_path.relative_to(tree.root)}: {summary}')
    if args.write:
      session = Session.model_validate(migrated)
      record_path.write_text(session.model_dump_json(indent=2) + '\n')


def _holds_a_frame(record: object) -> bool:
  """Whether a JSON file is a session record in the old shape."""
  if not isinstance(record, dict):
    return False
  source = record.get('source')
  if not isinstance(source, dict):
    return False
  image = source.get('image')
  return isinstance(image, dict) and 'frame' in image


def _migrated(
  record: dict[str, object], tree: PrivateTree
) -> tuple[dict[str, object], str]:
  """The record in its new shape, and a line saying what became of it."""
  source = record['source']
  assert isinstance(source, dict)
  image = _OldSheetImage.model_validate(source['image'])
  geometry = image.frame.geometry
  quad = image.frame.source_quad

  scan_path = tree.scan_archive / image.path
  if _is_page_corners(quad, geometry):
    new_geometry, summary = geometry, 'framed by its page corners; kept'
  elif (
    not scan_path.is_file()
    or hashlib.sha256(scan_path.read_bytes()).hexdigest() != image.content_hash
  ):
    new_geometry, summary = geometry, 'no archived scan; stand-in kept'
  else:
    scan = _scan_page(scan_path, image.page)
    new_geometry = _remeasured(scan, geometry, quad)
    summary = _describe_remeasure(geometry, new_geometry, quad)

  new_image = {
    'path': image.path,
    'content_hash': image.content_hash,
    'page': image.page,
    'geometry': json.loads(new_geometry.model_dump_json()),
  }
  return {**record, 'source': {**source, 'image': new_image}}, summary


def _is_page_corners(quad: _Quad, geometry: SheetGeometry) -> bool:
  """Whether the quad is the page itself, so the dewarp moved nothing."""
  return quad.top_left == _Point(x=0, y=0) and quad.bottom_right == _Point(
    x=geometry.image_width, y=geometry.image_height
  )


def _scan_page(scan_path: pathlib.Path, page: int) -> Image.Image:
  """The page of an archived scan a record was read from."""
  decoded = decode_scan(scan_path).value[page - 1]
  if not isinstance(decoded, DecodedScan):
    raise _MigrationError(
      f'{scan_path} page {page} no longer decodes: {decoded}'
    )
  return decoded.image


def _remeasured(
  scan: Image.Image, geometry: SheetGeometry, quad: _Quad
) -> SheetGeometry:
  """The record's grid found again in the scan's own pixels."""
  coefficients = _perspective_coefficients(
    quad, geometry.image_width, geometry.image_height
  )
  lefts = {box.left for box in geometry.row_boxes}
  rights = {box.right for box in geometry.row_boxes}
  if len(lefts) != 1 or len(rights) != 1:
    raise _MigrationError(
      f'its rows start at {len(lefts)} different left edges, so it holds more '
      'than one panel; only single-panel records are migrated'
    )
  grid = Box(
    left=lefts.pop(),
    top=geometry.row_boxes[0].top,
    right=rights.pop(),
    bottom=geometry.row_boxes[-1].bottom,
  )
  panel = BoardPanel(
    board_row_count=len(geometry.row_boxes),
    grid=_onto_scan(coefficients, grid, scan),
  )
  footer = (
    _onto_scan(coefficients, geometry.footer, scan) if geometry.footer else None
  )
  return resolve_sheet_geometry(scan, [panel], footer)


def _describe_remeasure(
  old: SheetGeometry, new: SheetGeometry, quad: _Quad
) -> str:
  """How far the re-measured rows sit from the record's.

  Raises:
    _MigrationError: a row moved far enough to be a different row.
  """
  coefficients = _perspective_coefficients(
    quad, old.image_width, old.image_height
  )
  pitch = new.row_pitch()
  shifts = []
  for old_box, new_box in zip(old.row_boxes, new.row_boxes, strict=True):
    _, old_center = _to_scan(
      coefficients,
      (old_box.left + old_box.right) / 2,
      (old_box.top + old_box.bottom) / 2,
    )
    new_center = (new_box.top + new_box.bottom) / 2
    shifts.append(abs(old_center - new_center) / pitch)
  if max(shifts) >= _MAXIMUM_ROW_SHIFT_IN_PITCHES:
    raise _MigrationError(
      f'a re-measured row moved {max(shifts):.2f} of a pitch, enough to be a '
      'different row'
    )
  return (
    f're-measured, {len(new.row_boxes)} rows, centers moved at most '
    f'{max(shifts):.2f} of a pitch (median {statistics.median(shifts):.2f})'
  )


def _onto_scan(
  coefficients: Sequence[float], box: Box, scan: Image.Image
) -> Box:
  """A dewarped-frame box mapped onto the scan, clamped to it.

  Mapped by its edges' midpoints rather than its corners. Where the dewarp
  tilted the frame, a box around the mapped corners is taller than the rows by
  the tilt — loose enough that geometry cannot tell which run of rules was
  meant.
  """
  x_middle = (box.left + box.right) / 2
  y_middle = (box.top + box.bottom) / 2
  _, top = _to_scan(coefficients, x_middle, box.top)
  _, bottom = _to_scan(coefficients, x_middle, box.bottom)
  left, _ = _to_scan(coefficients, box.left, y_middle)
  right, _ = _to_scan(coefficients, box.right, y_middle)
  return Box(
    left=max(0, round(left)),
    top=max(0, round(top)),
    right=min(scan.width, round(right)),
    bottom=min(scan.height, round(bottom)),
  )


def _to_scan(
  coefficients: Sequence[float], x: float, y: float
) -> tuple[float, float]:
  """Where a dewarped-frame point came from in the scan."""
  a, b, c, d, e, f, g, h = coefficients
  denominator = g * x + h * y + 1
  return (a * x + b * y + c) / denominator, (d * x + e * y + f) / denominator


def _perspective_coefficients(
  quad: _Quad, width: int, height: int
) -> Sequence[float]:
  """The transform the dewarp sampled the scan by, mapping its frame onto the
  quad.

  The eight coefficients follow from requiring the frame's four corners to land
  on the quad's, which is how the dewarp derived them.
  """
  corners = [
    ((0.0, 0.0), quad.top_left),
    ((0.0, float(height)), quad.bottom_left),
    ((float(width), float(height)), quad.bottom_right),
    ((float(width), 0.0), quad.top_right),
  ]
  matrix: list[list[float]] = []
  right_hand_side: list[float] = []
  for (out_x, out_y), source in corners:
    source_x, source_y = source.x, source.y
    matrix.append(
      [out_x, out_y, 1, 0, 0, 0, -out_x * source_x, -out_y * source_x]
    )
    right_hand_side.append(source_x)
    matrix.append(
      [0, 0, 0, out_x, out_y, 1, -out_x * source_y, -out_y * source_y]
    )
    right_hand_side.append(source_y)
  return _solve_linear_system(matrix, right_hand_side)


def _solve_linear_system(
  matrix: Sequence[Sequence[float]], right_hand_side: Sequence[float]
) -> list[float]:
  """Solve `matrix @ solution = right_hand_side`, with partial pivoting."""
  size = len(right_hand_side)
  rows = [
    [*row, value] for row, value in zip(matrix, right_hand_side, strict=True)
  ]
  for column in range(size):
    pivot_row = max(
      range(column, size), key=lambda row_index: abs(rows[row_index][column])
    )
    rows[column], rows[pivot_row] = rows[pivot_row], rows[column]
    pivot = rows[column][column]
    for row_index in range(column + 1, size):
      factor = rows[row_index][column] / pivot
      for other_column in range(column, size + 1):
        rows[row_index][other_column] -= factor * rows[column][other_column]

  solution = [0.0] * size
  for column in reversed(range(size)):
    accumulated = sum(
      rows[column][later] * solution[later] for later in range(column + 1, size)
    )
    solution[column] = (rows[column][size] - accumulated) / rows[column][column]
  return solution


if __name__ == '__main__':
  main()
