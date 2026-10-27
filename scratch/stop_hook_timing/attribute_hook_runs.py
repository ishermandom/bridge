# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Attribute every millisecond of the traced Stop hook runs `time_hook` wrote.

Each traced run yields one ordered list of timestamped events: the launcher's
spawn, every bash command in the chain, pytest's phase marks, and the launcher's
view of the exit. Consecutive events split the run into back-to-back segments,
and each segment is charged to the event that began it: the command bash was
about to run, or the pytest phase that had begun. The JavaScript checks run in
the background beside pytest, so their events are kept out of that sequence.

Rows are grouped as step, then script, then item, and averaged across rounds.
Means are used because they add up: the rows' means sum exactly to the total's.
Rounds slower than `QUIET_FACTOR` times the fastest are dropped whole, since
other load on the machine most likely slowed them.

Also reports pytest's phases in the hook against pytest alone, garbage
collection by phase, the test loop's makeup, and the tests' own time by file.

Usage, from the repo root: python3 -m
scratch.stop_hook_timing.attribute_hook_runs
"""

import itertools
import json
import re
import statistics
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import TypedDict

from scratch.stop_hook_timing.time_hook import RUNS

QUIET_FACTOR = 1.05

_TRACE_LINE = re.compile(r'^(\++)(\d+\.\d+) (\d+) (\S+?):(\d+) (.*)$')
_PYTEST_MARKS = (
  'plugin_imported',
  'configure',
  'collection_start',
  'collection_finish',
  'loop_start',
  'loop_end',
  'sessionfinish',
  'summary_start',
  'summary_end',
  'unconfigure',
  'last_atexit',
)
# What the segment after each pytest event is spent on.
_PYTEST_PHASES = {
  'launch': 'start: uv, interpreter, pytest import, preparse',
  'plugin_imported': 'initial conftests, plugin setup',
  'configure': 'configure to collection start',
  'collection_start': 'collection',
  'collection_finish': 'collection end to test loop',
  'loop_start': 'test loop',
  'loop_end': 'loop end to session finish',
  'sessionfinish': 'session finish (incl. tmp cleanup) to summary',
  'summary_start': 'terminal summary',
  'summary_end': 'summary to unconfigure',
  'unconfigure': 'unconfigure to last atexit',
  'last_atexit': 'interpreter shutdown, uv exit',
}
# The hook's checks, each run from `stop_checks.sh` and ending when the
# assignment that captures its output does.
_STEPS = (
  ('format.sh', 'breakage='),
  ('mypy-check.sh', 'failure='),
  ('run_tests.sh', 'failure='),
  ('ruff-lint.sh', 'failure='),
)
_STEP_ORDER = (
  'launch and exit',
  'stop_checks.sh glue',
  'format.sh',
  'is-third-party-repo.sh',
  'mypy-check.sh',
  'run_tests.sh',
  'ruff-lint.sh',
)
_SINGLE_PROGRAMS = {
  'readlink',
  'dirname',
  'realpath',
  'mktemp',
  'md5',
  'tail',
  'cat',
  'rm',
  'mkdir',
  'wait',
}
_GLUE = 'bash: builtins, forks for $(...)'


class Timeline(TypedDict):
  """What the timeline plugin writes."""

  marks: dict[str, float]
  gc_by_phase: dict[str, float]
  reports: dict[str, dict[str, float]]
  protocol: dict[str, float]


class LauncherRecord(TypedDict):
  """What `time_hook` writes for each run."""

  wall: float
  spawn: float
  exit: float
  passed: bool
  load: float


@dataclass
class Event:
  """One timestamped point in a traced run.

  `source` is the script a traced command sits in, `pytest` for a phase mark, or
  `launcher` for the run's spawn and exit. `step`, `script` and `format_pass`
  are filled in once the run's events are in order.
  """

  timestamp: float
  source: str
  command: str
  pid: int = 0
  step: str = ''
  script: str = ''
  format_pass: str = ''


@dataclass(frozen=True)
class TracedRun:
  """One traced run's launcher record, timeline and command trace."""

  label: str
  record: LauncherRecord
  timeline: Timeline
  trace: list[Event]


def milliseconds(seconds: float) -> str:
  """`seconds` as milliseconds, right-aligned for a column."""
  return f'{seconds * 1000:7.1f}'


def read_trace(label: str) -> list[Event]:
  """The traced commands of run `label`, in the order bash wrote them."""
  events = []
  for line in (RUNS / f'{label}.xtrace').read_text().splitlines():
    match = _TRACE_LINE.match(line)
    if match:
      events.append(
        Event(
          timestamp=float(match.group(2)),
          pid=int(match.group(3)),
          source=match.group(4),
          command=match.group(6),
        )
      )
  return events


