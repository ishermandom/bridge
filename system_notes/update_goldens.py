# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Re-render the fixture and overwrite its golden files.

Run after an intentional change to the filters, template, stylesheet, or
fixture, then review the golden diff before committing: the diff *is* the record
of what the change did to the rendering. `render_notes_test.py` compares against
these files.
"""

import logging
import shutil
import tempfile
from pathlib import Path

from system_notes import pdf_inspection, render_notes

FIXTURE = Path(__file__).resolve().parent / 'fixture'
GOLDEN_DIRECTORY = FIXTURE / 'golden'


def update_goldens() -> None:
  """Render `fixture/notes.md` in a scratch directory and copy the results."""
  with tempfile.TemporaryDirectory() as scratch:
    source = Path(scratch) / 'notes.md'
    shutil.copy(FIXTURE / 'notes.md', source)
    outputs = render_notes.render(source)
    shutil.copy(outputs.html, GOLDEN_DIRECTORY / 'notes.html')
    # The PDF golden is its extracted text, not its bytes: spec.md #goldens says
    # why.
    (GOLDEN_DIRECTORY / 'notes.pdf.txt').write_text(
      pdf_inspection.extract_text(outputs.pdf), encoding='utf-8'
    )
    shutil.copy(outputs.text, GOLDEN_DIRECTORY / 'notes.txt')


if __name__ == '__main__':
  # Surface WeasyPrint's warnings as the command line does; without a handler
  # they would vanish.
  logging.basicConfig(level=logging.WARNING, format='%(name)s: %(message)s')
  logging.getLogger('weasyprint').addFilter(render_notes.IgnoreKnownWarning())
  update_goldens()
