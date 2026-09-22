# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Render partnership system notes from Pandoc Markdown to HTML, PDF, and text.

`python -m system_notes.render_notes notes.md` writes `notes.html`, `notes.pdf`,
and `notes.txt` beside the input. The HTML is self-contained and serves the
screen; WeasyPrint lays the same HTML out under the stylesheet's print rules for
the PDF; pandoc's plain writer produces the text rendering for email. The design
and its rationale live in `spec.md`; the notation the Markdown may use is in the
repo README.
"""

import argparse
import logging
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import weasyprint

from system_notes import pdf_inspection

TOOL_DIRECTORY = Path(__file__).resolve().parent
TEMPLATE = TOOL_DIRECTORY / 'template.html'
STYLESHEET = TOOL_DIRECTORY / 'notes.css'

# Filter order matters: metadata checks the front matter first; nowrap protects
# the tokens bids left intact.
FILTERS = tuple(
  TOOL_DIRECTORY / 'filters' / name
  for name in (
    'metadata.lua',
    'bids.lua',
    'nowrap.lua',
  )
)

# Hard-wrap width of the plain-text rendering: comfortable in any mail client or
# terminal, with room for the deepest list indentation.
PLAIN_TEXT_COLUMNS = 72

# One list marker per nesting depth, the ladder notes.css gives `ul` levels;
# pandoc's plain writer marks every level `-`, so the markers are rewritten
# afterward. Twelve rungs — six rounds of the auction, a pair to each — cover
# any outline worth reading; a thirteenth depth keeps the last marker rather
# than starting over, matching the stylesheet, whose deepest selector applies to
# everything below it too.
LIST_MARKERS = ('○', '●', '□', '▪', '◦', '•', '△', '▲', '▽', '▼', '▷', '▶')

# A plain-writer list marker opening any line: its indent (two spaces per level)
# and the `-`.
PLAIN_LIST_MARKER = re.compile(r'^(?P<indent>[ ]*)- ', flags=re.MULTILINE)

# WeasyPrint parses media types only, so the stylesheet's phone-width media
# query draws warnings on every render. That rule is screen-only, so they carry
# no information. The match is on the query's own text, not on the warning's
# wording, so a print rule WeasyPrint cannot parse still warns.
PHONE_WIDTH_MEDIA_QUERY = 'max-width: 600px'

# The families the stylesheet asks for, spelled as `pdffonts` reports them. A
# rendered PDF may embed nothing else: another family means fontconfig supplied
# a face the stylesheet never named — a glyph the chosen fonts lack, or an
# element such as a code span that the stylesheet gives no family.
CHOSEN_FONT_FAMILIES = frozenset(
  {'IBM-Plex-Serif', 'Source-Sans-3', 'STIX-Two-Math'}
)


@dataclass(frozen=True)
class RenderedNotes:
  """The three output paths of one render."""

  html: Path
  pdf: Path
  text: Path


class IgnoreKnownWarning(logging.Filter):
  """Drop the benign phone-width media-query warnings."""

  def filter(self, record: logging.LogRecord) -> bool:
    return PHONE_WIDTH_MEDIA_QUERY not in record.getMessage()


class CollectedWarnings(logging.Handler):
  """Collect WeasyPrint's warnings so the render can fail on them."""

  def __init__(self) -> None:
    super().__init__(logging.WARNING)
    self.addFilter(IgnoreKnownWarning())
    self.messages: list[str] = []

  def emit(self, record: logging.LogRecord) -> None:
    self.messages.append(record.getMessage())


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


def verify_fonts(pdf: Path) -> None:
  """Fail if the PDF embeds any font family outside the chosen set."""
  unexpected = pdf_inspection.embedded_font_families(pdf) - CHOSEN_FONT_FAMILIES
  if unexpected:
    raise RuntimeError(
      f'{pdf} embeds font families outside the chosen set: '
      f'{", ".join(sorted(unexpected))}. Some text fell back to a face the '
      'stylesheet never named — a glyph the chosen fonts lack, or an element '
      'such as a code span that the stylesheet gives no family '
      '(spec.md #appearance).'
    )


def verify_nothing_warned(messages: Sequence[str], output: Path) -> None:
  """Fail on anything WeasyPrint reported while laying the page out.

  It warns and carries on where it cannot parse a rule or honor a layout, so —
  as with pandoc's `--fail-if-warnings` — every report but the known one means
  the page is not what the stylesheet asked for.
  """
  if messages:
    raise RuntimeError(
      f'WeasyPrint warned or errored while writing {output}:\n'
      + '\n'.join(messages)
    )


def render_pdf(html: Path, output: Path) -> None:
  """Lay the HTML out under the stylesheet's print rules as the PDF.

  WeasyPrint warns and carries on where it cannot parse a rule or honor a
  layout, so — as with pandoc's `--fail-if-warnings` — every warning but the
  known one fails the render. The embedded fonts are checked here too, since
  only the finished file shows what the page was actually set in.

  So the render goes to a scratch copy, and only a copy that passes every check
  reaches `output`. The outputs are committed beside their source, and a
  rejected layout left in place would be committed along with them.
  """
  collected = CollectedWarnings()
  logger = logging.getLogger('weasyprint')
  logger.addHandler(collected)
  with tempfile.TemporaryDirectory() as directory:
    unverified = Path(directory) / output.name
    try:
      markup = html.read_text(encoding='utf-8')
      weasyprint.HTML(string=markup).write_pdf(str(unverified))
    finally:
      logger.removeHandler(collected)
      verify_nothing_warned(collected.messages, output)
    verify_fonts(unverified)
    shutil.copyfile(unverified, output)


def apply_list_markers(text: str) -> str:
  """Give each list depth its marker from LIST_MARKERS."""

  def marker_for(match: re.Match[str]) -> str:
    indent = match['indent']
    depth = min(len(indent) // 2, len(LIST_MARKERS) - 1)
    return indent + LIST_MARKERS[depth] + ' '

  return PLAIN_LIST_MARKER.sub(marker_for, text)


def render_text(source: Path, output: Path) -> None:
  """Write the hard-wrapped plain-text rendering, for pasting into email."""
  run_pandoc(
    source, output, ['--to', 'plain', '--columns', str(PLAIN_TEXT_COLUMNS)]
  )
  output.write_text(
    apply_list_markers(output.read_text(encoding='utf-8')), encoding='utf-8'
  )


def render(source: Path) -> RenderedNotes:
  """Render `source` to its three outputs, named after it and beside it."""
  outputs = RenderedNotes(
    html=source.with_suffix('.html'),
    pdf=source.with_suffix('.pdf'),
    text=source.with_suffix('.txt'),
  )
  render_html(source, outputs.html)
  render_pdf(outputs.html, outputs.pdf)
  render_text(source, outputs.text)
  return outputs


def main(argv: Sequence[str]) -> None:
  """Command line: one Markdown path in, three files out beside it."""
  parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
  parser.add_argument(
    'source', type=Path, help='the notes Markdown file to render'
  )
  arguments = parser.parse_args(argv)
  logging.basicConfig(level=logging.WARNING, format='%(name)s: %(message)s')
  logging.getLogger('weasyprint').addFilter(IgnoreKnownWarning())
  outputs = render(arguments.source.resolve())
  for path in (outputs.html, outputs.pdf, outputs.text):
    print(f'wrote {path}')


if __name__ == '__main__':
  main(sys.argv[1:])
