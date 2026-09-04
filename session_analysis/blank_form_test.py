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

These cover the measuring half of geometry — `rule_grid` resolving printed rules
on real, noisy imagery — so the reading half is supplied as a literal panel
standing in for what `sheet_structure` reports. Its bounds are deliberately a
few pixels off the true rules, as a real reading's are, to show that they only
choose which rules are the grid rather than contributing a coordinate.
"""

import pathlib
import random

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from session_analysis.sheet_dewarp import dewarp_sheet
from session_analysis.unreviewed.sheet_geometry import (
  BoardPanel,
  Box,
  resolve_sheet_geometry,
)

_FIXTURE = (
  pathlib.Path(__file__).parent / 'testdata' / 'blank_scoresheet_v4.png'
)


def _reading() -> BoardPanel:
  """The v4 form's 28 board rows, as a reading of the sheet reports them.

  The bounds sit a few pixels inside the true rules — 6px below the first and
  6px above the last — since a real reading's are approximate. The row count is
  exact, which is what it is trusted for.
  """
  return BoardPanel(
    board_row_count=28,
    grid=Box(left=26, top=111, right=1174, bottom=1176),
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

  geometry = resolve_sheet_geometry(dewarped.image, [_reading()])

  # In the dewarped frame the form's board rows run from y=105 to y=1182, which
  # the reported 111..1176 snap out to. A header row and a scale chart sit above
  # them, chaining in at nearly the grid's own pitch, so landing on 105 is a
  # statement about which run of rules was chosen.
  assert geometry.row_boxes[0].top == 105
  assert geometry.row_boxes[-1].bottom == 1182


def test_a_degraded_capture_still_resolves_the_board_grid() -> None:
  degraded = _degrade(Image.open(_FIXTURE))

  dewarped = dewarp_sheet(degraded)
  geometry = resolve_sheet_geometry(dewarped.image, [_reading()])

  # The same y=105 the clean render resolves to, through a 1.5-degree rotation,
  # a vignette and a blur.
  assert geometry.row_boxes[0].top == 105


def test_the_footer_guide_underline_is_never_taken_for_a_board_row() -> None:
  # The underline runs nearly the full width one pitch below the grid, so ink
  # coverage cannot tell it from a rule. Taking it for one is what used to push
  # the footer region onto blank paper and lose the sheet's event and date.
  dewarped = dewarp_sheet(Image.open(_FIXTURE))

  geometry = resolve_sheet_geometry(dewarped.image, [_reading()])

  # The underline sits at y=1219, a pitch below the last board rule at 1182.
  assert geometry.row_boxes[-1].bottom < 1219
