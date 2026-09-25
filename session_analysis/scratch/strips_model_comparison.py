# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Cut a fixed strip set, then read it at each setting and record the cost.

The first two steps of the extraction model comparison — see this directory's
README.md for what the comparison is for and how to run every step.

Every run reads the same strips, so the only variables are the two the command
line sweeps: which model reads them and how much thinking it spends. The strips
are a saved artifact rather than something each sweep cuts afresh. Cutting
rests on the sheet's layout reading, a model call whose answer varies from run
to run, so two sweeps that each cut their own strips compare their arms over
different crops. Instead `cut` saves a set once and every `transcribe` reads a
saved one, letting arms from separate invocations share a single cutting.

Each run's raw transcription, cost, and token counts are written to the output
directory as one JSON file per run, alongside the strip set — judging a
disagreement means looking at the same crop the model was given. A run records
the model that answered as well as the one that was asked for, since the two
differ whenever the request names an alias, and it records which strip set it
read, so the scoring step can refuse to vote runs over different cuttings.
"""

import argparse
import dataclasses
import hashlib
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
from session_analysis.unreviewed.sheet_geometry import (
  SheetGeometry,
  resolve_sheet_geometry,
)
from session_analysis.unreviewed.sheet_structure import read_sheet_structure
from session_analysis.vision_model_invocation import (
  DEFAULT_EFFORT,
  DEFAULT_MODEL,
  Effort,
  LabeledImage,
  invoke_vision_model,
  run_claude,
)

# Where a strip set lives inside an output directory, and the file naming it.
STRIPS_DIRECTORY_NAME = 'strips'
_MANIFEST_NAME = 'manifest.json'


@dataclasses.dataclass(frozen=True)
class StripSet:
  """One cutting of one scan: the strips every run reads, and what cut them.

  The layout reading behind a cutting is itself a model call, so the fields
  describing it mirror a run's own — what was asked for, what answered, and what
  it cost. The geometry is kept alongside the strips so that two cuttings of one
  image can be compared box by box rather than only as same or different.
  """

  source_image: str
  layout_model: str
  layout_resolved_model: str
  layout_effort: str
  layout_cost_usd: float
  geometry: SheetGeometry
  strips: tuple[LabeledImage, ...]

  def digest(self) -> str:
    """A short hash over every strip's label and bytes, naming this cutting.

    Runs record it so the scoring step can tell whether two runs read the same
    crops without comparing images.
    """
    hasher = hashlib.sha256()
    for strip in self.strips:
      hasher.update(strip.label.encode())
      hasher.update(strip.image_bytes)
    return hasher.hexdigest()[:16]


def cut_strip_set(image_path: pathlib.Path, layout_model: str) -> StripSet:
  """Dewarp a scan, read its layout with one model, and cut its strips."""
  runner = _CostRecordingRunner()
  dewarped = dewarp_sheet(Image.open(image_path))
  structure = read_sheet_structure(
    dewarped.image, model=layout_model, run_command=runner
  )
  geometry = resolve_sheet_geometry(
    dewarped.image, structure.panels, structure.footer
  )
  event = _result_event(runner.last_stdout)
  cost = event.get('total_cost_usd')
  return StripSet(
    source_image=str(image_path),
    layout_model=layout_model,
    layout_resolved_model=_resolved_model(runner.last_stdout),
    # `read_sheet_structure` takes no effort of its own, so the layout reading
    # always runs at the invocation default.
    layout_effort=DEFAULT_EFFORT,
    layout_cost_usd=cost if isinstance(cost, (int, float)) else 0.0,
    geometry=geometry,
    strips=tuple(cut_strips(dewarped.image, geometry)),
  )


def write_strip_set(strip_set: StripSet, directory: pathlib.Path) -> None:
  """Save a strip set as its JPEG files plus a manifest describing them."""
  directory.mkdir(parents=True, exist_ok=True)
  entries = []
  for index, strip in enumerate(strip_set.strips):
    file_name = f'{index:02d}.jpg'
    (directory / file_name).write_bytes(strip.image_bytes)
    entries.append(
      {'file': file_name, 'label': strip.label, 'media_type': strip.media_type}
    )
  manifest = {
    'digest': strip_set.digest(),
    'source_image': strip_set.source_image,
    'layout_model': strip_set.layout_model,
    'layout_resolved_model': strip_set.layout_resolved_model,
    'layout_effort': strip_set.layout_effort,
    'layout_cost_usd': strip_set.layout_cost_usd,
    'geometry': json.loads(strip_set.geometry.model_dump_json()),
    'strips': entries,
  }
  (directory / _MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + '\n')


def read_strip_set(directory: pathlib.Path) -> StripSet:
  """Load a strip set that `write_strip_set` saved.

  Raises:
    ValueError: the manifest's recorded digest disagrees with the strips on
      disk — a file was edited or replaced after the set was written.
  """
  manifest = json.loads((directory / _MANIFEST_NAME).read_text())
  strip_set = StripSet(
    source_image=manifest['source_image'],
    layout_model=manifest['layout_model'],
    layout_resolved_model=manifest['layout_resolved_model'],
    layout_effort=manifest['layout_effort'],
    layout_cost_usd=manifest['layout_cost_usd'],
    geometry=SheetGeometry.model_validate(manifest['geometry']),
    strips=tuple(
      LabeledImage(
        label=entry['label'],
        image_bytes=(directory / entry['file']).read_bytes(),
        media_type=entry['media_type'],
      )
      for entry in manifest['strips']
    ),
  )
  if strip_set.digest() != manifest['digest']:
    raise ValueError(
      f'strips in {directory} hash to {strip_set.digest()}, but the manifest'
      f' records {manifest["digest"]}'
    )
  return strip_set


@dataclasses.dataclass(frozen=True)
class RunResult:
  """One run's read of the strips, with what the CLI reported it cost."""

  # What the request asked for, which may be an alias such as `opus`.
  model: str
  # What answered, read back off the stream — a release, never an alias.
  resolved_model: str
  effort: str
  # Which cutting this run read; see `StripSet.digest`.
  strips_digest: str
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
  strip_set: StripSet, model: str, effort: Effort, run_index: int
) -> RunResult:
  """Transcribe the strips once at one model and effort, recording the cost."""
  runner = _CostRecordingRunner()
  started = time.monotonic()
  transcription = invoke_vision_model(
    strip_set.strips,
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
    strips_digest=strip_set.digest(),
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


def _describe(strip_set: StripSet) -> str:
  """One line naming a strip set and what it holds, printed by both commands."""
  geometry = strip_set.geometry
  footer_note = (
    ' plus a footer' if geometry.footer else ' (this form prints no footer)'
  )
  return (
    f'strip set {strip_set.digest()}: {len(strip_set.strips)} strips from'
    f' {len(geometry.row_boxes)} rows{footer_note}, cut by'
    f' {strip_set.layout_resolved_model}'
  )


def cut_command(
  image_path: pathlib.Path,
  layout_model: str,
  output_directory: pathlib.Path,
) -> None:
  """Cut a new strip set from a scan and save it for `transcribe` to read."""
  strips_directory = output_directory / STRIPS_DIRECTORY_NAME
  # A directory holds exactly one cutting, so every sweep that names it reads
  # the same strips.
  if (strips_directory / _MANIFEST_NAME).exists():
    raise SystemExit(
      f'{strips_directory} already holds a strip set; choose another'
      ' --output-directory'
    )
  strip_set = cut_strip_set(image_path, layout_model)
  write_strip_set(strip_set, strips_directory)
  print(_describe(strip_set))


def transcribe_command(
  strips_from: pathlib.Path,
  output_directory: pathlib.Path,
  models: Sequence[str],
  efforts: Sequence[Effort],
  run_count: int,
) -> None:
  """Read a saved strip set at each setting, writing one JSON file per run."""
  strip_set = read_strip_set(strips_from / STRIPS_DIRECTORY_NAME)

  # The runs keep a copy of the strips they read beside them, so an output
  # directory's runs must all have read one set.
  strips_directory = output_directory / STRIPS_DIRECTORY_NAME
  if (strips_directory / _MANIFEST_NAME).exists():
    existing_digest = read_strip_set(strips_directory).digest()
    if existing_digest != strip_set.digest():
      raise SystemExit(
        f'{strips_directory} already holds strip set {existing_digest}, not'
        f' {strip_set.digest()}; runs over two cuttings cannot share a'
        ' directory'
      )
  else:
    write_strip_set(strip_set, strips_directory)
  print(_describe(strip_set))

  for model in models:
    for effort in efforts:
      for run_index in range(1, run_count + 1):
        result = run_once(strip_set, model, effort, run_index)
        print(
          f'{model} ({result.resolved_model}) at {effort} '
          f'run {run_index}: ${result.cost_usd:.4f}, '
          f'{result.output_tokens} output tokens, '
          f'{result.turn_count} turns, {result.wall_seconds:.0f}s'
        )
        destination = (
          output_directory / f'{model}-{effort}-run{result.run_index}.json'
        )
        destination.write_text(
          json.dumps(dataclasses.asdict(result), indent=2) + '\n'
        )


def main() -> None:
  """Parse the command line and run `cut` or `transcribe`."""
  parser = argparse.ArgumentParser(description=__doc__)
  commands = parser.add_subparsers(dest='command', required=True)

  cut_parser = commands.add_parser(
    'cut', help='cut a new strip set from a scan and save it'
  )
  cut_parser.add_argument('--image', type=pathlib.Path, required=True)
  cut_parser.add_argument(
    '--layout-model',
    default=DEFAULT_MODEL,
    help='the model whose layout reading cuts the strips (default: '
    '%(default)s)',
  )
  cut_parser.add_argument(
    '--output-directory', type=pathlib.Path, required=True
  )

  transcribe_parser = commands.add_parser(
    'transcribe', help='read a saved strip set at each setting'
  )
  transcribe_parser.add_argument(
    '--strips-from',
    type=pathlib.Path,
    required=True,
    help='a directory that `cut` or an earlier `transcribe` wrote',
  )
  transcribe_parser.add_argument(
    '--output-directory', type=pathlib.Path, required=True
  )
  transcribe_parser.add_argument(
    '--models', nargs='+', default=['opus', 'sonnet']
  )
  transcribe_parser.add_argument(
    '--efforts', nargs='+', type=Effort, default=[DEFAULT_EFFORT]
  )
  transcribe_parser.add_argument(
    '--runs', type=int, default=2, help='runs per setting'
  )
  arguments = parser.parse_args()

  if arguments.command == 'cut':
    cut_command(
      arguments.image, arguments.layout_model, arguments.output_directory
    )
  else:
    transcribe_command(
      arguments.strips_from,
      arguments.output_directory,
      arguments.models,
      arguments.efforts,
      arguments.runs,
    )


if __name__ == '__main__':
  main()
