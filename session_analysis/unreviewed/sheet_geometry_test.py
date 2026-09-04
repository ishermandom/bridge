# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for sheet_geometry.

The module resolves a reading of a sheet's layout against its printed rules, so
these tests vary the two independently: a reported extent that drifts, a
reported row count that does not match the pixels, and a sheet whose rows come
in more than one panel.
"""

import pydantic
import pytest
from PIL import Image, ImageDraw

from session_analysis.rule_grid import SheetGeometryError
from session_analysis.testing.synthetic_scans import draw_sheet
from session_analysis.unreviewed.sheet_geometry import (
  BoardPanel,
  Box,
  SheetGeometry,
  resolve_sheet_geometry,
)


def _panel(
  row_count: int, *, top: int, bottom: int, left: int, right: int
) -> BoardPanel:
  """A reading of a drawn sheet's rows, as the model would report one."""
  return BoardPanel(
    board_row_count=row_count,
    grid=Box(left=left, top=top, right=right, bottom=bottom),
  )


# --- resolving rules against a reading ---


def test_resolves_tight_rule_to_rule_row_boxes() -> None:
  # 29 rules at a 20px pitch bounding 28 board rows, drawn between x=40 and
  # x=560 on a 600x800 page.
  image = draw_sheet(range(100, 661, 20))

  geometry = resolve_sheet_geometry(
    image, [_panel(28, top=100, bottom=660, left=40, right=560)]
  )

  assert geometry.row_boxes[0] == Box(left=40, top=100, right=560, bottom=120)
  assert geometry.row_boxes[-1] == Box(left=40, top=640, right=560, bottom=660)
  assert geometry.image_width == 600
  assert geometry.image_height == 800


def test_a_drifting_reported_extent_still_lands_on_the_printed_rules() -> None:
  # The reported bounds are approximate — measured drift is about a quarter of a
  # row pitch — so they choose which rules are the grid without contributing a
  # coordinate to the answer. Reported 6px below the first rule and 7px above
  # the last; both answers come back on the rules themselves.
  image = draw_sheet(range(100, 661, 20))

  geometry = resolve_sheet_geometry(
    image, [_panel(28, top=106, bottom=653, left=40, right=560)]
  )

  assert geometry.row_boxes[0].top == 100
  assert geometry.row_boxes[-1].bottom == 660


def test_rules_beyond_the_reported_extent_are_left_out() -> None:
  # A chart printed above the grid and a footer guide underline below it both
  # chain in at the grid's pitch. Neither is inside the reported extent, so
  # neither becomes a row — which the old ink-coverage trim got wrong on real
  # scans.
  image = draw_sheet(range(100, 661, 20))
  draw = ImageDraw.Draw(image)
  for stray_y in (60, 80, 680):
    draw.line([(40, stray_y), (560, stray_y)], fill=0)

  geometry = resolve_sheet_geometry(
    image, [_panel(28, top=100, bottom=660, left=40, right=560)]
  )

  # The strays would move one end or the other had they been chained in.
  assert geometry.row_boxes[0].top == 100
  assert geometry.row_boxes[-1].bottom == 660


def test_a_row_count_the_pixels_do_not_support_raises() -> None:
  # The count is taken as exact, so a reading that claims 40 rows where 28 are
  # drawn is a disagreement between the two readings rather than something to
  # approximate around.
  image = draw_sheet(range(100, 661, 20))

  with pytest.raises(SheetGeometryError, match='40'):
    resolve_sheet_geometry(
      image, [_panel(40, top=100, bottom=660, left=40, right=560)]
    )


def test_a_panel_without_vertical_border_rules_uses_the_reported_span() -> None:
  # A form printing no vertical rules is less information, not a different kind
  # of failure — the same answer a single faded border gets. Drawn without the
  # borders `draw_sheet` would add, so the reported 40 and 560 are all there is
  # to go on.
  image = Image.new('L', (600, 800), color=255)
  draw = ImageDraw.Draw(image)
  for rule_y in range(100, 661, 20):
    draw.line([(40, rule_y), (560, rule_y)], fill=0)

  geometry = resolve_sheet_geometry(
    image, [_panel(28, top=100, bottom=660, left=40, right=560)]
  )

  assert geometry.row_boxes[0].left == 40
  assert geometry.row_boxes[0].right == 560


def test_two_panels_keep_their_own_borders_across_a_narrow_gutter() -> None:
  # Panels 500px wide with an 8px gutter, the proportions of the Bridge Buddy
  # form. Reach is 10px here, so each panel's search really does see its
  # neighbour's border across the gutter — resolving by nearest is what keeps
  # them apart, where reaching for the outermost line has each panel swallow the
  # gutter and a slice of the other.
  image = Image.new('L', (1200, 800), color=255)
  draw = ImageDraw.Draw(image)
  for left, right in ((60, 560), (568, 1068)):
    for rule_y in range(100, 181, 20):
      draw.line([(left, rule_y), (right, rule_y)], fill=0)
    for border_x in (left, right):
      draw.line([(border_x, 100), (border_x, 180)], fill=0)

  # Reported 2px inside each panel's drawn borders, so an answer on 560 or 568
  # is one the printed lines gave rather than the reading being handed back.
  geometry = resolve_sheet_geometry(
    image,
    [
      _panel(4, top=100, bottom=180, left=62, right=558),
      _panel(4, top=100, bottom=180, left=570, right=1066),
    ],
  )

  assert geometry.row_boxes[0].right == 560
  assert geometry.row_boxes[4].left == 568


