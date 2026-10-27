# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Timestamp each phase of a pytest run, for a breakdown of where time goes.

Loaded through `PYTEST_PLUGINS=timeline`, with this directory on `PYTHONPATH`.
An exit handler, registered at import so that it runs after the handlers pytest
registers later, writes JSON to the file `TIMELINE_OUT` names, holding:

- wall-clock marks, comparable with a launcher's `time.time()`, at plugin
  import, configure, collection's start and finish, the test loop's start and
  end, session finish, the terminal summary, unconfigure, and the exit handler
- garbage-collection pauses, totalled by phase
- each test's setup, call and teardown durations, and its wall time from the
  start of its protocol to the end

Two more variables add to the run:

- `TIMELINE_FAST_EXIT` ends the process with `os._exit` once the record is
  written, skipping Python's own shutdown, so a comparison shows its cost
- `TIMELINE_MODULES_OUT` names a file for where each module loaded by the end of
  collection came from, for classifying an import-time log

Marker lines on standard error divide such a log into the run's phases.
"""

import atexit
import gc
import json
import os
import sys
import time
from collections.abc import Generator
from pathlib import Path

import pytest

_marks: dict[str, float] = {'plugin_imported': time.time()}
_phase = ['startup']
_gc_by_phase: dict[str, float] = {}
_gc_started: list[float] = []
_reports: dict[str, dict[str, float]] = {}
_protocol: dict[str, float] = {}
_exit_status = [0]


def _on_gc(event: str, info: dict[str, int]) -> None:
  """Adds each garbage-collection pause to the current phase's total."""
  if event == 'start':
    _gc_started.append(time.perf_counter())
  elif _gc_started:
    elapsed = time.perf_counter() - _gc_started.pop()
    _gc_by_phase[_phase[0]] = _gc_by_phase.get(_phase[0], 0.0) + elapsed


gc.callbacks.append(_on_gc)


def _mark(name: str) -> None:
  _marks[name] = time.time()


def _write() -> None:
  """Writes the record, and with `TIMELINE_FAST_EXIT`, ends the process."""
  _mark('last_atexit')
  record = {
    'marks': _marks,
    'gc_by_phase': _gc_by_phase,
    'reports': _reports,
    'protocol': _protocol,
  }
  Path(os.environ['TIMELINE_OUT']).write_text(json.dumps(record))
  if os.environ.get('TIMELINE_FAST_EXIT'):
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_exit_status[0])


atexit.register(_write)
print('TIMELINE-PLUGIN-IMPORTED', file=sys.stderr, flush=True)


def pytest_configure(config: pytest.Config) -> None:
  """Marks configure."""
  _mark('configure')


def pytest_collection(session: pytest.Session) -> None:
  """Marks collection's start."""
  _phase[0] = 'collection'
  _mark('collection_start')
  print('TIMELINE-COLLECTION-STARTED', file=sys.stderr, flush=True)


def pytest_collection_finish(session: pytest.Session) -> None:
  """Marks collection's finish, and writes the module origins if asked."""
  _mark('collection_finish')
  modules_out = os.environ.get('TIMELINE_MODULES_OUT')
  if modules_out:
    origins = {
      name: getattr(module, '__file__', None)
      for name, module in list(sys.modules.items())
    }
    Path(modules_out).write_text(json.dumps(origins))
  print('TIMELINE-COLLECTION-FINISHED', file=sys.stderr, flush=True)


@pytest.hookimpl(wrapper=True)
def pytest_runtestloop(
  session: pytest.Session,
) -> Generator[None, object, object]:
  """Marks the test loop's start and end."""
  _phase[0] = 'tests'
  _mark('loop_start')
  try:
    return (yield)
  finally:
    _mark('loop_end')
    print('TIMELINE-TESTS-FINISHED', file=sys.stderr, flush=True)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_protocol(
  item: pytest.Item, nextitem: pytest.Item | None
) -> Generator[None, object, object]:
  """Records each test's wall time, from its protocol's start to its end."""
  started = time.perf_counter()
  try:
    return (yield)
  finally:
    _protocol[item.nodeid] = time.perf_counter() - started


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
  """Records each test's setup, call and teardown durations."""
  _reports.setdefault(report.nodeid, {})[report.when] = report.duration


def pytest_sessionfinish(
  session: pytest.Session, exitstatus: int | pytest.ExitCode
) -> None:
  """Marks session finish, and keeps the status for a fast exit."""
  _exit_status[0] = int(exitstatus)
  _mark('sessionfinish')
  _phase[0] = 'session finish'


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_terminal_summary(
  terminalreporter: pytest.TerminalReporter,
  exitstatus: pytest.ExitCode,
  config: pytest.Config,
) -> Generator[None, object, object]:
  """Marks the terminal summary's start and end."""
  _mark('summary_start')
  try:
    return (yield)
  finally:
    _mark('summary_end')


def pytest_unconfigure(config: pytest.Config) -> None:
  """Marks unconfigure."""
  _mark('unconfigure')
  _phase[0] = 'unconfigure'
