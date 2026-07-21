# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for extraction.

`transcribe_sheet` is tested end to end on a synthetic drawn grid with a
scripted `run_command` fake — no real `claude` process, mirroring the
vision_model_invocation tests.
"""

import json
import pathlib
import subprocess
from collections.abc import Sequence

from PIL import Image, ImageDraw

from session_analysis.extraction import transcribe_sheet


class _RecordingRunner:
  """A scripted `run_command` fake returning one canned success reply."""

  def __init__(self, result: str) -> None:
    self._result = result
    self.stdin_text: str | None = None

  def __call__(
    self, command: Sequence[str], stdin_text: str, cwd: pathlib.Path
  ) -> subprocess.CompletedProcess[str]:
    self.stdin_text = stdin_text
    reply = {'type': 'result', 'is_error': False, 'result': self._result}
    return subprocess.CompletedProcess(
      args=[], returncode=0, stdout=json.dumps(reply), stderr=''
    )


def _draw_sheet() -> Image.Image:
  """A synthetic 28-row scan: 29 rules at pitch 20 between vertical borders."""
  image = Image.new('L', (600, 800), color=255)
  draw = ImageDraw.Draw(image)
  rule_ys = list(range(100, 661, 20))
  for rule_y in rule_ys:
    draw.line([(40, rule_y), (560, rule_y)], fill=0)
  for border_x in (40, 560):
    draw.line([(border_x, rule_ys[0]), (border_x, rule_ys[-1])], fill=0)
  return image


def test_transcribe_sheet_returns_raw_json_and_the_detected_geometry() -> None:
  runner = _RecordingRunner(result='{"sheet": {"boards": []}}')

  transcription = transcribe_sheet(_draw_sheet(), run_command=runner)

  assert transcription.raw_json == '{"sheet": {"boards": []}}'
  assert len(transcription.geometry.row_boxes) == 28
  # The source quad sits just outside the drawn grid: the dewarp margins push
  # its top corner above and left of the first rule's start at (40, 100).
  assert transcription.source_quad.top_left.y < 100
  assert transcription.source_quad.top_left.x < 40


def test_transcribe_sheet_sends_labeled_strips_for_every_row() -> None:
  runner = _RecordingRunner(result='{}')

  transcribe_sheet(_draw_sheet(), run_command=runner)

  assert runner.stdin_text is not None
  content = json.loads(runner.stdin_text)['message']['content']
  # 29 label/image pairs (28 rows + footer) and the final instruction.
  assert len(content) == 59
  assert content[0] == {'type': 'text', 'text': 'Strip for printed row 1:'}
  assert content[1]['type'] == 'image'
  assert content[-3] == {'type': 'text', 'text': 'Strip for the footer:'}
  assert content[-1] == {
    'type': 'text',
    'text': 'Transcribe the attached scan.',
  }