def test_a_footer_clamped_out_of_the_image_is_dropped() -> None:
  # A footer reported below the page clamps to no height, and cutting a strip
  # from it fails inside PIL's JPEG writer — where nothing on the ingest path
  # catches it, so the whole run would pay for it. The page is 800px tall; the
  # footer is reported from y=900 to y=950.
  geometry = resolve_sheet_geometry(
    draw_sheet(range(100, 661, 20)),
    [_panel(28, top=100, bottom=660, left=40, right=560)],
    Box(left=40, top=900, right=560, bottom=950),
  )

  assert geometry.footer is None


def test_slices_reading_two_different_runs_raise() -> None:
  # Half the sheet ruled a pitch below the other half — a torn or doubly exposed
  # scan. Each slice is individually certain, so a check on per-slice confidence
  # passes; taking the median of what they chose would land between the two
  # groups, putting every rule mid-row with the row count still agreeing and
  # nothing downstream noticing.
  image = Image.new('L', (600, 800), color=255)
  draw = ImageDraw.Draw(image)
  for rule_y in range(100, 301, 20):
    draw.line([(40, rule_y), (300, rule_y)], fill=0)
  for rule_y in range(120, 321, 20):
    draw.line([(300, rule_y), (560, rule_y)], fill=0)
  for border_x in (40, 560):
    draw.line([(border_x, 100), (border_x, 320)], fill=0)

  with pytest.raises(SheetGeometryError, match='not reading the same rows'):
    resolve_sheet_geometry(
      image, [_panel(10, top=110, bottom=310, left=40, right=560)]
    )


def test_bounds_falling_between_two_runs_of_rules_raise() -> None:
  # Half a pitch of drift puts the reported bounds between the true grid and the
  # same grid shifted a rule down, and the nearer run wins by rounding — which
  # starts every strip on the wrong board and reads the footer's guide underline
  # as the last one. The row count agrees either way, so nothing else is left to
  # catch it. Strays at the grid's own 20px pitch above and below it, so a run
  # of 29 rules also starts at y=80 and at y=120. Reported 112..672, half a
  # pitch below the true 100..660 and half a pitch above that shifted run.
  image = draw_sheet(range(100, 661, 20))
  draw = ImageDraw.Draw(image)
  for stray_y in (60, 80, 680, 700):
    draw.line([(40, stray_y), (560, stray_y)], fill=0)

  with pytest.raises(SheetGeometryError, match='between two runs'):
    resolve_sheet_geometry(
      image, [_panel(28, top=112, bottom=672, left=40, right=560)]
    )


def test_the_drift_a_real_reading_carries_is_not_read_as_ambiguous() -> None:
  # The same neighbouring runs the test above sets up, read with the drift a
  # real reading carries: 6px on a 20px pitch, about a percent of the page and
  # well inside what separates one run from the next — so the check above must
  # not fire on it.
  image = draw_sheet(range(100, 661, 20))
  draw = ImageDraw.Draw(image)
  for stray_y in (60, 80, 680, 700):
    draw.line([(40, stray_y), (560, stray_y)], fill=0)

  geometry = resolve_sheet_geometry(
    image, [_panel(28, top=106, bottom=654, left=40, right=560)]
  )

  assert geometry.row_boxes[0].top == 100
  assert geometry.row_boxes[-1].bottom == 660


def test_overlapping_panels_raise() -> None:
  # A reading that reports one block of rows twice would resolve both copies
  # against the same printed rules and transcribe every board twice — and
  # invisibly, since the strips double alongside the boards.
  with pytest.raises(SheetGeometryError, match='overlaps'):
    resolve_sheet_geometry(
      draw_sheet(range(100, 661, 20)),
      [
        _panel(28, top=100, bottom=660, left=40, right=560),
        _panel(28, top=100, bottom=660, left=40, right=560),
      ],
    )


def test_a_panel_reported_with_no_area_raises() -> None:
  # Both borders at one x. Caught before the rule search, whose complaint would
  # be about column slices and row counts and would hide what went wrong.
  with pytest.raises(SheetGeometryError, match='no area'):
    resolve_sheet_geometry(
      draw_sheet(range(100, 661, 20)),
      [_panel(28, top=100, bottom=660, left=300, right=300)],
    )


def test_a_panel_reported_off_the_frame_raises() -> None:
  with pytest.raises(SheetGeometryError, match='no area'):
    resolve_sheet_geometry(
      draw_sheet(range(100, 661, 20)),
      [_panel(28, top=100, bottom=660, left=900, right=1000)],
    )


