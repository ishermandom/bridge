# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for extraction.

`transcribe_sheet` is tested end to end on a synthetic drawn grid with a
scripted `run_command` fake — no real `claude` process, mirroring the
vision_model_invocation tests.
"""

import json

from session_analysis.extraction import transcribe_sheet
from session_analysis.testing.scripted_model import ScriptedModelRunner
from session_analysis.testing.synthetic_scans import draw_sheet

# 29 rules bounding 28 board rows at a 20px pitch, on a 600x800-pixel page.
_STANDARD_RULE_YS = list(range(100, 661, 20))


def test_transcribe_sheet_returns_both_runs_raw_json() -> None:
  with ScriptedModelRunner(
    ['{"sheet": {"boards": []}}', '{"sheet": {"boards": [{}]}}']
  ) as runner:
    transcription = transcribe_sheet(draw_sheet(), run_command=runner)

  assert transcription.raw_jsons == (
    '{"sheet": {"boards": []}}',
    '{"sheet": {"boards": [{}]}}',
  )


def test_transcribe_sheet_returns_the_detected_geometry() -> None:
  with ScriptedModelRunner(['{}', '{}']) as runner:
    transcription = transcribe_sheet(
      draw_sheet(_STANDARD_RULE_YS), run_command=runner
    )

  assert len(transcription.geometry.row_boxes) == 28
  # The source quad sits just outside the drawn grid: the dewarp margins push
  # its top corner above and left of the first rule's start at (40, 100).
  assert transcription.source_quad.top_left.y < 100
  assert transcription.source_quad.top_left.x < 40


def test_transcribe_sheet_reads_the_same_strips_both_times() -> None:
  with ScriptedModelRunner(['{}', '{}']) as runner:
    transcribe_sheet(draw_sheet(), run_command=runner)

  assert len(runner.stdin_texts) == 2
  assert runner.stdin_texts[0] == runner.stdin_texts[1]


def test_transcribe_sheet_sends_labeled_strips_for_every_row() -> None:
  with ScriptedModelRunner(['{}', '{}']) as runner:
    transcribe_sheet(draw_sheet(_STANDARD_RULE_YS), run_command=runner)

  content = json.loads(runner.stdin_texts[0])['message']['content']
  # 29 label/image pairs (28 rows + footer) and the final instruction.
  assert len(content) == 59
  assert content[0] == {'type': 'text', 'text': 'Strip for printed row 1:'}
  assert content[1]['type'] == 'image'
  assert content[-3] == {'type': 'text', 'text': 'Strip for the footer:'}
  assert content[-1] == {
    'type': 'text',
    'text': 'Transcribe the attached scan.',
  }
