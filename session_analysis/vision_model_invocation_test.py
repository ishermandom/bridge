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
import json
import pathlib
import subprocess
from collections.abc import Mapping, Sequence

import pytest

from session_analysis.vision_model_invocation import (
  CommandRunner,
  LabeledImage,
  VisionModelInvocationError,
  invoke_vision_model,
)

_SCHEMA = {'type': 'object', 'properties': {'board': {'type': 'string'}}}
_IMAGE_BYTES = b'not a real image, just test bytes'
_MEDIA_TYPE = 'image/png'
_SYSTEM_PROMPT = 'transcribe this'
_INSTRUCTION = 'go transcribe'
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
  LabeledImage(
    label='Scan:', image_bytes=_IMAGE_BYTES, media_type=_MEDIA_TYPE
  ),
)


def _invoke_vision_model(
  *,
  run_command: CommandRunner,
  parts: Sequence[LabeledImage] = _SINGLE_PART,
  system_prompt: str = _SYSTEM_PROMPT,
  instruction: str = _INSTRUCTION,
  json_schema: Mapping[str, object] = _SCHEMA,
  model: str = _MODEL,
) -> str:
  """Call `invoke_vision_model`, defaulting the args a given test doesn't care
  about — callers pass only what they're testing.
  """
  return invoke_vision_model(
    parts,
    system_prompt,
    instruction,
    json_schema,
    model=model,
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
  parts = [
    LabeledImage(label='Row 1:', image_bytes=b'one', media_type='image/jpeg'),
    LabeledImage(label='Row 2:', image_bytes=b'two', media_type='image/jpeg'),
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
  assert content[3]['source']['data'] == base64.b64encode(b'two').decode(
    'ascii'
  )


def test_request_closes_with_the_given_instruction() -> None:
  runner = _make_successful_runner()

  _invoke_vision_model(run_command=runner, instruction='read the sheet')

  assert runner.stdin_text is not None
  content = json.loads(runner.stdin_text)['message']['content']
  assert content[-1] == {'type': 'text', 'text': 'read the sheet'}


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


def test_command_uses_the_given_model_not_the_default() -> None:
  runner = _make_successful_runner()

  _invoke_vision_model(run_command=runner, model='claude-haiku-4-5-20251001')

  assert runner.command is not None
  assert (
    runner.command[runner.command.index('--model') + 1]
    == 'claude-haiku-4-5-20251001'
  )


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


