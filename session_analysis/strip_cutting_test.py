# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for strip_cutting.

Cutting is tested against hand-built `SheetGeometry` values, so every expected
crop bound is visible in the test.
"""

import io

from PIL import Image

from session_analysis.sheet_geometry import Box, SheetGeometry
from session_analysis.strip_cutting import cut_strips

# Three tight 20px rows on a 100x200 page.
_GEOMETRY = SheetGeometry(
  image_width=100,
  image_height=200,
  row_boxes=(
    Box(left=10, top=50, right=90, bottom=70),
    Box(left=10, top=70, right=90, bottom=90),
    Box(left=10, top=90, right=90, bottom=110),
  ),
)


def _decode(image_bytes: bytes) -> Image.Image:
  return Image.open(io.BytesIO(image_bytes))


def test_cuts_one_labeled_strip_per_row_plus_the_footer() -> None:
  image = Image.new('RGB', (100, 200), color='white')

  parts = cut_strips(image, _GEOMETRY)

  assert [part.label for part in parts] == [
    'Strip for printed row 1:',
    'Strip for printed row 2:',
    'Strip for printed row 3:',
    'Strip for the footer:',
  ]
  assert all(part.media_type == 'image/jpeg' for part in parts)
  assert all(_decode(part.image_bytes).format == 'JPEG' for part in parts)


def test_row_strips_are_padded_into_their_neighbors() -> None:
  image = Image.new('RGB', (100, 200), color='white')

  parts = cut_strips(image, _GEOMETRY)

  # 0.3 of the 20px row pitch, i.e. 6px, added above and below the tight 20px
  # row box.
  assert _decode(parts[0].image_bytes).size == (80, 32)


def test_strip_padding_clamps_at_the_image_edges() -> None:
  image = Image.new('RGB', (100, 24), color='white')
  geometry = SheetGeometry(
    image_width=100,
    image_height=24,
    row_boxes=(Box(left=10, top=2, right=90, bottom=22),),
  )

  parts = cut_strips(image, geometry)

  # 6px of padding would reach y=-4 and y=28; both clamp to the image.
  assert _decode(parts[0].image_bytes).size == (80, 24)


def test_the_footer_strip_is_cut_unpadded() -> None:
  image = Image.new('RGB', (100, 200), color='white')

  parts = cut_strips(image, _GEOMETRY)

  # The derived footer box: 2.5 pitches (50px) below the bottom rule at 110.
  assert _decode(parts[-1].image_bytes).size == (80, 50)
