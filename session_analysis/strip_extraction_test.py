# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for strip_extraction.

Cutting is tested against hand-built `SheetGeometry` values, so every expected
crop bound is visible in the test. `transcribe_sheet` is tested end to end on a
synthetic drawn grid with a scripted `run_command` fake — no real `claude`
process, mirroring the vision_model_invocation tests.
"""

import io
import json
import pathlib
import subprocess
from collections.abc import Sequence

from PIL import Image, ImageDraw

from session_analysis.sheet_geometry import Box, SheetGeometry
from session_analysis.strip_extraction import cut_strips, transcribe_sheet

# Three tight 20px rows and a footer on a 100x200 page.
_GEOMETRY = SheetGeometry(
  image_width=100,
  image_height=200,
  row_boxes=(
    Box(left=10, top=50, right=90, bottom=70),
    Box(left=10, top=70, right=90, bottom=90),
    Box(left=10, top=90, right=90, bottom=110),
  ),
  footer_box=Box(left=10, top=110, right=90, bottom=140),
)


def _decode(image_bytes: bytes) -> Image.Image:
  return Image.open(io.BytesIO(image_bytes))


# --- cut_strips ---


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
    footer_box=Box(left=10, top=22, right=90, bottom=24),
  )

  parts = cut_strips(image, geometry)

  # 6px of padding would reach y=-4 and y=28; both clamp to the image.
  assert _decode(parts[0].image_bytes).size == (80, 24)


def test_the_footer_strip_is_cut_unpadded() -> None:
  image = Image.new('RGB', (100, 200), color='white')

  parts = cut_strips(image, _GEOMETRY)

  assert _decode(parts[-1].image_bytes).size == (80, 30)


# --- transcribe_sheet ---


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
