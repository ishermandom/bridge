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
import types
from collections.abc import Sequence

from session_analysis.extraction import transcribe_sheet
from session_analysis.testing.synthetic_scans import draw_sheet

# 29 rules bounding 28 board rows at a 20px pitch, on a 600x800-pixel page.
_STANDARD_RULE_YS = list(range(100, 661, 20))


class _RecordingRunner:
  """A scripted `run_command` fake: returns each of `results` in order,
  recording every stdin it was called with so a test can inspect every request.
  """

  def __init__(self, results: Sequence[str]) -> None:
    self._results = list(results)
    self.stdin_texts: list[str] = []

  def __call__(
    self, command: Sequence[str], stdin_text: str, cwd: pathlib.Path
  ) -> subprocess.CompletedProcess[str]:
    self.stdin_texts.append(stdin_text)
    reply = {
      'type': 'result',
      'is_error': False,
      'result': self._results.pop(0),
    }
    return subprocess.CompletedProcess(
      args=[], returncode=0, stdout=json.dumps(reply), stderr=''
    )

  def __enter__(self) -> '_RecordingRunner':
    return self

  def __exit__(
    self,
    exc_type: type[BaseException] | None,
    exc: BaseException | None,
    tb: types.TracebackType | None,
  ) -> None:
    if exc_type is None:
      assert not self._results, f'{len(self._results)} scripted replies unused'


def test_transcribe_sheet_returns_both_runs_raw_json() -> None:
  with _RecordingRunner(
    ['{"sheet": {"boards": []}}', '{"sheet": {"boards": [{}]}}']
  ) as runner:
    transcription = transcribe_sheet(draw_sheet(), run_command=runner)

  assert transcription.raw_jsons == (
    '{"sheet": {"boards": []}}',
    '{"sheet": {"boards": [{}]}}',
  )


def test_transcribe_sheet_returns_the_detected_geometry() -> None:
  with _RecordingRunner(['{}', '{}']) as runner:
    transcription = transcribe_sheet(
      draw_sheet(_STANDARD_RULE_YS), run_command=runner
    )

  assert len(transcription.geometry.row_boxes) == 28
  # The source quad sits just outside the drawn grid: the dewarp margins push
  # its top corner above and left of the first rule's start at (40, 100).
  assert transcription.source_quad.top_left.y < 100
  assert transcription.source_quad.top_left.x < 40


def test_transcribe_sheet_reads_the_same_strips_both_times() -> None:
  with _RecordingRunner(['{}', '{}']) as runner:
    transcribe_sheet(draw_sheet(), run_command=runner)

  assert len(runner.stdin_texts) == 2
  assert runner.stdin_texts[0] == runner.stdin_texts[1]


def test_transcribe_sheet_sends_labeled_strips_for_every_row() -> None:
  with _RecordingRunner(['{}', '{}']) as runner:
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
