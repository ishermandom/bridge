# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for vision_model_invocation.

No real `claude` process is ever spawned: `invoke_vision_model` takes an
injectable `run_command`, which these tests fake with a canned
`CompletedProcess` — mirroring how this codebase fakes other external clients.
"""

import base64
import json
import pathlib
import subprocess
from collections.abc import Sequence

import pytest

from session_analysis.vision_model_invocation import (
  VisionModelInvocationError,
  invoke_vision_model,
)

_SCHEMA = {'type': 'object', 'properties': {'board': {'type': 'string'}}}


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


def _make_scan(tmp_path: pathlib.Path, suffix: str = '.png') -> pathlib.Path:
  scan_path = tmp_path / f'scan{suffix}'
  scan_path.write_bytes(b'not a real image, just test bytes')
  return scan_path


# --- successful invocation ---


def test_returns_the_result_event_payload(tmp_path: pathlib.Path) -> None:
  runner = _RecordingRunner(
    _make_completed_process(
      [
        {'type': 'system', 'subtype': 'init'},
        {'type': 'result', 'is_error': False, 'result': '{"board": "7"}'},
      ]
    )
  )

  result = invoke_vision_model(
    _make_scan(tmp_path), 'transcribe this', _SCHEMA, run_command=runner
  )

  assert result == '{"board": "7"}'


def test_request_embeds_the_image_as_base64(tmp_path: pathlib.Path) -> None:
  scan_path = _make_scan(tmp_path)
  runner = _RecordingRunner(
    _make_completed_process(
      [{'type': 'result', 'is_error': False, 'result': '{}'}]
    )
  )

  invoke_vision_model(scan_path, 'transcribe this', _SCHEMA, run_command=runner)

  assert runner.stdin_text is not None
  request = json.loads(runner.stdin_text)
  image_block = request['message']['content'][0]
  assert image_block['type'] == 'image'
  assert image_block['source']['media_type'] == 'image/png'
  assert image_block['source']['data'] == base64.b64encode(
    scan_path.read_bytes()
  ).decode('ascii')


def test_command_carries_the_model_prompt_and_schema(
  tmp_path: pathlib.Path,
) -> None:
  runner = _RecordingRunner(
    _make_completed_process(
      [{'type': 'result', 'is_error': False, 'result': '{}'}]
    )
  )

  invoke_vision_model(
    _make_scan(tmp_path),
    'transcribe this',
    _SCHEMA,
    model='claude-sonnet-5',
    run_command=runner,
  )

  assert runner.command is not None
  assert '--model' in runner.command
  assert (
    runner.command[runner.command.index('--model') + 1] == 'claude-sonnet-5'
  )
  assert '--system-prompt' in runner.command
  assert (
    runner.command[runner.command.index('--system-prompt') + 1]
    == 'transcribe this'
  )
  assert '--json-schema' in runner.command
  schema_argument = runner.command[runner.command.index('--json-schema') + 1]
  assert json.loads(schema_argument) == _SCHEMA


# --- failure modes ---


def test_nonzero_exit_raises(tmp_path: pathlib.Path) -> None:
  runner = _RecordingRunner(
    _make_completed_process([], returncode=1, stderr='boom')
  )

  with pytest.raises(VisionModelInvocationError, match='boom'):
    invoke_vision_model(
      _make_scan(tmp_path), 'transcribe this', _SCHEMA, run_command=runner
    )


def test_missing_result_event_raises(tmp_path: pathlib.Path) -> None:
  runner = _RecordingRunner(
    _make_completed_process([{'type': 'system', 'subtype': 'init'}])
  )

  with pytest.raises(VisionModelInvocationError, match='no result event'):
    invoke_vision_model(
      _make_scan(tmp_path), 'transcribe this', _SCHEMA, run_command=runner
    )


def test_is_error_result_raises(tmp_path: pathlib.Path) -> None:
  runner = _RecordingRunner(
    _make_completed_process(
      [{'type': 'result', 'is_error': True, 'result': 'Invalid API key'}]
    )
  )

  with pytest.raises(VisionModelInvocationError, match='Invalid API key'):
    invoke_vision_model(
      _make_scan(tmp_path), 'transcribe this', _SCHEMA, run_command=runner
    )


def test_unsupported_image_suffix_raises(tmp_path: pathlib.Path) -> None:
  scan_path = _make_scan(tmp_path, suffix='.gif')
  runner = _RecordingRunner(_make_completed_process([]))

  with pytest.raises(ValueError, match=r'\.gif'):
    invoke_vision_model(
      scan_path, 'transcribe this', _SCHEMA, run_command=runner
    )
