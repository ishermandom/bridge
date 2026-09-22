# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Re-render the fixture and overwrite its golden files.

Run after an intentional change to the template, stylesheet, or fixture, then
review the golden diff before committing: the diff *is* the record of what the
change did to the rendering. `render_notes_test.py` compares against these
files.
"""

import shutil
import tempfile
from pathlib import Path

from system_notes import render_notes

FIXTURE = Path(__file__).resolve().parent / 'fixture'
GOLDEN_DIRECTORY = FIXTURE / 'golden'


def update_goldens() -> None:
  """Render `fixture/notes.md` in a scratch directory and copy the results."""
  with tempfile.TemporaryDirectory() as scratch:
    source = Path(scratch) / 'notes.md'
    shutil.copy(FIXTURE / 'notes.md', source)
    outputs = render_notes.render(source)
    shutil.copy(outputs.html, GOLDEN_DIRECTORY / 'notes.html')
    shutil.copy(outputs.text, GOLDEN_DIRECTORY / 'notes.txt')


if __name__ == '__main__':
  update_goldens()
