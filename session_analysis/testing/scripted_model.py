# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""A scripted stand-in for the headless `claude` invocation.

Every stage that reaches the vision model reaches it through
`vision_model_invocation`'s injected `run_command`, so a test replaces the
subprocess by handing one of these in. Replies are consumed in the order they
were scripted, which is what makes a two-run transcription testable: the two
reads of one sheet are simply the first two replies.

Used as a context manager, it also asserts that every scripted reply was
consumed — a test that scripts three replies and drives two calls has not tested
what it thinks it has. The check is skipped when an exception is already
propagating, so a real failure is never masked by this one.
"""

import json
import pathlib
import subprocess
import types
from collections.abc import Sequence


class ScriptedModelRunner:
  """A `run_command` fake returning scripted results, in order.

  Records every stdin it was handed, so a test can inspect what was actually
  sent to the model as well as what came back.
  """

  def __init__(self, results: Sequence[str]) -> None:
    self._results = list(results)
    self.stdin_texts: list[str] = []

  def __call__(
    self, command: Sequence[str], stdin_text: str, cwd: pathlib.Path
  ) -> subprocess.CompletedProcess[str]:
    self.stdin_texts.append(stdin_text)
    reply = {
      'type': 'result',
      'is_error': False,
      'result': self._results.pop(0),
    }
    return subprocess.CompletedProcess(
      args=[], returncode=0, stdout=json.dumps(reply), stderr=''
    )

  def __enter__(self) -> 'ScriptedModelRunner':
    return self

  def __exit__(
    self,
    exc_type: type[BaseException] | None,
    exc: BaseException | None,
    tb: types.TracebackType | None,
  ) -> None:
    if exc_type is None:
      assert not self._results, f'{len(self._results)} scripted replies unused'
