# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Render partnership system notes from Pandoc Markdown to HTML and text.

`python -m system_notes.render_notes notes.md` writes `notes.html` and
`notes.txt` beside the input. The HTML is self-contained and serves the screen;
pandoc's plain writer produces the text rendering for email. The design and its
rationale live in `spec.md`.
"""

import argparse
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

TOOL_DIRECTORY = Path(__file__).resolve().parent
TEMPLATE = TOOL_DIRECTORY / 'template.html'
STYLESHEET = TOOL_DIRECTORY / 'notes.css'

# Filter order matters: metadata checks the front matter first.
FILTERS = tuple(TOOL_DIRECTORY / 'filters' / name for name in ('metadata.lua',))

# Hard-wrap width of the plain-text rendering: comfortable in any mail client or
# terminal, with room for the deepest list indentation.
PLAIN_TEXT_COLUMNS = 72


@dataclass(frozen=True)
class RenderedNotes:
  """The output paths of one render."""

  html: Path
  text: Path


def run_pandoc(
  source: Path, output: Path, format_arguments: Sequence[str]
) -> None:
  """Run pandoc over `source` with every filter, writing `output`.

  `--fail-if-warnings` turns authoring slips such as a duplicate heading id into
  a failed render rather than a subtly wrong document.
  """
  command = ['pandoc', str(source), '--fail-if-warnings']
  for filter_path in FILTERS:
    command.extend(['--lua-filter', str(filter_path)])
  command.extend(format_arguments)
  command.extend(['--output', str(output)])
  try:
    subprocess.run(
      command, capture_output=True, text=True, encoding='utf-8', check=True
    )
  except subprocess.CalledProcessError as error:
    # The exception's message names only the command and its exit status; pandoc
    # explains the failure on stderr.
    error.add_note(error.stderr.strip())
    raise


def render_html(source: Path, output: Path) -> None:
  """Write the self-contained HTML, stylesheet embedded."""
  run_pandoc(
    source,
    output,
    [
      '--standalone',
      '--embed-resources',
      '--template',
      str(TEMPLATE),
      '--css',
      str(STYLESHEET),
    ],
  )


def render_text(source: Path, output: Path) -> None:
  """Write the hard-wrapped plain-text rendering, for pasting into email."""
  run_pandoc(
    source, output, ['--to', 'plain', '--columns', str(PLAIN_TEXT_COLUMNS)]
  )


def render(source: Path) -> RenderedNotes:
  """Render `source` to its outputs, named after it and beside it."""
  outputs = RenderedNotes(
    html=source.with_suffix('.html'),
    text=source.with_suffix('.txt'),
  )
  render_html(source, outputs.html)
  render_text(source, outputs.text)
  return outputs


def main(argv: Sequence[str]) -> None:
  """Command line: one Markdown path in, two files out beside it."""
  parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
  parser.add_argument(
    'source', type=Path, help='the notes Markdown file to render'
  )
  arguments = parser.parse_args(argv)
  outputs = render(arguments.source.resolve())
  for path in (outputs.html, outputs.text):
    print(f'wrote {path}')


if __name__ == '__main__':
  main(sys.argv[1:])