def test_panels_are_read_left_to_right_however_they_are_reported() -> None:
  # The order is what puts `row_boxes` in the sheet's board order, and only the
  # prompt asks for it — a right-hand panel reported first would have every
  # strip labelled with the other panel's row number.
  image = Image.new('L', (600, 800), color=255)
  draw = ImageDraw.Draw(image)
  for left, right in ((40, 280), (320, 560)):
    for rule_y in range(100, 181, 20):
      draw.line([(left, rule_y), (right, rule_y)], fill=0)
    for border_x in (left, right):
      draw.line([(border_x, 100), (border_x, 180)], fill=0)

  geometry = resolve_sheet_geometry(
    image,
    [
      _panel(4, top=100, bottom=180, left=320, right=560),
      _panel(4, top=100, bottom=180, left=40, right=280),
    ],
  )

  assert geometry.row_boxes[0].left == 40
  assert geometry.row_boxes[4].left == 320


def test_a_box_whose_edges_cross_is_refused() -> None:
  # A `Box` also arrives from outside — a model reading parses into these — and
  # `Image.crop` answers an inverted one with a bare ValueError nothing catches.
  with pytest.raises(pydantic.ValidationError, match='edges cross'):
    Box(left=500, top=0, right=40, bottom=100)


def test_a_footer_reaching_past_the_image_is_clamped_to_it() -> None:
  # The footer is reported rather than measured, so nothing else keeps it in
  # frame; a strip cut past the edge is padded with black, which reads as ink.
  # The page is 800px tall; the footer is reported as reaching to y=5000.
  geometry = resolve_sheet_geometry(
    draw_sheet(range(100, 661, 20)),
    [_panel(28, top=100, bottom=660, left=40, right=560)],
    Box(left=40, top=660, right=560, bottom=5000),
  )

  assert geometry.footer
  assert geometry.footer.bottom == 800


def test_a_margin_outside_the_table_is_not_taken_for_its_border() -> None:
  # Several forms carry a punched margin down the left of the page. It is the
  # outermost vertical line but not the table's border, and the reported border
  # is what tells the two apart. Drawn 6px out, inside the 10px reach, so the
  # border wins on nearness rather than the margin simply being out of range.
  # The table's left border is drawn at x=40 and the margin at x=34.
  image = draw_sheet(range(100, 661, 20))
  ImageDraw.Draw(image).line([(34, 100), (34, 660)], fill=0)

  geometry = resolve_sheet_geometry(
    image, [_panel(28, top=100, bottom=660, left=40, right=560)]
  )

  assert geometry.row_boxes[0].left == 40


# --- sheets whose rows come in more than one panel ---


def test_two_panels_contribute_their_rows_in_reading_order() -> None:
  # A vendor form printing boards 1-3 down the left and 4-9 down the right, the
  # right panel running lower because no chart sits beneath it.
  image = Image.new('L', (600, 800), color=255)
  draw = ImageDraw.Draw(image)
  for rule_y in range(100, 181, 20):
    draw.line([(40, rule_y), (280, rule_y)], fill=0)
  for border_x in (40, 280):
    draw.line([(border_x, 100), (border_x, 180)], fill=0)
  for rule_y in range(100, 241, 20):
    draw.line([(320, rule_y), (560, rule_y)], fill=0)
  for border_x in (320, 560):
    draw.line([(border_x, 100), (border_x, 240)], fill=0)

  geometry = resolve_sheet_geometry(
    image,
    [
      _panel(4, top=100, bottom=180, left=40, right=280),
      _panel(7, top=100, bottom=240, left=320, right=560),
    ],
  )

  assert geometry.row_boxes[0] == Box(left=40, top=100, right=280, bottom=120)
  assert geometry.row_boxes[3].bottom == 180
  assert geometry.row_boxes[4] == Box(left=320, top=100, right=560, bottom=120)
  assert geometry.row_boxes[-1].bottom == 240


# --- the footer ---


def test_the_footer_is_carried_through_as_given() -> None:
  footer = Box(left=40, top=660, right=560, bottom=710)

  geometry = resolve_sheet_geometry(
    draw_sheet(range(100, 661, 20)),
    [_panel(28, top=100, bottom=660, left=40, right=560)],
    footer,
  )

  assert geometry.footer == footer


def test_a_sheet_with_no_footer_carries_none() -> None:
  geometry = resolve_sheet_geometry(
    draw_sheet(range(100, 661, 20)),
    [_panel(28, top=100, bottom=660, left=40, right=560)],
  )

  assert geometry.footer is None


# --- SheetGeometry.row_pitch ---


def test_row_pitch_is_the_median_tight_row_height() -> None:
  geometry = SheetGeometry(
    image_width=100,
    image_height=100,
    row_boxes=(
      Box(left=0, top=0, right=100, bottom=18),
      Box(left=0, top=18, right=100, bottom=38),
      Box(left=0, top=38, right=100, bottom=61),
    ),
  )

  assert geometry.row_pitch() == 20
