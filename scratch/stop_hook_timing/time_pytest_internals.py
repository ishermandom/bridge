# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Split the hook's pytest run below the timeline plugin's phases.

Each run is `run_tests.sh`'s pytest invocation alone:

- as it is, interleaved with a variant that ends the process with `os._exit`
  after the last exit handler, so their difference is Python's own shutdown
- once more with `PYTHONPROFILEIMPORTTIME`, for the time each phase spends
  importing, by standard library, third-party and project code, and by top-level
  package
- a few times with the collection sampler, for where collection's time goes
  besides imports: pytest's own work, the test modules' own top-level code,
  loading the test modules, and subprocesses

Usage, from the repo root: python3 -m
scratch.stop_hook_timing.time_pytest_internals ROUNDS
"""

import itertools
import json
import re
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path

from scratch.stop_hook_timing.attribute_hook_runs import Timeline
from scratch.stop_hook_timing.hook_commands import (
  OUT,
  PYTEST,
  REPO_ROOT,
  base_environment,
  plugin_environment,
)

RUNS = OUT / 'pytest_internals'
_IMPORT_LINE = re.compile(r'import time:\s+(\d+) \|\s+(\d+) \|( *)(\S+)')
# The timeline plugin's marker lines, and the phase each one begins.
_PHASE_MARKERS = {
  'TIMELINE-PLUGIN-IMPORTED': 'configure and conftests',
  'TIMELINE-COLLECTION-STARTED': 'collection',
  'TIMELINE-COLLECTION-FINISHED': 'tests',
  'TIMELINE-TESTS-FINISHED': 'after tests',
}
_SEGMENTS = (
  ('spawn', 'plugin_imported'),
  ('plugin_imported', 'configure'),
  ('configure', 'collection_start'),
  ('collection_start', 'collection_finish'),
  ('collection_finish', 'loop_start'),
  ('loop_start', 'loop_end'),
  ('loop_end', 'sessionfinish'),
  ('sessionfinish', 'summary_start'),
  ('summary_start', 'summary_end'),
  ('summary_end', 'unconfigure'),
  ('unconfigure', 'last_atexit'),
  ('last_atexit', 'exit'),
  ('spawn', 'exit'),
)


def _run(
  label: str,
  extra: Mapping[str, str],
  plugins: tuple[str, ...] = (),
  arguments: tuple[str, ...] = (),
) -> tuple[Timeline, str]:
  """Runs pytest once, as `label`; returns its timeline and standard error.

  The timeline's marks gain the launcher's `spawn` and `exit`.
  """
  environment = base_environment()
  environment.update(plugin_environment(RUNS / f'{label}.json', plugins))
  environment.update(extra)
  spawn = time.time()
  completed = subprocess.run(
    (*PYTEST, *arguments),
    cwd=REPO_ROOT,
    env=environment,
    capture_output=True,
    text=True,
    stdin=subprocess.DEVNULL,
  )
  exit_ = time.time()
  if completed.returncode != 0:
    print(f'{label}: status {completed.returncode}\n{completed.stdout[-1500:]}')
  timeline: Timeline = json.loads((RUNS / f'{label}.json').read_text())
  timeline['marks'].update({'spawn': spawn, 'exit': exit_})
  return timeline, completed.stderr


def time_shutdown(rounds: int) -> None:
  """Prints each phase's mean as is and with `os._exit`, and garbage collection
  by phase.
  """
  variants = {'as is': {}, 'os._exit': {'TIMELINE_FAST_EXIT': '1'}}
  timelines: dict[str, list[Timeline]] = defaultdict(list)
  _run('warm', {})
  for round_number in range(rounds):
    for name, extra in variants.items():
      timeline, _ = _run(f'{name}-{round_number}', extra)
      timelines[name].append(timeline)
  print(f'pytest alone, mean ms per segment ({" | ".join(variants)}):')
  for start, end in _SEGMENTS:
    cells = [
      statistics.mean(
        timeline['marks'][end] - timeline['marks'][start]
        for timeline in timelines[name]
      )
      * 1000
      for name in variants
    ]
    print(f'  {cells[0]:7.1f} | {cells[1]:7.1f}  {start} -> {end}')
  by_phase: dict[str, list[float]] = defaultdict(list)
  for timeline in timelines['as is']:
    for phase, seconds in timeline['gc_by_phase'].items():
      by_phase[phase].append(seconds * 1000)
  print(
    'garbage collection by phase, mean ms: '
    + ', '.join(
      f'{phase} {statistics.mean(values):.1f}'
      for phase, values in by_phase.items()
    )
  )


def _kind_of(path: str | None) -> str:
  if path is None:
    return 'standard library'
  if '/site-packages/' in path:
    return 'third-party'
  if path.startswith(str(REPO_ROOT)):
    return 'project'
  return 'standard library'


def time_imports() -> None:
  """Prints each phase's import time, by kind and by top-level package."""
  modules_path = RUNS / 'modules.json'
  timeline, stderr = _run(
    'importtime',
    {
      'PYTHONPROFILEIMPORTTIME': '1',
      'PYTEST_ADDOPTS': '--tb=short -s',
      'TIMELINE_MODULES_OUT': str(modules_path),
    },
  )
  origins: dict[str, str | None] = json.loads(modules_path.read_text())
  marks = timeline['marks']
  collection = marks['collection_finish'] - marks['collection_start']
  print(
    'imports by phase (PYTHONPROFILEIMPORTTIME, -s), self time; this run '
    f'collected in {collection * 1000:.0f}ms'
  )
  phase = 'start-up'
  by_phase: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
  for line in stderr.splitlines():
    for marker, name in _PHASE_MARKERS.items():
      if marker in line:
        phase = name
    match = _IMPORT_LINE.match(line)
    if match:
      by_phase[phase][match.group(4)] += int(match.group(1))
  for phase, selves in by_phase.items():
    kinds: dict[str, int] = defaultdict(int)
    packages: dict[str, int] = defaultdict(int)
    for name, microseconds in selves.items():
      kinds[_kind_of(origins.get(name))] += microseconds
      packages[name.split('.')[0]] += microseconds
    total = sum(selves.values())
    print(
      f'  {phase}: {total / 1000:.0f}ms in {len(selves)} imports; '
      + ', '.join(
        f'{kind} {value / 1000:.0f}ms' for kind, value in sorted(kinds.items())
      )
    )
    top = sorted(packages.items(), key=lambda item: -item[1])[:12]
    print(
      '    top packages: '
      + ', '.join(f'{package} {value / 1000:.0f}' for package, value in top)
    )


