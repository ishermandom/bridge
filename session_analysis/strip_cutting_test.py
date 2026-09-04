# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for strip_cutting.

Cutting is tested against hand-built `SheetGeometry` values, so every expected
crop bound is visible in the test.
"""

import io

from PIL import Image

from session_analysis.strip_cutting import cut_strips
from session_analysis.unreviewed.sheet_geometry import Box, SheetGeometry

# Three tight 20px rows on a 100x200 page, with a 50px footer band below them.
_GEOMETRY = SheetGeometry(
  image_width=100,
  image_height=200,
  row_boxes=(
    Box(left=10, top=50, right=90, bottom=70),
    Box(left=10, top=70, right=90, bottom=90),
    Box(left=10, top=90, right=90, bottom=110),
  ),
  footer=Box(left=10, top=110, right=90, bottom=160),
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


def test_the_footer_strip_is_padded_like_a_row() -> None:
  # The footer band is read off the sheet rather than derived with a margin of
  # its own, so it can hug the printed guide underlines that ascenders cross —
  # and it is the only place the session key comes from.
  image = Image.new('RGB', (100, 200), color='white')

  parts = cut_strips(image, _GEOMETRY)

  # The footer box as given, 110..160, plus 6px of padding at each end.
  assert _decode(parts[-1].image_bytes).size == (80, 62)


def test_a_sheet_with_no_footer_contributes_no_footer_strip() -> None:
  # Several vendor forms print conversion charts below the table and no footer
  # at all; cutting one anyway would hand the model a chart to read an event
  # and date out of.
  image = Image.new('RGB', (100, 200), color='white')
  geometry = SheetGeometry(
    image_width=100,
    image_height=200,
    row_boxes=(Box(left=10, top=50, right=90, bottom=70),),
  )

  parts = cut_strips(image, geometry)

  assert [part.label for part in parts] == ['Strip for printed row 1:']