def is_background(event: Event) -> bool:
  """Whether `event` belongs to the JavaScript checks beside pytest.

  The checks may run under a wrapper such as `taskpolicy`, so any word naming a
  Node tool marks them.
  """
  words = event.command.split(' ')
  return event.source == 'run_tests.sh' and (
    any('/node_modules/.bin/' in word for word in words)
    or event.command == 'realpath ./club_sites/palo_alto'
  )


def item_label(event: Event) -> str:
  """What the segment after `event` was spent on."""
  if event.source == 'pytest':
    return 'pytest: ' + _PYTEST_PHASES[event.command]
  words = event.command.split(' ')
  program = words[0].split('/')[-1]
  if '=' in words[0]:
    return _GLUE
  if program.endswith('.sh'):
    return f'start {program}'
  if program == 'uv':
    position = words.index('--with') + 2 if '--with' in words else 4
    tool = words[position]
    if tool == 'pytest':
      return 'pytest: ' + _PYTEST_PHASES['launch']
    rest = [word for word in words[position + 1 :] if not word.startswith('/')]
    return f'uv run {tool} {" ".join(rest)}'.rstrip()
  if program == 'git':
    subcommand = [
      word
      for word in words[1:]
      if not word.startswith('-') and not word.startswith('/')
    ][:1]
    flag = words[-1] if words[-1].startswith('--') else ''
    return f'git {" ".join(subcommand)} {flag}'.strip()
  if program == 'prettier':
    if '--find-config-path' in words:
      return 'prettier --find-config-path'
    return 'prettier --write'
  if program == 'find':
    pattern = next((word for word in words if '*.' in word), '?')
    return f'find {pattern.strip(chr(39))}'
  if program in ('exit', 'return'):
    return 'script exit, back to caller'
  if program in _SINGLE_PROGRAMS:
    return program
  return _GLUE


def critical_path(run: TracedRun) -> list[Event]:
  """The run's events in time order, less the background checks."""
  events = [event for event in run.trace if not is_background(event)]
  events.extend(
    Event(timestamp=run.timeline['marks'][mark], source='pytest', command=mark)
    for mark in _PYTEST_MARKS
  )
  events.sort(key=lambda event: event.timestamp)
  events.insert(
    0, Event(timestamp=run.record['spawn'], source='launcher', command='spawn')
  )
  events.append(
    Event(timestamp=run.record['exit'], source='launcher', command='exit')
  )
  return events


def assign_steps(events: Sequence[Event]) -> None:
  """Labels each event with the hook step and the script it belongs to."""
  step = 'stop_checks.sh glue'
  pending_end = ''
  is_bridge_tests = False
  format_pass = ''
  for event in events:
    source, command = event.source, event.command
    if source == 'format.sh' and command.startswith('cd '):
      format_pass = 'bridge' if '/bridge/' in command else 'dotfiles'
    if source == 'stop_checks.sh':
      format_pass = ''
      for script, end in _STEPS:
        if command.endswith('/' + script):
          step, pending_end = script, end
      if pending_end and command.startswith(pending_end):
        event.step = 'stop_checks.sh glue'
        step, pending_end = 'stop_checks.sh glue', ''
      elif 'is-third-party-repo.sh' in command:
        step = 'is-third-party-repo.sh'
      elif command.startswith('for check'):
        step = 'stop_checks.sh glue'
    event.format_pass = format_pass
    if source == 'quiet-tests.sh' and command == './run_tests.sh':
      is_bridge_tests = True
    if source == 'quiet-tests.sh' and command.startswith('output='):
      is_bridge_tests = False
    if source == 'launcher':
      event.step = 'launch and exit'
    elif not event.step:
      event.step = step
    script = source
    if source == 'run_tests.sh':
      script = (
        'bridge run_tests.sh' if is_bridge_tests else 'hooks/run_tests.sh'
      )
    if source in ('quiet-prettier.sh', 'quiet-ruff.sh') and format_pass:
      script = f'{source} ({format_pass})'
    event.script = script


def attribute(events: Sequence[Event]) -> dict[tuple[str, str, str], float]:
  """Each segment's length, keyed by step, script and item."""
  rows: dict[tuple[str, str, str], float] = defaultdict(float)
  for current, following in itertools.pairwise(events):
    gap = following.timestamp - current.timestamp
    label = item_label(current)
    script = current.script
    if label.startswith('start '):
      # A script's startup belongs to the script being started.
      script = label.split(' ')[1]
      if script == 'run_tests.sh':
        script = (
          'bridge run_tests.sh'
          if current.source == 'quiet-tests.sh'
          else 'hooks/run_tests.sh'
        )
      if script in ('quiet-prettier.sh', 'quiet-ruff.sh'):
        script = f'{script} ({current.format_pass})'
      label = 'bash startup (fork, exec, init)'
    if current.source == 'launcher' and current.command == 'spawn':
      label = 'launch stop_checks.sh (fork, exec, bash startup)'
      script = 'stop_checks.sh'
    if label.startswith('pytest: '):
      script = 'pytest'
    if following.source == 'launcher':
      label = 'stop_checks.sh exit, launcher sees it'
      script = 'stop_checks.sh'
    rows[(current.step, script, label)] += gap
  return rows