def _package_of(path: str) -> str:
  if '/site-packages/' in path:
    return path.split('/site-packages/')[1].split('/')[0]
  if path.startswith(str(REPO_ROOT)):
    return 'project:' + path[len(str(REPO_ROOT)) + 1 :].split('/')[0]
  return 'standard library'


def _classify(stack: Sequence[Sequence[str]]) -> tuple[str, str]:
  """A category and a detail for one sampled stack, innermost frame first."""
  files = [frame[0] for frame in stack]
  names = [frame[1] for frame in stack]
  if any('subprocess.py' in file for file in files):
    return 'subprocesses', ''
  # The outermost test module's own code, if any: the module being loaded.
  test_body = next(
    (
      index
      for index in range(len(stack) - 1, -1, -1)
      if files[index].endswith('_test.py') and names[index] == '<module>'
    ),
    None,
  )
  if test_body is not None:
    inner = stack[:test_body]
    if any(frame[1] == '_find_and_load' for frame in inner):
      # Charge an import to the package whose module code is running.
      body = next((frame[0] for frame in inner if frame[1] == '<module>'), '?')
      return 'imports made by test modules', _package_of(body)
    location = files[test_body].removeprefix(f'{REPO_ROOT}/')
    return "test modules' own top-level code", location
  if any('assertion/rewrite.py' in file for file in files):
    return 'loading test modules (assertion rewriting, bytecode)', ''
  if '_find_and_load' in names:
    return 'other imports', ''
  for file, name in stack:
    if '/_pytest/' in file:
      return "pytest's own work", f'{file.split("/_pytest/")[-1]}:{name}'
    if '/pluggy/' in file:
      return "pytest's own work", f'pluggy:{name}'
  if not stack:
    return 'other', ''
  return 'other', f'{Path(files[0]).name}:{names[0]}'


def sample_collection(runs: int) -> None:
  """Prints where collection's time goes, by category, from `runs` sampled
  collect-only runs; each sample counts for the time since the one before.
  """
  samples_path = RUNS / 'collection_samples.json'
  totals: dict[str, list[float]] = defaultdict(list)
  details: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
  for run_number in range(runs):
    _run(
      f'sampled-{run_number}',
      {'SAMPLER_OUT': str(samples_path)},
      plugins=('collection_sampler',),
      arguments=('--collect-only', '-q'),
    )
    samples: list[tuple[float, list[list[str]]]] = json.loads(
      samples_path.read_text()
    )
    run_totals: dict[str, float] = defaultdict(float)
    for (before, _), (now, stack) in itertools.pairwise(samples):
      category, detail = _classify(stack)
      run_totals[category] += now - before
      details[category][detail] += (now - before) / runs
    run_totals['= collection wall (sampled)'] = samples[-1][0] - samples[0][0]
    for category, seconds in run_totals.items():
      totals[category].append(seconds)
  print('collection, sampled:')
  for category, values in sorted(
    totals.items(), key=lambda item: -statistics.mean(item[1])
  ):
    print(f'  {statistics.mean(values) * 1000:7.1f}ms  {category}')
    top = sorted(details[category].items(), key=lambda item: -item[1])[:10]
    for detail, seconds in top:
      if detail and seconds >= 0.001:
        print(f'             {seconds * 1000:6.1f}  {detail}')


def main(rounds: int) -> None:
  """Runs every split."""
  RUNS.mkdir(parents=True, exist_ok=True)
  time_shutdown(rounds)
  time_imports()
  sample_collection(4)


if __name__ == '__main__':
  main(int(sys.argv[1]))
