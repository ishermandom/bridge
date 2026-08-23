# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Synthetic scoresheet scans, drawn with PIL for the image-pipeline tests.

Every test that needs a scan draws one here rather than reading a committed
image fixture: real scans carry member handwriting, and a drawn grid pins the
expected rule positions exactly.
"""

from collections.abc import Sequence

from PIL import Image, ImageDraw

# The horizontal extent of the drawn grid, inset from the page's own edges the
# way a printed sheet's margins inset it.
GRID_LEFT = 40
GRID_RIGHT = 560

# The grid a caller gets when it has no opinion about the geometry: 25 rules
# bounding 24 board rows at a 24px pitch.
#
# Its count, pitch and offset are all deliberately unlike the ones the tests
# spell out for themselves, so that a test whose assertions or extra drawn lines
# turn on where the rules sit cannot quietly pass while taking this default. It
# should pass its own rules, keeping those positions beside the assertions that
# depend on them.
_DEFAULT_RULE_YS = tuple(range(80, 657, 24))


def draw_sheet(
  rule_ys: Sequence[int] = _DEFAULT_RULE_YS,
  *,
  width: int = 600,
  height: int = 800,
) -> Image.Image:
  """A synthetic scan: horizontal rules at `rule_ys` inside vertical edges."""
  image = Image.new('L', (width, height), color=255)
  draw = ImageDraw.Draw(image)
  for rule_y in rule_ys:
    draw.line([(GRID_LEFT, rule_y), (GRID_RIGHT, rule_y)], fill=0)
  for border_x in (GRID_LEFT, GRID_RIGHT):
    draw.line([(border_x, rule_ys[0]), (border_x, rule_ys[-1])], fill=0)
  return image
