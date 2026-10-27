# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Time each external command the Stop hook runs, alone, round-robin.

The results split the traced run's rows further:

- uv's overhead, against each tool's own time
- a tool's startup, against its work
- prettier's pattern expansion, against the same pass handed an explicit list of
  its files
- the `find` probes, with and without the dotfiles checkout's `.claude/`
- the background JavaScript checks, each alone

Also counts the modules whose cached results mypy loads, from its verbose log.

Usage, from the repo root: python3 -m scratch.stop_hook_timing.time_tools ROUNDS
"""

import hashlib
import os
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

from scratch.stop_hook_timing.hook_commands import (
  DOTFILES_ROOT,
  REPO_ROOT,
  TSC,
  VITEST,
  base_environment,
)

_BRIDGE_VENV = REPO_ROOT / '.venv' / 'bin'
_DOTFILES_VENV = DOTFILES_ROOT / '.venv' / 'bin'
_BRIDGE_PATTERNS = ('*.md', '*.js', '*.ts')
_DOTFILES_PATTERNS = ('*.md', '*.js')


def _prettier_write(
  directory: Path, targets: tuple[str, ...]
) -> tuple[str, ...]:
  """`quiet-prettier.sh`'s write pass over `directory`, given `targets`."""
  cache_directory = (
    f'{os.environ.get("TMPDIR", "/tmp")}/prettier-cache-{os.getuid()}'
  )
  location = (
    f'{cache_directory}/{hashlib.md5(str(directory).encode()).hexdigest()}'
  )
  return (
    'prettier',
    '--config',
    str(Path.home() / '.prettierrc'),
    '--cache',
    '--cache-strategy',
    'content',
    '--cache-location',
    location,
    '--log-level',
    'warn',
    '--write',
    *targets,
  )


def _globs(patterns: tuple[str, ...]) -> tuple[str, ...]:
  return tuple(f'**/{pattern}' for pattern in patterns)


def _find_probe(pattern: str) -> tuple[str, ...]:
  """`quiet-prettier.sh`'s probe for a file matching `pattern`."""
  return (
    'find',
    '.',
    '-name',
    'node_modules',
    '-prune',
    '-o',
    '-name',
    pattern,
    '-print',
    '-quit',
  )


def _listed_files(
  directory: Path, patterns: tuple[str, ...]
) -> tuple[str, ...]:
  """The files prettier's write pass covers in `directory`, as it lists them."""
  logging_pass = [
    'log' if word == 'warn' else word
    for word in _prettier_write(directory, _globs(patterns))
  ]
  completed = subprocess.run(
    logging_pass,
    cwd=directory,
    env=base_environment(),
    capture_output=True,
    text=True,
    check=True,
  )
  return tuple(
    line.split(' ')[0] for line in completed.stdout.splitlines() if line.strip()
  )


