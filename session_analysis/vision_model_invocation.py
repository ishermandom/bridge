# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Headless invocation of Claude Code as the scoresheet vision model.

Extraction reads a sheet image through the existing Claude subscription rather
than a separate vision API: `claude -p` in non-interactive mode, given a
transcription-scoped system prompt and a JSON Schema for its output. See spec.md
(Extraction) for why headless Claude Code was chosen and how the invocation is
shaped.

The request is an ordered sequence of `LabeledImage` parts — per-row strips, in
production — closed by the fixed transcription ask. Images are embedded directly
in the request rather than left to `Read` tool calls: that collapses the
exchange to one turn and skips the tool definition's token cost entirely.
Embedding requires `--input-format stream-json`, which the CLI only allows
paired with `--output-format stream-json` — so the response is parsed as one
JSON object per line, ending in a `result` event, rather than the single-object
envelope `--output-format json` gives.
"""

import base64
import dataclasses
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

DEFAULT_MODEL = 'claude-opus-4-8'

# The user-turn ask that closes each request, after the images. All real
# instruction lives in the system prompt; the user turn exists because the API
# needs one to respond to, and this line makes its ask explicit rather than
# sending images with no request.
_TRANSCRIPTION_INSTRUCTION = 'Transcribe the attached scan.'


@dataclasses.dataclass(frozen=True)
class LabeledImage:
  """One request part: an image preceded by a text label naming what it shows
  (e.g. which printed row a strip covers).
  """

  label: str
  image_bytes: bytes
  media_type: str


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


def run_claude(
  command: Sequence[str], stdin_text: str, cwd: pathlib.Path
) -> subprocess.CompletedProcess[str]:
  """The production `CommandRunner`: run the real `claude` subprocess."""
  cwd.mkdir(exist_ok=True)
  return subprocess.run(
    command, input=stdin_text, capture_output=True, text=True, cwd=cwd
  )


def _build_request(parts: Sequence[LabeledImage]) -> str:
  """Return the stream-json request line carrying the labeled images."""
  content: list[dict[str, object]] = []
  for part in parts:
    content.append({'type': 'text', 'text': part.label})
    content.append(
      {
        'type': 'image',
        'source': {
          'type': 'base64',
          'media_type': part.media_type,
          'data': base64.b64encode(part.image_bytes).decode('ascii'),
        },
      }
    )
  content.append({'type': 'text', 'text': _TRANSCRIPTION_INSTRUCTION})
  message = {'type': 'user', 'message': {'role': 'user', 'content': content}}
  return json.dumps(message) + '\n'


def _parse_result(stdout: str) -> str:
  """Return the `result` event's payload from a stream-json transcript.

  Raises:
    VisionModelInvocationError: no line parses as JSON, no line is a `result` event,
      or the result event's `is_error` flag is set.
  """
  # TODO: this aborts on the first non-JSON line, even if a valid `result` event
  # follows later in the stream. Accepted for now — observed CLI output is
  # always clean JSON lines — but a stray non-JSON line (a warning printed to
  # stdout, a partial write) would surface a confusing error instead of the real
  # result.
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
  parts: Sequence[LabeledImage],
  system_prompt: str,
  json_schema: Mapping[str, object],
  *,
  model: str = DEFAULT_MODEL,
  run_command: CommandRunner = run_claude,
) -> str:
  """Run one scoresheet transcription through headless Claude Code.

  Args:
    parts: the images to transcribe, in request order, each embedded as base64
      rather than left to a `Read` tool call.
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
  request = _build_request(parts)

  command = [
      'claude', '-p',
      '--model', model,
      '--system-prompt', system_prompt,
      '--tools', '',
      '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
      '--setting-sources', '',
      '--input-format', 'stream-json',
      '--output-format', 'stream-json',
      # The CLI refuses `-p` with stream-json output unless verbose; the extra
      # events it emits are skipped by `_parse_result` anyway.
      '--verbose',
      '--json-schema', json.dumps(dict(json_schema)),
      # A response violating the schema comes back as an error tool result the
      # model corrects on its next turn, so leave room for a retry or two; live
      # runs hit this (a first attempt shaped as `{"boards": {...}}`).
      '--max-turns', '3',
  ]  # fmt: skip

  process = run_command(command, request, _SCRATCH_DIRECTORY)

  if process.returncode != 0:
    raise VisionModelInvocationError(
      f'claude exited {process.returncode}: {process.stderr.strip()}'
    )

  return _parse_result(process.stdout)
