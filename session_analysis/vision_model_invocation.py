# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Headless invocation of Claude Code as the scoresheet vision model.

Extraction reads a sheet image through the existing Claude subscription rather
than a separate vision API: `claude -p` in non-interactive mode, given a
transcription-scoped system prompt and a JSON Schema for its output. See spec.md
(Extraction) for why headless Claude Code was chosen and how the invocation is
shaped.

The image is embedded directly in the request rather than left to a `Read` tool
call: that collapses the exchange to one turn and skips the tool definition's
token cost entirely. Embedding requires `--input-format stream-json`, which the
CLI only allows paired with `--output-format stream-json` — so the response is
parsed as one JSON object per line, ending in a `result` event, rather than the
single-object envelope `--output-format json` gives.
"""

import base64
import json
import pathlib
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence

# A fixed, reused scratch directory to invoke `claude` from. Even with a
# replacement system prompt and every setting source disabled, the CLI still
# folds some per-machine context (cwd, git status) into the request; running
# from a directory with no CLAUDE.md, no git repo, and nothing else in it keeps
# that context minimal and identical across invocations.
_SCRATCH_DIRECTORY = (
  pathlib.Path(tempfile.gettempdir()) / 'session_analysis_vision_model_scratch'
)

_DEFAULT_MODEL = 'claude-sonnet-5'

_MEDIA_TYPE_BY_SUFFIX = {
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
}

# The shape a scripted test fake must match: given the `claude` command line and
# the stream-json request to feed it on stdin, return the completed process.
# Production code runs the real subprocess; tests substitute a fake that returns
# a canned result with no process ever spawned.
CommandRunner = Callable[
  [Sequence[str], str, pathlib.Path], subprocess.CompletedProcess[str]
]


class VisionModelInvocationError(Exception):
  """Raised when the headless `claude` invocation itself fails.

  Covers a nonzero exit, a missing or unparseable result event, and the CLI's
  own `is_error` flag (an auth failure, a rate limit, and the like) — not a
  `json_schema` violation in a successful response, which is the caller's
  concern once this returns.
  """


def _run_claude(
  command: Sequence[str], stdin_text: str, cwd: pathlib.Path
) -> subprocess.CompletedProcess[str]:
  cwd.mkdir(exist_ok=True)
  return subprocess.run(
    command, input=stdin_text, capture_output=True, text=True, cwd=cwd
  )


def _build_request(image_bytes: bytes, media_type: str) -> str:
  """Return the stream-json request line embedding the image as base64."""
  message = {
    'type': 'user',
    'message': {
      'role': 'user',
      'content': [
        {
          'type': 'image',
          'source': {
            'type': 'base64',
            'media_type': media_type,
            'data': base64.b64encode(image_bytes).decode('ascii'),
          },
        },
        {'type': 'text', 'text': 'Transcribe the attached scan.'},
      ],
    },
  }
  return json.dumps(message) + '\n'


def _parse_result(stdout: str) -> str:
  """Return the `result` event's payload from a stream-json transcript.

  Raises:
    VisionModelInvocationError: no line parses as JSON, no line is a `result` event,
      or the result event's `is_error` flag is set.
  """
  result_event = None
  for line in stdout.splitlines():
    try:
      event = json.loads(line)
    except json.JSONDecodeError as error:
      raise VisionModelInvocationError(
        f'claude emitted a non-JSON line: {line!r} ({error})'
      ) from error
    if event.get('type') == 'result':
      result_event = event
      break

  if result_event is None:
    raise VisionModelInvocationError(
      f'no result event in claude output: {stdout!r}'
    )

  if result_event.get('is_error'):
    raise VisionModelInvocationError(
      f'claude reported an error: {result_event.get("result")!r}'
    )

  result = result_event.get('result')
  if not isinstance(result, str):
    raise VisionModelInvocationError(
      f'claude result event has a non-string result field: {result!r}'
    )
  return result


def invoke_vision_model(
  image_bytes: bytes,
  media_type: str,
  system_prompt: str,
  json_schema: Mapping[str, object],
  *,
  model: str = _DEFAULT_MODEL,
  run_command: CommandRunner = _run_claude,
) -> str:
  """Run one scoresheet image through headless Claude Code.

  Args:
    image_bytes: the scan to transcribe, embedded in the request as base64
      rather than left to a `Read` tool call.
    media_type: the image's MIME type, e.g. `'image/png'`. See
      `media_type_for_suffix` to derive it from a file extension.
    system_prompt: replaces the CLI's default agentic-coding system prompt
      entirely, scoping the model to transcription.
    json_schema: a JSON Schema the response must validate against, enforced by
      `--json-schema` so the result is directly parseable rather than prose or
      markdown-fenced JSON.
    model: the model alias or full name to invoke.
    run_command: the subprocess runner to use. Defaults to a real
      `subprocess.run` call, which creates the scratch directory if missing;
      tests substitute a fake that returns a scripted `CompletedProcess` with
      no process ever spawned and no directory ever touched.

  Returns:
    The model's response, as a JSON string conforming to `json_schema`.

  Raises:
    VisionModelInvocationError: the `claude` process exited nonzero, or its output
      failed to yield a successful result event — see `_parse_result`.
  """
  request = _build_request(image_bytes, media_type)

  command = [
      'claude', '-p',
      '--model', model,
      '--system-prompt', system_prompt,
      '--tools', '',
      '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
      '--setting-sources', '',
      '--input-format', 'stream-json',
      '--output-format', 'stream-json',
      '--json-schema', json.dumps(dict(json_schema)),
      '--max-turns', '1',
  ]  # fmt: skip

  process = run_command(command, request, _SCRATCH_DIRECTORY)

  if process.returncode != 0:
    raise VisionModelInvocationError(
      f'claude exited {process.returncode}: {process.stderr.strip()}'
    )

  return _parse_result(process.stdout)


def media_type_for_suffix(suffix: str) -> str:
  """Return the MIME type for a lowercase image file suffix (e.g. `'.png'`).

  Raises:
    ValueError: the suffix isn't one of the supported image types.
  """
  try:
    return _MEDIA_TYPE_BY_SUFFIX[suffix]
  except KeyError:
    raise ValueError(
      f'unsupported image suffix {suffix!r}: expected one of '
      f'{sorted(_MEDIA_TYPE_BY_SUFFIX)}'
    ) from None


def invoke_vision_model_for_scan(
  image_path: pathlib.Path,
  system_prompt: str,
  json_schema: Mapping[str, object],
  *,
  model: str = _DEFAULT_MODEL,
  run_command: CommandRunner = _run_claude,
) -> str:
  """Thin wrapper: read `image_path` and delegate to `invoke_vision_model`.

  The only job here is resolving a scan file to bytes and a media type; see
  `invoke_vision_model` for the actual invocation, which takes bytes directly so
  it can be tested without touching the filesystem.
  """
  media_type = media_type_for_suffix(image_path.suffix.lower())
  return invoke_vision_model(
      image_path.read_bytes(),
      media_type,
      system_prompt,
      json_schema,
      model=model,
      run_command=run_command,
  )  # fmt: skip
