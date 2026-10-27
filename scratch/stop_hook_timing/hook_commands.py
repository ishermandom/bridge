# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Where the Stop hook and this repo live, and the commands the hook runs, as
the timing scripts reproduce them.

`PYTEST` mirrors the pytest invocation `run_tests.sh` makes when the Stop hook
runs it. Keep the two in step, or the timings stop describing the hook.
"""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK = Path.home() / '.claude' / 'hooks' / 'stop_checks.sh'
# The hook links into the dotfiles checkout, at `claude/hooks/` below its root.
DOTFILES_ROOT = HOOK.resolve().parents[2]
PLUGINS = Path(__file__).resolve().parent / 'plugins'

# Results go outside the checkout, so no run's output can be committed.
OUT = Path(
  os.environ.get(
    'STOP_HOOK_TIMING_OUT',
    str(Path(os.environ.get('TMPDIR', '/tmp')) / 'stop_hook_timing'),
  )
)

_SUITES = (
  'anki',
  'club_sites/palo_alto',
  'convention_cards',
  'practice/squeezes/scratch',
  'session_analysis',
  'system_notes',
)

# Run from the repo root, as `quiet-tests.sh` runs `./run_tests.sh`, so the
# script's `$repo_root` is `.`.
PYTEST = (
  'uv',
  'run',
  '--project',
  '.',
  'pytest',
  '--disable-plugin-autoload',
  '-m',
  'not slow',
  '-p',
  'no:debugging',
  *(f'./{suite}' for suite in _SUITES),
  '--ignore=./practice/squeezes/scratch/generation_test.py',
  '--ignore=./practice/squeezes/scratch/server_test.py',
)

_PACKAGE = './club_sites/palo_alto'
TSC = (f'{_PACKAGE}/node_modules/.bin/tsc', '-p', f'{_PACKAGE}/jsconfig.json')
VITEST = (
  f'{_PACKAGE}/node_modules/.bin/vitest',
  'run',
  '--root',
  str(REPO_ROOT / 'club_sites' / 'palo_alto'),
)


def base_environment() -> dict[str, str]:
  """This process's environment, less anything that would change what a timed
  command does or measure the harness instead of the hook.
  """
  dropped = {
    'PYTHONPYCACHEPREFIX',
    'PYTEST_ADDOPTS',
    'PYTEST_PLUGINS',
    'SHELLOPTS',
    'BASH_XTRACEFD',
    'PS4',
    'PYTHONPATH',
  }
  return {
    name: value for name, value in os.environ.items() if name not in dropped
  }


def plugin_environment(
  timeline_path: Path, plugins: tuple[str, ...] = ()
) -> dict[str, str]:
  """Environment additions that load the timeline plugin, plus `plugins`, into
  pytest, with the timeline written to `timeline_path`.
  """
  return {
    'PYTEST_PLUGINS': ','.join((*plugins, 'timeline')),
    'PYTHONPATH': str(PLUGINS),
    'TIMELINE_OUT': str(timeline_path),
    'PYTEST_ADDOPTS': '--tb=short',
  }
