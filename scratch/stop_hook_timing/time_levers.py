# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Time candidate levers on the hook's pytest run, round-robin, and check that
each still passes every selected test.

The variants, each against pytest as the hook runs it:

- pytest's debugging plugin left on
- the test files whose every test the hook deselects left out, found by
  collecting with and without `-m "not slow"`
- garbage collection paused while pytest collects, then frozen, with and without
  one full collection just before the freeze (`plugins/gc_variants.py`)
- the JavaScript checks running beside pytest at each priority and vitest worker
  setting tried, with when they finish against pytest

Before the timed rounds, a diagnostic run of each freeze variant reports how
many objects collection leaves tracked, how many of them are garbage, and how
many are frozen. Every timed run reports its peak memory.

Usage, from the repo root: python3 -m scratch.stop_hook_timing.time_levers
ROUNDS
"""

import json
import re
import shlex
import statistics
import subprocess
import sys
import threading
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from scratch.stop_hook_timing.attribute_hook_runs import Timeline
from scratch.stop_hook_timing.hook_commands import (
  OUT,
  PYTEST,
  REPO_ROOT,
  TSC,
  VITEST,
  base_environment,
  plugin_environment,
)

RUNS = OUT / 'levers'
_PEAK = re.compile(r'GC-PEAK ([\d.]+)MiB')
_SEGMENTS = (
  ('start', 'spawn', 'collection_start'),
  ('collection', 'collection_start', 'collection_finish'),
  ('test loop', 'loop_start', 'loop_end'),
  ('end', 'loop_end', 'exit'),
  ('total', 'spawn', 'exit'),
)


@dataclass(frozen=True)
class Variant:
  """One way to run pytest, and whether the JavaScript checks run beside it.

  `javascript_wrapper` prefixes the checks' shell command, such as `taskpolicy
  -c utility `; None leaves the checks out entirely.
  """

  command: tuple[str, ...] = PYTEST
  environment: Mapping[str, str] = field(default_factory=dict)
  javascript_wrapper: str | None = None
  vitest_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class Result:
  """One timed run."""

  marks: Mapping[str, float]
  gc_seconds: float
  peak_mebibytes: float
  summary: str
  javascript_seconds: float | None
  step_seconds: float


def _without(command: Sequence[str], *pair: str) -> tuple[str, ...]:
  """`command` less the adjacent words `pair`."""
  words = list(command)
  for index in range(len(words) - 1):
    if tuple(words[index : index + 2]) == pair:
      return (*words[:index], *words[index + 2 :])
  raise ValueError(f'{pair} not in {command}')


def _collected_files(command: Sequence[str]) -> dict[str, int]:
  """Each test file `command` collects, with its count of collected tests."""
  completed = subprocess.run(
    (*command, '--collect-only', '-q'),
    cwd=REPO_ROOT,
    env={**base_environment(), 'PYTEST_ADDOPTS': '--tb=short'},
    capture_output=True,
    text=True,
    check=True,
  )
  counts: dict[str, int] = defaultdict(int)
  for line in completed.stdout.splitlines():
    if '::' in line:
      counts[line.split('::')[0]] += 1
  return counts


def _fully_deselected() -> tuple[str, ...]:
  """`--ignore` arguments for the files whose every test the hook deselects."""
  selected = _collected_files(PYTEST)
  every = _collected_files(_without(PYTEST, '-m', 'not slow'))
  files = sorted(name for name in every if name not in selected)
  print(f'test files whose every test is deselected: {", ".join(files)}')
  return tuple(f'--ignore=./{name}' for name in files)


def _variants() -> dict[str, Variant]:
  freeze = {'GC_VARIANT': 'freeze'}
  collect_freeze = {'GC_VARIANT': 'collect_freeze'}
  one_by_one = ('--no-file-parallelism',)
  return {
    'as the hook runs it': Variant(),
    'debugging plugin left on': Variant(
      command=_without(PYTEST, '-p', 'no:debugging')
    ),
    'fully deselected files left out': Variant(
      command=(*PYTEST, *_fully_deselected())
    ),
    'gc paused, then frozen': Variant(environment=freeze),
    'gc paused, collected once, then frozen': Variant(
      environment=collect_freeze
    ),
    'JavaScript beside it': Variant(javascript_wrapper=''),
    'JavaScript beside it, nice -n 20': Variant(
      javascript_wrapper='nice -n 20 '
    ),
    'JavaScript beside it, taskpolicy -c utility': Variant(
      javascript_wrapper='taskpolicy -c utility '
    ),
    'JavaScript beside it, taskpolicy -c background': Variant(
      javascript_wrapper='taskpolicy -c background '
    ),
    'JavaScript beside it, taskpolicy -b': Variant(
      javascript_wrapper='taskpolicy -b '
    ),
    'JavaScript beside it, vitest --maxWorkers=1': Variant(
      javascript_wrapper='', vitest_flags=('--maxWorkers=1',)
    ),
    'JavaScript beside it, vitest --no-file-parallelism': Variant(
      javascript_wrapper='', vitest_flags=one_by_one
    ),
    'JavaScript beside it, utility and --no-file-parallelism': Variant(
      javascript_wrapper='taskpolicy -c utility ', vitest_flags=one_by_one
    ),
  }


def _run(label: str, variant: Variant, diagnose: bool = False) -> Result:
  """Runs `variant` once, as `label`."""
  environment = base_environment()
  environment.update(
    plugin_environment(RUNS / f'{label}.json', plugins=('gc_variants',))
  )
  environment.update(variant.environment)
  if diagnose:
    environment['GC_DIAGNOSE'] = '1'

  javascript_times: dict[str, float] = {}
  watcher = None
  if variant.javascript_wrapper is not None:
    checks = (
      f'{shlex.join(TSC)} && {shlex.join((*VITEST, *variant.vitest_flags))}'
    )
    javascript_times['start'] = time.time()
    javascript = subprocess.Popen(
      f'{variant.javascript_wrapper}sh -c {shlex.quote(checks)}',
      shell=True,
      cwd=REPO_ROOT,
      stdout=subprocess.DEVNULL,
      stderr=subprocess.DEVNULL,
    )

    # Notes when the checks finish, which may be before or after pytest does.
    def note_end() -> None:
      javascript.wait()
      javascript_times['end'] = time.time()

    watcher = threading.Thread(target=note_end)
    watcher.start()

  spawn = time.time()
  completed = subprocess.run(
    variant.command,
    cwd=REPO_ROOT,
    env=environment,
    capture_output=True,
    text=True,
    stdin=subprocess.DEVNULL,
  )
  exit_ = time.time()
  if watcher is not None:
    watcher.join()

  summary = completed.stdout.strip().splitlines()[-1]
  if completed.returncode != 0:
    print(f'{label}: status {completed.returncode}: {summary}')
  if diagnose:
    print(
      f'{label}: '
      + '; '.join(
        line.removeprefix('GC-')
        for line in completed.stderr.splitlines()
        if line.startswith('GC-')
      )
    )
  timeline: Timeline = json.loads((RUNS / f'{label}.json').read_text())
  peak = _PEAK.search(completed.stderr)
  javascript_seconds = None
  if 'end' in javascript_times:
    javascript_seconds = javascript_times['end'] - javascript_times['start']
  # The test step waits for whichever side finishes last.
  step_start = javascript_times.get('start', spawn)
  step_end = max(exit_, javascript_times.get('end', exit_))
  return Result(
    marks={**timeline['marks'], 'spawn': spawn, 'exit': exit_},
    gc_seconds=sum(timeline['gc_by_phase'].values()),
    peak_mebibytes=float(peak.group(1)) if peak else 0.0,
    summary=summary,
    javascript_seconds=javascript_seconds,
    step_seconds=step_end - step_start,
  )


def main(rounds: int) -> None:
  """Times every variant `rounds` times, interleaved, after an untimed run of
  each and the freeze variants' diagnostics.
  """
  RUNS.mkdir(parents=True, exist_ok=True)
  variants = _variants()
  for name in (
    'gc paused, then frozen',
    'gc paused, collected once, then frozen',
  ):
    _run(f'diagnose {name}', variants[name], diagnose=True)
  for name, variant in variants.items():
    _run(f'warm {name}', variant)
  results: dict[str, list[Result]] = defaultdict(list)
  for round_number in range(rounds):
    for name, variant in variants.items():
      results[name].append(_run(f'{name} {round_number}', variant))

  print(f'means over {rounds} rounds (ms, peak memory in MiB)')
  print(
    f'{"":56}'
    + ''.join(f'{segment:>12}' for segment, _, _ in _SEGMENTS)
    + f'{"gc":>8}{"peak":>8}'
  )
  for name, runs in results.items():
    cells = [
      statistics.mean(run.marks[end] - run.marks[start] for run in runs) * 1000
      for _, start, end in _SEGMENTS
    ]
    gc_total = statistics.mean(run.gc_seconds for run in runs) * 1000
    peak = statistics.mean(run.peak_mebibytes for run in runs)
    print(
      f'{name:56}'
      + ''.join(f'{cell:12.1f}' for cell in cells)
      + f'{gc_total:8.1f}{peak:8.1f}'
    )
  for name, runs in results.items():
    finishes = [
      run.javascript_seconds for run in runs if run.javascript_seconds
    ]
    detail = ''
    if finishes:
      detail = (
        f"; the checks' own run {statistics.mean(finishes) * 1000:.0f}ms, "
        'whole step '
        f'{statistics.mean(run.step_seconds for run in runs) * 1000:.0f}ms'
      )
    print(f'{name}: {runs[0].summary}{detail}')


if __name__ == '__main__':
  main(int(sys.argv[1]))
