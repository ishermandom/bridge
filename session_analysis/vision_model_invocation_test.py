# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for vision_model_invocation.

No real `claude` process is ever spawned: `invoke_vision_model` takes an
injectable `run_command`, which these tests fake with a canned
`CompletedProcess` — mirroring how this codebase fakes other external clients.
`invoke_vision_model` takes `LabeledImage` parts directly, so no test needs the
filesystem at all.
"""

import base64
import io
import json
import os
import pathlib
import subprocess
from collections.abc import Mapping, Sequence

import pytest
from PIL import Image

from session_analysis.vision_model_invocation import (
  DEFAULT_EFFORT,
  MAX_IMAGE_BYTES,
  CommandRunner,
  Effort,
  LabeledImage,
  VisionModelInvocationError,
  invoke_vision_model,
)


def _make_image_bytes(
  width: int, height: int, *, is_noise: bool = False
) -> bytes:
  """A PNG of the given size — blank, which compresses to almost nothing, or
  random noise, which PNG cannot compress at all.
  """
  if is_noise:
    image = Image.frombytes(
      'RGB', (width, height), os.urandom(width * height * 3)
    )
  else:
    image = Image.new('RGB', (width, height), 'white')
  buffer = io.BytesIO()
  image.save(buffer, format='PNG')
  return buffer.getvalue()


_SCHEMA = {'type': 'object', 'properties': {'board': {'type': 'string'}}}
_IMAGE_BYTES = _make_image_bytes(8, 8)
_MEDIA_TYPE = 'image/png'
_SYSTEM_PROMPT = 'transcribe this'
_MODEL = 'claude-sonnet-5'


class _RecordingRunner:
  """A scripted `run_command` fake: returns one canned reply, recording the
  command and stdin it was called with so a test can inspect them.
  """

  def __init__(
    self, completed_process: subprocess.CompletedProcess[str]
  ) -> None:
    self._completed_process = completed_process
    self.command: list[str] | None = None
    self.stdin_text: str | None = None

  def __call__(
    self, command: Sequence[str], stdin_text: str, cwd: pathlib.Path
  ) -> subprocess.CompletedProcess[str]:
    self.command = list(command)
    self.stdin_text = stdin_text
    return self._completed_process


def _make_completed_process(
  stdout_events: list[dict[str, object]], returncode: int = 0, stderr: str = ''
) -> subprocess.CompletedProcess[str]:
  stdout = '\n'.join(json.dumps(event) for event in stdout_events)
  return subprocess.CompletedProcess(
    args=[], returncode=returncode, stdout=stdout, stderr=stderr
  )


def _make_successful_runner(result: str = '{}') -> _RecordingRunner:
  """A runner whose invocation succeeds with the given result payload — for
  tests where the payload itself isn't what's under test.
  """
  return _RecordingRunner(
    _make_completed_process(
      [{'type': 'result', 'is_error': False, 'result': result}]
    )
  )


_SINGLE_PART = (
  LabeledImage(label='Scan:', image_bytes=_IMAGE_BYTES, media_type=_MEDIA_TYPE),
)


def _invoke_vision_model(
  *,
  run_command: CommandRunner,
  parts: Sequence[LabeledImage] = _SINGLE_PART,
  system_prompt: str = _SYSTEM_PROMPT,
  json_schema: Mapping[str, object] = _SCHEMA,
  model: str = _MODEL,
  effort: Effort = DEFAULT_EFFORT,
) -> str:
  """Call `invoke_vision_model`, defaulting the args a given test doesn't care
  about — callers pass only what they're testing.
  """
  return invoke_vision_model(
    parts,
    system_prompt,
    json_schema,
    model=model,
    effort=effort,
    run_command=run_command,
  )


# --- successful invocation ---


def test_returns_the_result_event_payload() -> None:
  runner = _RecordingRunner(
    _make_completed_process(
      [
        {'type': 'system', 'subtype': 'init'},
        {'type': 'result', 'is_error': False, 'result': '{"board": "7"}'},
      ]
    )
  )

  result = _invoke_vision_model(run_command=runner)

  assert result == '{"board": "7"}'


def test_request_embeds_the_image_as_base64() -> None:
  runner = _make_successful_runner()

  _invoke_vision_model(run_command=runner)

  assert runner.stdin_text is not None
  request = json.loads(runner.stdin_text)
  image_block = request['message']['content'][1]
  assert image_block['type'] == 'image'
  assert image_block['source']['media_type'] == _MEDIA_TYPE
  assert image_block['source']['data'] == base64.b64encode(_IMAGE_BYTES).decode(
    'ascii'
  )


def test_request_precedes_each_image_with_its_label() -> None:
  runner = _make_successful_runner()
  first_image = _make_image_bytes(8, 8)
  second_image = _make_image_bytes(9, 9)
  parts = [
    LabeledImage(
      label='Row 1:', image_bytes=first_image, media_type='image/png'
    ),
    LabeledImage(
      label='Row 2:', image_bytes=second_image, media_type='image/png'
    ),
  ]

  _invoke_vision_model(run_command=runner, parts=parts)

  assert runner.stdin_text is not None
  content = json.loads(runner.stdin_text)['message']['content']
  assert [block['type'] for block in content] == [
    'text',
    'image',
    'text',
    'image',
    'text',
  ]
  assert content[0]['text'] == 'Row 1:'
  assert content[2]['text'] == 'Row 2:'
  assert content[3]['source']['data'] == base64.b64encode(second_image).decode(
    'ascii'
  )


def test_request_closes_with_the_transcription_ask() -> None:
  runner = _make_successful_runner()

  _invoke_vision_model(run_command=runner)

  assert runner.stdin_text is not None
  content = json.loads(runner.stdin_text)['message']['content']
  assert content[-1] == {
    'type': 'text',
    'text': 'Transcribe the attached scan.',
  }


def test_command_carries_the_model_prompt_and_schema() -> None:
  runner = _make_successful_runner()

  _invoke_vision_model(
    run_command=runner,
    model=_MODEL,
    system_prompt=_SYSTEM_PROMPT,
    json_schema=_SCHEMA,
  )

  assert runner.command is not None
  assert '--model' in runner.command
  assert runner.command[runner.command.index('--model') + 1] == _MODEL
  assert '--system-prompt' in runner.command
  assert (
    runner.command[runner.command.index('--system-prompt') + 1]
    == _SYSTEM_PROMPT
  )
  assert '--json-schema' in runner.command
  schema_argument = runner.command[runner.command.index('--json-schema') + 1]
  assert json.loads(schema_argument) == _SCHEMA


def test_command_pins_the_effort_level() -> None:
  """Every run sends a level, so none inherits the CLI's per-model default.

  Calls the entry point directly rather than through the helper above, which
  passes an effort of its own and would stand in for the default under test.
  """
  runner = _make_successful_runner()

  invoke_vision_model(_SINGLE_PART, _SYSTEM_PROMPT, _SCHEMA, run_command=runner)

  assert runner.command is not None
  assert '--effort' in runner.command
  assert runner.command[runner.command.index('--effort') + 1] == DEFAULT_EFFORT


def test_command_uses_the_given_effort_not_the_default() -> None:
  # `LOW` because transcription would never default to it: were the level under
  # test also the default, the assertion would pass without the override doing
  # anything.
  runner = _make_successful_runner()

  _invoke_vision_model(run_command=runner, effort=Effort.LOW)

  assert runner.command is not None
  assert runner.command[runner.command.index('--effort') + 1] == 'low'


def test_command_uses_the_given_model_not_the_default() -> None:
  runner = _make_successful_runner()

  _invoke_vision_model(run_command=runner, model='claude-haiku-4-5-20251001')

  assert runner.command is not None
  assert (
    runner.command[runner.command.index('--model') + 1]
    == 'claude-haiku-4-5-20251001'
  )


# --- image limits ---


def test_an_image_exactly_at_the_edge_limit_is_sent() -> None:
  runner = _make_successful_runner()
  parts = [
    LabeledImage(
      label='Strip:',
      image_bytes=_make_image_bytes(2000, 10),
      media_type='image/png',
    )
  ]

  _invoke_vision_model(run_command=runner, parts=parts)

  assert runner.command is not None


def test_an_image_over_the_edge_limit_is_refused_before_sending() -> None:
  runner = _make_successful_runner()
  parts = [
    LabeledImage(
      label='Strip:',
      image_bytes=_make_image_bytes(2001, 10),
      media_type='image/png',
    )
  ]

  with pytest.raises(ValueError, match='2001x10'):
    _invoke_vision_model(run_command=runner, parts=parts)
  assert runner.command is None


def test_an_image_over_the_token_budget_is_refused_before_sending() -> None:
  # 1960 pixels is within the edge limit, but 70 patches a side is 4900 visual
  # tokens, past the 4784 budget.
  runner = _make_successful_runner()
  parts = [
    LabeledImage(
      label='Page:',
      image_bytes=_make_image_bytes(1960, 1960),
      media_type='image/png',
    )
  ]

  with pytest.raises(ValueError, match='4900 visual tokens'):
    _invoke_vision_model(run_command=runner, parts=parts)
  assert runner.command is None


def test_an_image_over_the_byte_limit_is_refused_before_sending() -> None:
  # Noise defeats PNG's compression, so 1200x1200 encodes to about 4.3MB — past
  # the byte limit while well within both the edge limit and the token budget.
  runner = _make_successful_runner()
  parts = [
    LabeledImage(
      label='Page:',
      image_bytes=_make_image_bytes(1200, 1200, is_noise=True),
      media_type='image/png',
    )
  ]

  with pytest.raises(
    ValueError, match=f'exceed the {MAX_IMAGE_BYTES}-byte cap'
  ) as refusal:
    _invoke_vision_model(run_command=runner, parts=parts)
  assert runner.command is None
  # The two limits the image is within go unmentioned.
  assert 'pixels' not in str(refusal.value)
  assert 'tokens' not in str(refusal.value)


# --- failure modes ---


def test_nonzero_exit_raises() -> None:
  runner = _RecordingRunner(
    _make_completed_process([], returncode=1, stderr='boom')
  )

  with pytest.raises(VisionModelInvocationError, match='boom'):
    _invoke_vision_model(run_command=runner)


def test_missing_result_event_raises() -> None:
  runner = _RecordingRunner(
    _make_completed_process([{'type': 'system', 'subtype': 'init'}])
  )

  with pytest.raises(VisionModelInvocationError, match='no result event'):
    _invoke_vision_model(run_command=runner)


def test_is_error_result_raises() -> None:
  runner = _RecordingRunner(
    _make_completed_process(
      [{'type': 'result', 'is_error': True, 'result': 'Invalid API key'}]
    )
  )

  with pytest.raises(VisionModelInvocationError, match='Invalid API key'):
    _invoke_vision_model(run_command=runner)