def load_records(variant: str) -> list[tuple[str, LauncherRecord]]:
  """Every record of `variant`, with its label, the untimed round left out."""
  records = []
  for path in sorted(RUNS.glob(f'{variant}-[0-9]*.json')):
    if path.name.endswith('.timeline.json'):
      continue
    record: LauncherRecord = json.loads(path.read_text())
    records.append((path.stem, record))
  return records


def load_timeline(label: str) -> Timeline:
  """The timeline run `label` wrote."""
  timeline: Timeline = json.loads((RUNS / f'{label}.timeline.json').read_text())
  return timeline


def quiet(
  records: Sequence[tuple[str, LauncherRecord]],
) -> list[tuple[str, LauncherRecord]]:
  """The rounds no slower than `QUIET_FACTOR` times the fastest."""
  fastest = min(record['wall'] for _, record in records)
  kept = [
    (label, record)
    for label, record in records
    if record['wall'] <= QUIET_FACTOR * fastest
  ]
  walls = ' '.join(
    f'{record["wall"] * 1000:.0f}'
    + ('' if record['wall'] <= QUIET_FACTOR * fastest else 'x')
    + f'(load {record["load"]:.1f})'
    for _, record in records
  )
  print(f'  kept {len(kept)} of {len(records)} rounds; walls {walls}')
  return kept


def summarize(name: str, walls: Sequence[float]) -> None:
  """Prints the mean, median and range of `walls`."""
  print(
    f'{name}: n={len(walls)} mean {milliseconds(statistics.mean(walls))} '
    f'median {milliseconds(statistics.median(walls))} '
    f'min {milliseconds(min(walls))} max {milliseconds(max(walls))}'
  )


def print_rows(
  per_run_rows: Sequence[Mapping[tuple[str, str, str], float]],
) -> None:
  """Prints the step, script and item means, with each item's range."""
  keys = sorted({key for rows in per_run_rows for key in rows})
  by_step: dict[str, list[tuple[str, str, list[float]]]] = defaultdict(list)
  for step, script, label in keys:
    values = [rows.get((step, script, label), 0.0) for rows in per_run_rows]
    by_step[step].append((script, label, values))
  grand = 0.0
  for step in _STEP_ORDER:
    items = by_step.get(step, [])
    step_mean = sum(statistics.mean(values) for _, _, values in items)
    grand += step_mean
    print(f'\n{milliseconds(step_mean)}ms  STEP {step}')
    by_script: dict[str, list[tuple[str, list[float]]]] = defaultdict(list)
    for script, label, values in items:
      by_script[script].append((label, values))
    for script, entries in sorted(
      by_script.items(),
      key=lambda item: -sum(statistics.mean(values) for _, values in item[1]),
    ):
      script_mean = sum(statistics.mean(values) for _, values in entries)
      print(f'  {milliseconds(script_mean)}ms  {script}')
      for label, values in sorted(
        entries, key=lambda entry: -statistics.mean(entry[1])
      ):
        print(
          f'    {milliseconds(statistics.mean(values))}ms  {label}'
          f'   [min {milliseconds(min(values)).strip()}, '
          f'max {milliseconds(max(values)).strip()}]'
        )
  print(f'\n{milliseconds(grand)}ms  total (sum of row means)')


def pytest_phases(timeline: Timeline, start: float) -> dict[str, float]:
  """Each pytest phase's length, from `start` through the exit handler."""
  points = [('start', start)] + [
    (mark, timeline['marks'][mark]) for mark in _PYTEST_MARKS
  ]
  return {
    name: following - current
    for (name, current), (_, following) in itertools.pairwise(points)
  }


def print_phase_comparison(
  in_hook: Sequence[Mapping[str, float]], alone: Sequence[Mapping[str, float]]
) -> None:
  """Prints pytest's phases in the hook against pytest alone."""
  print('\npytest phases: in the hook vs alone (mean ms), and the difference')
  for name in in_hook[0]:
    hook_mean = statistics.mean(phases[name] for phases in in_hook)
    alone_mean = statistics.mean(phases[name] for phases in alone)
    print(
      f'  {milliseconds(hook_mean)}  {milliseconds(alone_mean)}  '
      f'{milliseconds(hook_mean - alone_mean)}  after {name}'
    )


