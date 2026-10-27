# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Sample the main thread's stack during collection, from a second thread.

Loaded through `PYTEST_PLUGINS`; writes the samples as JSON to the file
`SAMPLER_OUT` names once collection finishes. Each sample is a timestamp and the
stack as (file, function) pairs, innermost first. A short switch interval lets
the sampler take the interpreter's lock about every half millisecond.

Python 3.15's own sampling profiler would be the better tool, but on macOS it
needs elevated permissions to read another process.
"""

import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

_samples: list[tuple[float, list[tuple[str, str]]]] = []
_stop = threading.Event()
# Plugins load on the main thread, so this is the thread collection runs on.
_main_thread = threading.get_ident()


def _sample() -> None:
  while not _stop.is_set():
    frame = sys._current_frames().get(_main_thread)
    stack = []
    while frame is not None:
      stack.append((frame.f_code.co_filename, frame.f_code.co_name))
      frame = frame.f_back
    _samples.append((time.perf_counter(), stack))
    time.sleep(0.0005)


@pytest.hookimpl(tryfirst=True)
def pytest_collection(session: pytest.Session) -> None:
  """Starts sampling."""
  _samples.append((time.perf_counter(), []))
  sys.setswitchinterval(0.0002)
  threading.Thread(target=_sample, daemon=True).start()


@pytest.hookimpl(trylast=True)
def pytest_collection_finish(session: pytest.Session) -> None:
  """Stops sampling and writes the samples."""
  _stop.set()
  sys.setswitchinterval(0.005)
  Path(os.environ['SAMPLER_OUT']).write_text(json.dumps(_samples))
