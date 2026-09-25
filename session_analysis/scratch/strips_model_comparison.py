# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Read one scan's strips at each setting, and record what each run cost.

Step one of the extraction model comparison — see this directory's README.md for
what the comparison is for and how to run both steps.

Strips are cut once from a single scan and every run reads those same strips, so
the only variables are the two the command line sweeps: which model reads them
and how much thinking it spends. Each run's raw transcription, cost, and token
counts are written to the output directory as one JSON file per run, alongside
the strip images themselves — judging a disagreement means looking at the same
crop the model was given.

A run records the model that answered as well as the one that was asked for.
They differ whenever the request names an alias — `opus` rather than a release —
and the measurement is worth little without saying which release produced it.
"""

import argparse
import dataclasses
import json
import pathlib
import subprocess
import time
from collections.abc import Sequence

from PIL import Image

from session_analysis.extraction_prompt import VISION_MODEL_SYSTEM_PROMPT
from session_analysis.extraction_schema import VISION_MODEL_OUTPUT_SCHEMA
from session_analysis.sheet_dewarp import dewarp_sheet
from session_analysis.strip_cutting import cut_strips
from session_analysis.unreviewed.sheet_geometry import resolve_sheet_geometry
from session_analysis.unreviewed.sheet_structure import read_sheet_structure
from session_analysis.vision_model_invocation import (
  DEFAULT_EFFORT,
  Effort,
  LabeledImage,
  invoke_vision_model,
  run_claude,
)


@dataclasses.dataclass(frozen=True)
class RunResult:
  """One run's read of the strips, with what the CLI reported it cost."""

  # What the request asked for, which may be an alias such as `opus`.
  model: str
  # What answered, read back off the stream — a release, never an alias.
  resolved_model: str
  effort: str
  run_index: int
  cost_usd: float
  input_tokens: int
  output_tokens: int
  cache_read_tokens: int
  cache_creation_tokens: int
  turn_count: int
  wall_seconds: float
  transcription: str


class _CostRecordingRunner:
  """A `CommandRunner` that keeps each invocation's raw stdout.

  `invoke_vision_model` returns only the result event's payload, dropping the
  cost and usage fields on the same event — so the runner holds onto the whole
  transcript and the caller re-reads it for the figures.
  """

  def __init__(self) -> None:
    self.last_stdout = ''

  def __call__(
    self, command: Sequence[str], stdin_text: str, cwd: pathlib.Path
  ) -> subprocess.CompletedProcess[str]:
    process = run_claude(command, stdin_text, cwd)
    self.last_stdout = process.stdout
    return process


def _result_event(stdout: str) -> dict[str, object]:
  """Return the `result` event from a stream-json transcript."""
  for line in stdout.splitlines():
    event = json.loads(line)
    if event.get('type') == 'result':
      assert isinstance(event, dict)
      return event
  raise ValueError(f'no result event in claude output: {stdout[:500]!r}')


def _resolved_model(stdout: str) -> str:
  """Return the model the CLI actually ran, from the stream's init event.

  An alias is resolved by the CLI, not by this harness, so the request line
  cannot say which release read the strips — only the transcript can.
  """
  for line in stdout.splitlines():
    event = json.loads(line)
    if event.get('type') == 'system':
      model = event.get('model')
      if isinstance(model, str):
        return model
  raise ValueError(f'no init event naming a model: {stdout[:500]!r}')


def _integer_field(usage: object, name: str) -> int:
  """Read one integer field out of the result event's `usage` object."""
  if not isinstance(usage, dict):
    return 0
  value = usage.get(name, 0)
  return value if isinstance(value, int) else 0


def run_once(
  strips: Sequence[LabeledImage], model: str, effort: Effort, run_index: int
) -> RunResult:
  """Transcribe the strips once at one model and effort, recording the cost."""
  runner = _CostRecordingRunner()
  started = time.monotonic()
  transcription = invoke_vision_model(
    strips,
    VISION_MODEL_SYSTEM_PROMPT,
    VISION_MODEL_OUTPUT_SCHEMA,
    model=model,
    effort=effort,
    run_command=runner,
  )
  wall_seconds = time.monotonic() - started

  event = _result_event(runner.last_stdout)
  usage = event.get('usage')
  cost = event.get('total_cost_usd')
  turns = event.get('num_turns')
  return RunResult(
    model=model,
    resolved_model=_resolved_model(runner.last_stdout),
    effort=effort,
    run_index=run_index,
    cost_usd=cost if isinstance(cost, (int, float)) else 0.0,
    input_tokens=_integer_field(usage, 'input_tokens'),
    output_tokens=_integer_field(usage, 'output_tokens'),
    cache_read_tokens=_integer_field(usage, 'cache_read_input_tokens'),
    cache_creation_tokens=_integer_field(usage, 'cache_creation_input_tokens'),
    turn_count=turns if isinstance(turns, int) else 0,
    wall_seconds=wall_seconds,
    transcription=transcription,
  )


def main() -> None:
  """Cut one scan's strips, read them at each setting, write the results."""
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--image', type=pathlib.Path, required=True)
  parser.add_argument('--output-directory', type=pathlib.Path, required=True)
  parser.add_argument('--models', nargs='+', default=['opus', 'sonnet'])
  parser.add_argument(
    '--efforts', nargs='+', type=Effort, default=[DEFAULT_EFFORT]
  )
  parser.add_argument('--runs', type=int, default=2)
  arguments = parser.parse_args()

  arguments.output_directory.mkdir(parents=True, exist_ok=True)

  # Cut once, outside the run loop: every run reads byte-identical strips. The
  # layout reading costs its own call, and is deliberately not varied with the
  # settings under comparison — the strips are what is being compared.
  dewarped = dewarp_sheet(Image.open(arguments.image))
  structure = read_sheet_structure(dewarped.image)
  geometry = resolve_sheet_geometry(
    dewarped.image, structure.panels, structure.footer
  )
  strips = cut_strips(dewarped.image, geometry)
  print(
    f'cut {len(strips)} strips from {len(geometry.row_boxes)} rows'
    f'{" plus a footer" if geometry.footer else " (this form prints no footer)"}'
  )

  # Keep the strips themselves alongside the runs — judging a disagreement means
  # looking at the same crop the model was given.
  strips_directory = arguments.output_directory / 'strips'
  strips_directory.mkdir(exist_ok=True)
  for index, strip in enumerate(strips):
    (strips_directory / f'{index:02d}.jpg').write_bytes(strip.image_bytes)

  for model in arguments.models:
    for effort in arguments.efforts:
      for run_index in range(1, arguments.runs + 1):
        result = run_once(strips, model, effort, run_index)
        print(
          f'{model} ({result.resolved_model}) at {effort} '
          f'run {run_index}: ${result.cost_usd:.4f}, '
          f'{result.output_tokens} output tokens, '
          f'{result.turn_count} turns, {result.wall_seconds:.0f}s'
        )
        destination = (
          arguments.output_directory
          / f'{model}-{effort}-run{result.run_index}.json'
        )
        destination.write_text(
          json.dumps(dataclasses.asdict(result), indent=2) + '\n'
        )


if __name__ == '__main__':
  main()