def print_garbage_collection(timelines: Iterable[Timeline]) -> None:
  """Prints garbage-collection pauses by phase."""
  by_phase: dict[str, list[float]] = defaultdict(list)
  for timeline in timelines:
    for phase, seconds in timeline['gc_by_phase'].items():
      by_phase[phase].append(seconds)
  print(
    '\ngarbage collection by phase (mean ms): '
    + ', '.join(
      f'{phase} {milliseconds(statistics.mean(values)).strip()}'
      for phase, values in by_phase.items()
    )
  )


def _project(nodeid: str) -> str:
  parts = nodeid.lstrip('./').split('/')
  if parts[0] in ('club_sites', 'practice'):
    return '/'.join(parts[:2])
  return parts[0]


def print_test_loop(timelines: Sequence[Timeline]) -> None:
  """Prints the test loop's makeup: the tests' own time by project, pytest's
  work around each test, and time outside any test.
  """
  rows: dict[str, list[float]] = defaultdict(list)
  for timeline in timelines:
    marks = timeline['marks']
    loop = marks['loop_end'] - marks['loop_start']
    protocol = sum(timeline['protocol'].values())
    by_project: dict[str, float] = defaultdict(float)
    for nodeid, phases in timeline['reports'].items():
      by_project[_project(nodeid)] += sum(phases.values())
    for project, seconds in by_project.items():
      rows[f"tests' own setup+call+teardown: {project}"].append(seconds)
    reported = sum(by_project.values())
    rows['pytest per-test machinery (protocol - reported)'].append(
      protocol - reported
    )
    rows["loop outside any test's protocol"].append(loop - protocol)
    rows['= loop wall'].append(loop)
  print(f'\ntest loop (mean ms), {len(timelines[0]["protocol"])} tests:')
  for label, values in sorted(
    rows.items(), key=lambda item: -statistics.mean(item[1])
  ):
    print(f'  {milliseconds(statistics.mean(values))}  {label}')


def print_tests_by_file(timelines: Sequence[Timeline], shown: int = 12) -> None:
  """Prints the tests' own time by file, the costliest `shown` first."""
  by_file: dict[str, list[float]] = defaultdict(list)
  for timeline in timelines:
    totals: dict[str, float] = defaultdict(float)
    for nodeid, phases in timeline['reports'].items():
      totals[nodeid.split('::')[0].lstrip('./')] += sum(phases.values())
    for name, seconds in totals.items():
      by_file[name].append(seconds)
  ranked = sorted(by_file.items(), key=lambda item: -statistics.mean(item[1]))
  print("\ntests' own setup+call+teardown by file (mean ms):")
  for name, values in ranked[:shown]:
    print(f'  {milliseconds(statistics.mean(values))}  {name}')
  rest = sum(statistics.mean(values) for _, values in ranked[shown:])
  print(f'  {milliseconds(rest)}  the other {len(ranked) - shown} files')


def main() -> None:
  """Prints the whole report."""
  summarize(
    'plain hook',
    [record['wall'] for _, record in quiet(load_records('plain'))],
  )
  traced = [
    TracedRun(label, record, load_timeline(label), read_trace(label))
    for label, record in quiet(load_records('traced'))
  ]
  alone = [
    (record, load_timeline(label))
    for label, record in quiet(load_records('pytest'))
  ]
  summarize('traced hook', [run.record['wall'] for run in traced])

  per_run_rows = []
  in_hook_phases = []
  for run in traced:
    events = critical_path(run)
    assign_steps(events)
    rows = attribute(events)
    # The segments tile the run, so they must sum to its length.
    total = sum(rows.values())
    assert abs(total - (run.record['exit'] - run.record['spawn'])) < 1e-6
    per_run_rows.append(rows)
    pytest_launch = next(
      event.timestamp
      for event in events
      if event.command.startswith('uv run') and 'pytest' in event.command
    )
    in_hook_phases.append(pytest_phases(run.timeline, pytest_launch))
  print_rows(per_run_rows)

  tsc_to_vitest = []
  for run in traced:
    background = [event for event in run.trace if is_background(event)]
    tsc_to_vitest.append(background[-1].timestamp - background[0].timestamp)
  print(
    '\nJavaScript checks (background): tsc start to vitest start, mean '
    f'{milliseconds(statistics.mean(tsc_to_vitest)).strip()}ms'
  )

  print_phase_comparison(
    in_hook_phases,
    [pytest_phases(timeline, record['spawn']) for record, timeline in alone],
  )
  alone_exit = [
    record['exit'] - timeline['marks']['last_atexit']
    for record, timeline in alone
  ]
  print(
    '  alone: last exit handler to the launcher seeing the exit, mean '
    f'{milliseconds(statistics.mean(alone_exit)).strip()}ms'
  )
  timelines = [run.timeline for run in traced]
  print_garbage_collection(timelines)
  print_test_loop(timelines)
  print_tests_by_file(timelines)


if __name__ == '__main__':
  main()
