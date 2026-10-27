# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Time the whole Stop hook over this repo, round-robin, three ways:

- plain: `~/.claude/hooks/stop_checks.sh` as Claude Code runs it
- traced: the same, with every bash command in the chain timestamped (bash's
  command trace, written to a file) and pytest's phases recorded by the timeline
  plugin
- pytest: `run_tests.sh`'s pytest invocation alone, with the timeline plugin, so
  the JavaScript checks' contention can be read off against the traced runs

Interleaving the three spreads any drift in the machine's load across all of
them. Each run's record goes to `hook_runs/` in the output directory: its wall
time, the launcher's timestamps, whether it passed, and the load average, plus
for a traced run the command trace and the timeline.

Usage, from the repo root: python3 -m scratch.stop_hook_timing.time_hook ROUNDS
"""

import json
import os
import shutil
import subprocess
import sys
import time

from scratch.stop_hook_timing.hook_commands import (
  HOOK,
  OUT,
  PYTEST,
  REPO_ROOT,
  base_environment,
  plugin_environment,
)

RUNS = OUT / 'hook_runs'
VARIANTS = ('plain', 'traced', 'pytest')

# What Claude Code hands a Stop hook on standard input; the hook ignores it.
_PAYLOAD = json.dumps(
  {
    'session_id': 'timing',
    'hook_event_name': 'Stop',
    'stop_hook_active': False,
    'cwd': str(REPO_ROOT),
  }
)

# Each traced line opens with its time, process, script and line number.
_PS4 = '+${EPOCHREALTIME} ${BASHPID} ${BASH_SOURCE[0]##*/}:${LINENO} '


def _run(variant: str, round_number: int) -> None:
  """Runs `variant` once and writes its record."""
  label = f'{variant}-{round_number}'
  environment = base_environment()
  command: tuple[str, ...] = (str(HOOK),)
  payload = _PAYLOAD
  pass_fds: tuple[int, ...] = ()
  trace_fd = None
  if variant in ('traced', 'pytest'):
    environment.update(plugin_environment(RUNS / f'{label}.timeline.json'))
  if variant == 'traced':
    trace_fd = os.open(
      RUNS / f'{label}.xtrace',
      os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_TRUNC,
    )
    pass_fds = (trace_fd,)
    # Exported this way, tracing reaches every bash script in the chain, and
    # each writes its trace to the inherited descriptor.
    environment.update(
      {
        'SHELLOPTS': 'xtrace',
        'PS4': _PS4,
        'BASH_XTRACEFD': str(trace_fd),
      }
    )
  if variant == 'pytest':
    command = PYTEST
    payload = ''

  load = os.getloadavg()[0]
  spawn = time.time()
  started = time.perf_counter()
  completed = subprocess.run(
    command,
    cwd=REPO_ROOT,
    env=environment,
    input=payload,
    capture_output=True,
    text=True,
    pass_fds=pass_fds,
  )
  wall = time.perf_counter() - started
  exit_ = time.time()
  if trace_fd is not None:
    os.close(trace_fd)

  # The hook prints nothing when every check passes.
  passed = completed.returncode == 0 and (
    variant == 'pytest' or not completed.stdout
  )
  if not passed:
    print(
      f'{label}: status {completed.returncode}\n'
      f'{completed.stdout[-2000:]}\n{completed.stderr[-2000:]}'
    )
  record = {
    'wall': wall,
    'spawn': spawn,
    'exit': exit_,
    'passed': passed,
    'load': load,
  }
  (RUNS / f'{label}.json').write_text(json.dumps(record))
  print(f'{label}: {wall * 1000:.0f}ms', flush=True)


def main(rounds: int) -> None:
  """Runs `rounds` rounds after an untimed one, which settles caches."""
  shutil.rmtree(RUNS, ignore_errors=True)
  RUNS.mkdir(parents=True)
  for variant in VARIANTS:
    _run(variant, -1)
  for round_number in range(rounds):
    for variant in VARIANTS:
      _run(variant, round_number)


if __name__ == '__main__':
  main(int(sys.argv[1]))
