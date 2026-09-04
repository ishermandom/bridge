# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for extraction.

`transcribe_sheet` is tested end to end on a synthetic drawn grid with a
scripted `run_command` fake — no real `claude` process, mirroring the
vision_model_invocation tests. The fake answers three calls per sheet: the
layout reading first, then the two transcription runs it voted between.
"""

import json
import statistics
from collections.abc import Sequence

from PIL import Image

from session_analysis.extraction import transcribe_sheet
from session_analysis.rule_grid import resolve_grid_consensus
from session_analysis.sheet_dewarp import dewarp_sheet
from session_analysis.testing.scripted_model import ScriptedModelRunner
from session_analysis.testing.synthetic_scans import draw_sheet

# The grid a test with no opinion about the geometry draws. Only its row count
# is depended on: no assertion here turns on where these rules sit.
_TWENTY_FOUR_ROWS = list(range(80, 657, 24))


def _frame_bounds(rule_ys: Sequence[int]) -> tuple[Image.Image, int, int]:
  """The dewarped frame of a drawn sheet, and where its grid sits in it.

  A scripted reading has to name roughly where the rows are, as a real one does
  — the dewarp adds margins, so the drawn `rule_ys` are not those positions. The
  drawn sheet carries nothing but its own rules, so the slice consensus over the
  dewarped frame is the grid.
  """
  frame = dewarp_sheet(draw_sheet(rule_ys)).image
  chains = resolve_grid_consensus(frame.convert('L')).chains
  top = statistics.median(chain.rule_ys[0] for chain in chains)
  bottom = statistics.median(chain.rule_ys[-1] for chain in chains)
  return frame, round(top), round(bottom)


def _reading(rule_ys: Sequence[int], row_count: int, *, footer: bool) -> str:
  """A scripted layout reading of a drawn sheet, as the model returns one."""
  frame, top, bottom = _frame_bounds(rule_ys)
  return json.dumps(
    {
      'panels': [
        {
          'board_row_count': row_count,
          'grid': {
            'left': 0,
            'top': top,
            'right': frame.width,
            'bottom': bottom,
          },
        }
      ],
      'footer': {
        'left': 0,
        'top': frame.height - 50,
        'right': frame.width,
        'bottom': frame.height,
      }
      if footer
      else None,
      'notes': '',
    }
  )


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


def test_transcribe_sheet_returns_the_resolved_geometry() -> None:
  # 29 rules at a 20px pitch bounding 28 board rows, drawn from y=100 between
  # x=40 and x=560.
  rule_ys = range(100, 661, 20)

  with ScriptedModelRunner(
    [_reading(rule_ys, 28, footer=False), '{}', '{}']
  ) as runner:
    transcription = transcribe_sheet(draw_sheet(rule_ys), run_command=runner)

  # The reading's 28 reached the geometry: a count mis-parsed as 27 would still
  # resolve against these rules, so this is not the row count coming back to
  # meet itself.
  assert len(transcription.geometry.row_boxes) == 28
  # The source quad sits just outside the drawn grid: the dewarp margins push
  # its top corner above and left of the first rule's start at (40, 100).
  assert transcription.source_quad.top_left.y < 100
  assert transcription.source_quad.top_left.x < 40


def test_transcribe_sheet_reads_the_same_strips_both_times() -> None:
  with ScriptedModelRunner(
    [_reading(_TWENTY_FOUR_ROWS, 24, footer=False), '{}', '{}']
  ) as runner:
    transcribe_sheet(draw_sheet(_TWENTY_FOUR_ROWS), run_command=runner)

  # Three requests: the layout reading, then the two transcription runs, which
  # must be byte-identical for the vote to mean anything.
  assert len(runner.stdin_texts) == 3
  assert runner.stdin_texts[1] == runner.stdin_texts[2]


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
  # strip named this way it is to leave the event and date empty — so the
  # wording is load-bearing rather than cosmetic.
  assert content[-3] == {'type': 'text', 'text': 'Strip for the footer:'}
  assert content[-1] == {
    'type': 'text',
    'text': 'Transcribe the attached scan.',
  }


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
