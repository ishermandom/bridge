# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Geometry tests against a real scoresheet: the v4 form in day-to-day use.

The fixture is the blank v4 scoresheet, rendered from the sibling
bridge-scoresheets repo's `latest.pdf`: rasterized at 300dpi (`sips -s format
png --resampleWidth 2550`), alpha-composited onto white (the PDF's background is
transparent), rotated 90 degrees counterclockwise to upright (page 1 prints
rotated), grayscaled, and halved to keep the file small. Unlike the drawn grids
in the sibling tests, it carries everything the real form does: scale charts
above the grid, a board-height header row, round-break rules, row shading, and
footer guide underlines.

Both tests expect 29 rows: the 28 board rows plus the printed header row, which
sits at board pitch on this form and is deliberately kept — the transcription
prompt drops its strip from the output instead. The chart rows above the grid
are trimmed by ink coverage.
"""

import pathlib
import random

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from session_analysis.sheet_dewarp import dewarp_sheet
from session_analysis.sheet_geometry import detect_sheet_geometry

_FIXTURE = (
  pathlib.Path(__file__).parent / 'testdata' / 'blank_scoresheet_v4.png'
)


def _degrade(image: Image.Image) -> Image.Image:
  """A rough phone capture: scribbles, slight rotation, uneven light, blur."""
  rng = random.Random(7)
  scribbled = image.copy()
  draw = ImageDraw.Draw(scribbled)
  # Handwriting-like polylines scattered over the grid area.
  for _ in range(60):
    x = rng.randrange(80, image.width - 250)
    y = rng.randrange(200, image.height - 150)
    points = [(x, y)]
    for _ in range(3):
      points.append(
        (
          points[-1][0] + rng.randrange(10, 60),
          points[-1][1] + rng.randrange(-8, 9),
        )
      )
    draw.line(points, fill=60, width=2)
  rotated = scribbled.rotate(
    1.5, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=255
  )
  # Light falls off toward one edge, as under a ceiling lamp.
  vignette = (
    Image.linear_gradient('L')
    .resize(rotated.size)
    .point(lambda value: 205 + value * 50 // 255)
  )
  dimmed = ImageChops.multiply(rotated, vignette)
  return dimmed.filter(ImageFilter.GaussianBlur(0.5))


def test_the_clean_render_resolves_the_board_grid() -> None:
  dewarped = dewarp_sheet(Image.open(_FIXTURE))

  geometry = detect_sheet_geometry(dewarped.image)

  # 28 board rows plus the header row (see the module docstring).
  assert len(geometry.row_boxes) == 29


def test_a_degraded_capture_still_resolves_the_board_grid() -> None:
  degraded = _degrade(Image.open(_FIXTURE))

  dewarped = dewarp_sheet(degraded)
  geometry = detect_sheet_geometry(dewarped.image)

  assert len(geometry.row_boxes) == 29
