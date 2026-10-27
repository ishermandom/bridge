# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Garbage-collection handling around collection, chosen by `GC_VARIANT`.

- `freeze`: pause garbage collection while pytest collects, then freeze every
  object alive at that point, so later collections never scan it again
- `collect_freeze`: the same, with one full collection just before the freeze,
  so no garbage is frozen along with the live objects
- unset or empty: leave garbage collection as it is

`GC_DIAGNOSE=1` prints how many objects are tracked when collection finishes,
how many of them are garbage, and how many end up frozen. Every run prints its
peak memory when pytest unconfigures. Both go to standard error, as lines that
start with `GC-`.
"""

import gc
import os
import resource
import sys
import time

import pytest

_variant = os.environ.get('GC_VARIANT', '')


@pytest.hookimpl(tryfirst=True)
def pytest_collection(session: pytest.Session) -> None:
  """Pauses garbage collection for the variants that freeze."""
  if _variant:
    gc.disable()


@pytest.hookimpl(trylast=True)
def pytest_collection_finish(session: pytest.Session) -> None:
  """Freezes what collection loaded, and reports on it if asked."""
  if os.environ.get('GC_DIAGNOSE'):
    tracked = len(gc.get_objects())
    started = time.perf_counter()
    garbage = gc.collect()
    seconds = time.perf_counter() - started
    print(
      f'GC-DIAGNOSE tracked {tracked} garbage {garbage} '
      f'full-collection {seconds * 1000:.1f}ms',
      file=sys.stderr,
    )
  if _variant == 'collect_freeze':
    gc.collect()
  if _variant:
    gc.freeze()
    gc.enable()
    print(f'GC-DIAGNOSE frozen {gc.get_freeze_count()}', file=sys.stderr)


def pytest_unconfigure(config: pytest.Config) -> None:
  """Prints the run's peak memory, which macOS reports in bytes."""
  peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
  print(f'GC-PEAK {peak / 2**20:.1f}MiB', file=sys.stderr)
