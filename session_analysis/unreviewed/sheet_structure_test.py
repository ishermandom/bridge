# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for sheet_structure.

The reading is scripted rather than asked for, so what these cover is the two
things the module does around the model call: sending the sheet at exactly the
size the model sees it at, and returning what comes back to the sheet's own
pixel space.
"""

import json

import pytest
from PIL import Image

from session_analysis.testing.scripted_model import ScriptedModelRunner
from session_analysis.unreviewed.sheet_structure import (
  SheetStructureError,
  image_for_model,
  read_sheet_structure,
)


def _reply(
  *,
  panels: list[dict[str, object]] | None = None,
  footer: dict[str, int] | None = None,
  notes: str = '',
) -> str:
  """One scripted reading, in the wire shape the schema asks for.

  `panels` distinguishes an empty list from an absent one: a reading claiming no
  panels at all is a case worth scripting.
  """
  if panels is None:
    panels = [
      {
        'board_row_count': 28,
        'grid': {'left': 40, 'top': 100, 'right': 560, 'bottom': 660},
      }
    ]
  return json.dumps(
    {
      'panels': panels,
      'footer': footer,
      'notes': notes,
    }
  )


# --- sending the sheet at the size the model sees ---


def test_an_image_within_the_limits_is_sent_unscaled() -> None:
  # 600x800 costs 22x29 = 638 visual tokens, well inside the budget.
  sent, scale = image_for_model(Image.new('L', (600, 800)))

  assert sent.size == (600, 800)
  assert scale == 1.0


def test_an_oversized_image_is_scaled_to_the_visual_token_budget() -> None:
  # A 4K frame: both edges are inside the 2576px limit only after the 4784-token
  # budget has already forced a scale, which is the case that binds for every
  # page-shaped image.
  sent, scale = image_for_model(Image.new('L', (3840, 2160)))

  assert sent.size == (2576, 1449)
  assert scale == pytest.approx(2576 / 3840)


# --- returning the reading to the sheet's own space ---


def test_a_reading_of_an_unscaled_sheet_is_returned_as_given() -> None:
  with ScriptedModelRunner([_reply()]) as runner:
    structure = read_sheet_structure(
      Image.new('L', (600, 800)), run_command=runner
    )

  assert len(structure.panels) == 1
  assert structure.panels[0].board_row_count == 28
  assert structure.panels[0].grid.top == 100
  assert structure.panels[0].grid.bottom == 660


def test_a_reading_of_a_scaled_sheet_is_divided_back_by_the_scale() -> None:
  # The model reads a half-size copy, so a rule it reports at y=100 is at y=200
  # on the sheet itself. Getting this wrong shifts every row box.
  sheet = Image.new('L', (3840, 2160))
  scale = image_for_model(sheet)[1]

  with ScriptedModelRunner([_reply()]) as runner:
    structure = read_sheet_structure(sheet, run_command=runner)

  assert structure.panels[0].grid.top == round(100 / scale)
  assert structure.panels[0].grid.bottom == round(660 / scale)


def test_a_sheet_with_no_footer_reads_as_none() -> None:
  # Several vendor forms print conversion charts below the table and no footer
  # at all, so its absence is an ordinary answer rather than a failure.
  with ScriptedModelRunner([_reply(footer=None)]) as runner:
    structure = read_sheet_structure(
      Image.new('L', (600, 800)), run_command=runner
    )

  assert structure.footer is None


def test_a_footer_is_read_when_the_form_prints_one() -> None:
  with ScriptedModelRunner(
    [_reply(footer={'left': 40, 'top': 660, 'right': 560, 'bottom': 710})]
  ) as runner:
    structure = read_sheet_structure(
      Image.new('L', (600, 800)), run_command=runner
    )

  assert structure.footer
  assert structure.footer.top == 660


def test_side_by_side_panels_are_read_in_order() -> None:
  # A vendor form printing boards down two columns, the left one shortened by a
  # chart beneath it — so the panels differ in row count as well as position.
  with ScriptedModelRunner(
    [
      _reply(
        panels=[
          {
            'board_row_count': 16,
            'grid': {'left': 40, 'top': 100, 'right': 280, 'bottom': 420},
          },
          {
            'board_row_count': 20,
            'grid': {'left': 320, 'top': 100, 'right': 560, 'bottom': 500},
          },
        ]
      )
    ]
  ) as runner:
    structure = read_sheet_structure(
      Image.new('L', (600, 800)), run_command=runner
    )

  assert [panel.board_row_count for panel in structure.panels] == [16, 20]
  assert [panel.grid.left for panel in structure.panels] == [40, 320]


def test_the_model_notes_are_carried_for_a_person_to_read() -> None:
  with ScriptedModelRunner(
    [_reply(notes='the SAMPLE overprint hides the middle rules')]
  ) as runner:
    structure = read_sheet_structure(
      Image.new('L', (600, 800)), run_command=runner
    )

  assert 'SAMPLE' in structure.notes


# --- a reading that cannot be used ---


def test_a_reply_that_is_not_a_sheet_structure_is_refused() -> None:
  with (
    ScriptedModelRunner(['{"rows": 28}']) as runner,
    pytest.raises(SheetStructureError, match='did not parse'),
  ):
    read_sheet_structure(Image.new('L', (600, 800)), run_command=runner)


def test_a_footer_flush_with_the_page_edge_is_accepted() -> None:
  # The ordinary answer for a band at the bottom of the sheet, and a pixel or
  # two beyond it is the ordinary rounding. `sheet_geometry` clamps both;
  # refusing them here would lose a whole sheet to a rounding.
  with ScriptedModelRunner(
    [_reply(footer={'left': 0, 'top': 760, 'right': 600, 'bottom': 803})]
  ) as runner:
    structure = read_sheet_structure(
      Image.new('L', (600, 800)), run_command=runner
    )

  assert structure.footer
  assert structure.footer.bottom == 803


def test_a_reading_placed_outside_the_image_is_refused() -> None:
  # The whole coordinate contract is that the image sent is the image read. A
  # box outside it means the model scaled the image again, so every coordinate
  # is in a space this module cannot convert from — which would otherwise
  # surface far away, as rules resolving to the wrong rows.
  with (
    ScriptedModelRunner(
      [
        _reply(
          panels=[
            {
              'board_row_count': 28,
              'grid': {'left': 40, 'top': 100, 'right': 1400, 'bottom': 660},
            }
          ]
        )
      ]
    ) as runner,
    pytest.raises(SheetStructureError, match='outside the 600x800'),
  ):
    read_sheet_structure(Image.new('L', (600, 800)), run_command=runner)


def test_a_reply_claiming_no_panels_is_refused() -> None:
  # Every sheet this pipeline reads has board rows somewhere; none at all means
  # the reading is of something else.
  with (
    ScriptedModelRunner([_reply(panels=[])]) as runner,
    pytest.raises(SheetStructureError, match='did not parse'),
  ):
    read_sheet_structure(Image.new('L', (600, 800)), run_command=runner)


def test_a_panel_claiming_no_rows_is_refused() -> None:
  with (
    ScriptedModelRunner(
      [
        _reply(
          panels=[
            {
              'board_row_count': 0,
              'grid': {'left': 40, 'top': 100, 'right': 560, 'bottom': 660},
            }
          ]
        )
      ]
    ) as runner,
    pytest.raises(SheetStructureError, match='did not parse'),
  ):
    read_sheet_structure(Image.new('L', (600, 800)), run_command=runner)
