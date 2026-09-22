# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Read back what a rendered PDF contains.

Verifying a render asks what text landed on each page. poppler's `pdftotext`
answers, and its `-layout` mode keeps column order and running headers so the
result can serve as a golden.
"""

import subprocess
from collections.abc import Sequence
from pathlib import Path


def _run_poppler(command: Sequence[str]) -> str:
  """Run one poppler tool, returning its stdout."""
  return subprocess.run(
    command, capture_output=True, text=True, encoding='utf-8', check=True
  ).stdout


def extract_text(pdf: Path) -> str:
  """Return the PDF's text, laid out as on the page (`pdftotext -layout`)."""
  return _run_poppler(['pdftotext', '-layout', str(pdf), '-'])
