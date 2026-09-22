# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Each Lua filter on small inputs, one filter at a time, through pandoc."""

import subprocess
from pathlib import Path

import pytest

FILTERS = Path(__file__).resolve().parent / 'filters'


def failing_pandoc(markdown: str, filter_name: str) -> str:
  """Run pandoc on `markdown` expecting the filter to fail; return stderr."""
  completed = subprocess.run(
    ['pandoc', '--lua-filter', str(FILTERS / filter_name)],
    input=markdown,
    capture_output=True,
    text=True,
    encoding='utf-8',
  )
  assert completed.returncode != 0, 'the filter should have failed'
  return completed.stderr


# --- metadata ---


@pytest.mark.parametrize(
  'front_matter', ['date: 2026-08-26', 'title: ""', "title: ''"]
)
def test_missing_or_empty_title_fails_the_render(front_matter: str) -> None:
  stderr = failing_pandoc(f'---\n{front_matter}\n---\n\nBody.', 'metadata.lua')
  assert 'non-empty `title`' in stderr