def _commands() -> dict[str, tuple[Path, tuple[str, ...]]]:
  """Each command to time, by name, with the directory it runs in."""
  bridge_files = _listed_files(REPO_ROOT, _BRIDGE_PATTERNS)
  dotfiles_files = _listed_files(DOTFILES_ROOT, _DOTFILES_PATTERNS)
  bridge, dotfiles = REPO_ROOT, DOTFILES_ROOT
  return {
    'env bash -c :': (bridge, ('/usr/bin/env', 'bash', '-c', ':')),
    'git rev-parse --show-toplevel': (
      bridge,
      ('git', 'rev-parse', '--show-toplevel'),
    ),
    'python -c pass': (bridge, (str(_BRIDGE_VENV / 'python'), '-c', 'pass')),
    "python -c 'import pytest'": (
      bridge,
      (str(_BRIDGE_VENV / 'python'), '-c', 'import pytest'),
    ),
    'uv run python -c pass': (
      bridge,
      ('uv', 'run', '--project', '.', 'python', '-c', 'pass'),
    ),
    'uv run --with ruff ruff --version (bridge)': (
      bridge,
      ('uv', 'run', '--project', str(bridge), '--with', 'ruff', 'ruff', '-V'),
    ),
    'ruff --version (bridge venv)': (
      bridge,
      (str(_BRIDGE_VENV / 'ruff'), '-V'),
    ),
    'uv run --with ruff ruff --version (dotfiles)': (
      dotfiles,
      ('uv', 'run', '--project', str(dotfiles), '--with', 'ruff', 'ruff', '-V'),
    ),
    'ruff --version (dotfiles venv)': (
      dotfiles,
      (str(_DOTFILES_VENV / 'ruff'), '-V'),
    ),
    'uv run --with mypy mypy --version': (
      bridge,
      ('uv', 'run', '--project', str(bridge), '--with', 'mypy', 'mypy', '-V'),
    ),
    'mypy --version (venv)': (bridge, (str(_BRIDGE_VENV / 'mypy'), '-V')),
    'ruff check --fix (bridge)': (
      bridge,
      (str(_BRIDGE_VENV / 'ruff'), 'check', '--fix', str(bridge)),
    ),
    'ruff format (bridge)': (
      bridge,
      (str(_BRIDGE_VENV / 'ruff'), 'format', str(bridge)),
    ),
    'ruff check --color never (bridge)': (
      bridge,
      (str(_BRIDGE_VENV / 'ruff'), 'check', '--color', 'never'),
    ),
    'ruff check --fix (dotfiles)': (
      dotfiles,
      (str(_DOTFILES_VENV / 'ruff'), 'check', '--fix', str(dotfiles)),
    ),
    'ruff format (dotfiles)': (
      dotfiles,
      (str(_DOTFILES_VENV / 'ruff'), 'format', str(dotfiles)),
    ),
    'mypy --strict (bridge)': (
      bridge,
      (str(_BRIDGE_VENV / 'mypy'), '--strict', str(bridge)),
    ),
    'prettier --version': (bridge, ('prettier', '--version')),
    'prettier --find-config-path (bridge)': (
      bridge,
      ('prettier', '--find-config-path', './placeholder'),
    ),
    'prettier --write, patterns (bridge)': (
      bridge,
      _prettier_write(bridge, _globs(_BRIDGE_PATTERNS)),
    ),
    f'prettier --write, {len(bridge_files)} files listed (bridge)': (
      bridge,
      _prettier_write(bridge, bridge_files),
    ),
    'prettier --write, patterns (dotfiles)': (
      dotfiles,
      _prettier_write(dotfiles, _globs(_DOTFILES_PATTERNS)),
    ),
    f'prettier --write, {len(dotfiles_files)} files listed (dotfiles)': (
      dotfiles,
      _prettier_write(dotfiles, dotfiles_files),
    ),
    'find *.ts (bridge)': (bridge, _find_probe('*.ts')),
    'find *.ts (dotfiles)': (dotfiles, _find_probe('*.ts')),
    'find *.ts (dotfiles, skipping .claude)': (
      dotfiles,
      (
        'find',
        '.',
        '(',
        '-name',
        'node_modules',
        '-o',
        '-path',
        './.claude',
        ')',
        '-prune',
        '-o',
        '-name',
        '*.ts',
        '-print',
        '-quit',
      ),
    ),
    'tsc alone': (bridge, TSC),
    'vitest alone': (bridge, VITEST),
  }


def _mypy_modules() -> int:
  """How many modules' cached results mypy loads over this repo."""
  completed = subprocess.run(
    (str(_BRIDGE_VENV / 'mypy'), '--strict', '-v', str(REPO_ROOT)),
    cwd=REPO_ROOT,
    env=base_environment(),
    capture_output=True,
    text=True,
  )
  return len(re.findall(r'Metadata fresh for', completed.stderr))


def main(rounds: int) -> None:
  """Times every command `rounds` times, interleaved, and prints medians."""
  environment = base_environment()
  commands = _commands()
  samples: dict[str, list[float]] = {name: [] for name in commands}
  loads = []
  for _ in range(rounds):
    loads.append(os.getloadavg()[0])
    for name, (directory, command) in commands.items():
      started = time.perf_counter()
      completed = subprocess.run(
        command, cwd=directory, env=environment, capture_output=True
      )
      samples[name].append(time.perf_counter() - started)
      # A probe that finds nothing exits non-zero by design.
      if completed.returncode != 0 and not name.startswith('find'):
        print(
          f'{name}: status {completed.returncode}: {completed.stderr[-300:]!r}'
        )
  print(f'loads at each round: {" ".join(f"{load:.1f}" for load in loads)}')
  for name, times in samples.items():
    print(
      f'{statistics.median(times) * 1000:7.1f}ms median '
      f'{min(times) * 1000:7.1f}ms min  {name}'
    )
  print(f'mypy loads cached results for {_mypy_modules()} modules')


if __name__ == '__main__':
  main(int(sys.argv[1]))
