# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for extraction.

`transcribe_sheet` is tested end to end on a synthetic drawn grid with a
scripted `run_command` fake — no real `claude` process, mirroring the
vision_model_invocation tests. The fake answers three calls per sheet: the
layout reading first, then the two transcription runs that assembly votes
between.
"""

import json
from collections.abc import Sequence

import pytest

from session_analysis.extraction import transcribe_sheet
from session_analysis.testing.scripted_model import ScriptedModelRunner
from session_analysis.testing.synthetic_scans import draw_sheet

# The grid a test with no opinion about the geometry draws. Only its row count
# is depended on: no assertion here turns on where these rules sit.
_TWENTY_FOUR_ROWS = list(range(80, 657, 24))


def _reading(rule_ys: Sequence[int], row_count: int, *, footer: bool) -> str:
  """A scripted layout reading of a drawn sheet, as the model returns one.

  A real reading names roughly where the rows are; this one names the drawn
  first and last rules exactly, since the scan is read as drawn.
  """
  sheet = draw_sheet(rule_ys)
  return json.dumps(
    {
      'panels': [
        {
          'board_row_count': row_count,
          'grid': {
            'left': 0,
            'top': rule_ys[0],
            'right': sheet.width,
            'bottom': rule_ys[-1],
          },
        }
      ],
      'footer': {
        'left': 0,
        'top': sheet.height - 50,
        'right': sheet.width,
        'bottom': sheet.height,
      }
      if footer
      else None,
      'notes': '',
    }
  )


@pytest.mark.slow
def test_transcribe_sheet_returns_both_runs_raw_json() -> None:
  with ScriptedModelRunner(
    [
      _reading(_TWENTY_FOUR_ROWS, 24, footer=False),
      '{"sheet": {"boards": []}}',
      '{"sheet": {"boards": [{}]}}',
    ]
  ) as runner:
    transcription = transcribe_sheet(
      draw_sheet(_TWENTY_FOUR_ROWS), run_command=runner
    )

  assert transcription.raw_jsons == (
    '{"sheet": {"boards": []}}',
    '{"sheet": {"boards": [{}]}}',
  )


@pytest.mark.slow
def test_transcribe_sheet_returns_the_resolved_geometry() -> None:
  # 29 rules at a 20px pitch bounding 28 board rows, drawn from y=100 between
  # x=40 and x=560.
  rule_ys = range(100, 661, 20)

  with ScriptedModelRunner(
    [_reading(rule_ys, 28, footer=False), '{}', '{}']
  ) as runner:
    transcription = transcribe_sheet(draw_sheet(rule_ys), run_command=runner)

  # The reading's 28 reached the geometry. The assertion is not circular: a
  # count mis-parsed as 27 would still have resolved against these rules, and
  # come back as 27 boxes.
  assert len(transcription.geometry.row_boxes) == 28
  # In the scan's own pixels: the first row starts at the drawn first rule.
  assert transcription.geometry.row_boxes[0].top == 100


@pytest.mark.slow
def test_transcribe_sheet_reads_the_same_strips_both_times() -> None:
  with ScriptedModelRunner(
    [_reading(_TWENTY_FOUR_ROWS, 24, footer=False), '{}', '{}']
  ) as runner:
    transcribe_sheet(draw_sheet(_TWENTY_FOUR_ROWS), run_command=runner)

  # Three requests: the layout reading, then the two transcription runs, which
  # must be byte-identical for the vote to mean anything.
  assert len(runner.stdin_texts) == 3
  assert runner.stdin_texts[1] == runner.stdin_texts[2]


@pytest.mark.slow
def test_transcribe_sheet_sends_labeled_strips_for_every_row() -> None:
  # 29 rules bounding 28 board rows; the reading reports a footer besides.
  rule_ys = range(100, 661, 20)

  with ScriptedModelRunner(
    [_reading(rule_ys, 28, footer=True), '{}', '{}']
  ) as runner:
    transcribe_sheet(draw_sheet(rule_ys), run_command=runner)

  content = json.loads(runner.stdin_texts[1])['message']['content']
  # 29 label/image pairs (28 rows + footer) and the final instruction.
  assert len(content) == 59
  assert content[0] == {'type': 'text', 'text': 'Strip for printed row 1:'}
  # The footer's label is what the prompt tells the model to go by — without a
  # strip named this way the model leaves the event and date empty — so the
  # wording is load-bearing rather than cosmetic.
  assert content[-3] == {'type': 'text', 'text': 'Strip for the footer:'}
  assert content[-1] == {
    'type': 'text',
    'text': 'Transcribe the attached scan.',
  }


@pytest.mark.slow
def test_the_layout_reading_is_sent_as_one_whole_page() -> None:
  # The reading is a judgement about the form, so it gets the sheet entire — the
  # strips it decides the bounds of cannot be cut until it comes back.
  rule_ys = range(100, 661, 20)

  with ScriptedModelRunner(
    [_reading(rule_ys, 28, footer=False), '{}', '{}']
  ) as runner:
    transcribe_sheet(draw_sheet(rule_ys), run_command=runner)

  content = json.loads(runner.stdin_texts[0])['message']['content']
  # One label/image pair and the instruction.
  assert len(content) == 3
  assert content[0] == {'type': 'text', 'text': 'Scoresheet:'}
