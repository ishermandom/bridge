# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for vision_model_invocation.

No real `claude` process is ever spawned: `invoke_vision_model` takes an
injectable `run_command`, which these tests fake with a canned
`CompletedProcess` — mirroring how this codebase fakes other external clients.
`invoke_vision_model` itself takes image bytes directly, so most tests need no
filesystem at all. `invoke_vision_model_for_scan`, the thin wrapper whose only
job is reading a scan file, is tested separately with `tmp_path`.
"""

import base64
import json
import pathlib
import subprocess
from collections.abc import Mapping, Sequence

import pytest

from session_analysis.vision_model_invocation import (
  CommandRunner,
  VisionModelInvocationError,
  invoke_vision_model,
  invoke_vision_model_for_scan,
  media_type_for_suffix,
)

_SCHEMA = {'type': 'object', 'properties': {'board': {'type': 'string'}}}
_IMAGE_BYTES = b'not a real image, just test bytes'
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


def _invoke_vision_model(
  *,
  run_command: CommandRunner,
  image_bytes: bytes = _IMAGE_BYTES,
  media_type: str = _MEDIA_TYPE,
  system_prompt: str = _SYSTEM_PROMPT,
  json_schema: Mapping[str, object] = _SCHEMA,
  model: str = _MODEL,
) -> str:
  """Call `invoke_vision_model`, defaulting the args a given test doesn't care
  about — callers pass only what they're testing.
  """
  return invoke_vision_model(
    image_bytes,
    media_type,
    system_prompt,
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
  image_block = request['message']['content'][0]
  assert image_block['type'] == 'image'
  assert image_block['source']['media_type'] == _MEDIA_TYPE
  assert image_block['source']['data'] == base64.b64encode(_IMAGE_BYTES).decode(
    'ascii'
  )


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


# --- media_type_for_suffix ---


def test_media_type_for_known_suffix() -> None:
  assert media_type_for_suffix('.png') == 'image/png'
  assert media_type_for_suffix('.jpeg') == 'image/jpeg'


def test_media_type_for_unsupported_suffix_raises() -> None:
  with pytest.raises(ValueError, match=r'\.gif'):
    media_type_for_suffix('.gif')


# --- invoke_vision_model_for_scan (thin file-reading wrapper) ---


def _make_scan(tmp_path: pathlib.Path, suffix: str = '.png') -> pathlib.Path:
  scan_path = tmp_path / f'scan{suffix}'
  scan_path.write_bytes(_IMAGE_BYTES)
  return scan_path


def test_for_scan_reads_the_file_and_delegates(tmp_path: pathlib.Path) -> None:
  scan_path = _make_scan(tmp_path)
  runner = _make_successful_runner(result='{"board": "7"}')

  result = invoke_vision_model_for_scan(
    scan_path, _SYSTEM_PROMPT, _SCHEMA, run_command=runner
  )

  assert result == '{"board": "7"}'
  assert runner.stdin_text is not None
  image_block = json.loads(runner.stdin_text)['message']['content'][0]
  assert image_block['source']['media_type'] == 'image/png'
  assert image_block['source']['data'] == base64.b64encode(_IMAGE_BYTES).decode(
    'ascii'
  )


def test_for_scan_unsupported_suffix_raises(tmp_path: pathlib.Path) -> None:
  scan_path = _make_scan(tmp_path, suffix='.gif')
  runner = _make_successful_runner()

  with pytest.raises(ValueError, match=r'\.gif'):
    invoke_vision_model_for_scan(
      scan_path, _SYSTEM_PROMPT, _SCHEMA, run_command=runner
    )
