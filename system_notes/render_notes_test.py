# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""The fixture rendered end to end, against its goldens."""

import re
import shutil
from pathlib import Path

import pytest

from system_notes import pdf_inspection, render_notes

FIXTURE = Path(__file__).resolve().parent / 'fixture'
GOLDEN_DIRECTORY = FIXTURE / 'golden'


@pytest.fixture(scope='module')
def rendered(
  tmp_path_factory: pytest.TempPathFactory,
) -> render_notes.RenderedNotes:
  """The fixture rendered once into a scratch directory."""
  source = tmp_path_factory.mktemp('render') / 'notes.md'
  shutil.copy(FIXTURE / 'notes.md', source)
  return render_notes.render(source)


def read(path: Path) -> str:
  """The file's text, decoded as UTF-8 whatever the locale says."""
  return path.read_text(encoding='utf-8')


# --- goldens ---


def test_html_matches_golden(rendered: render_notes.RenderedNotes) -> None:
  assert read(rendered.html) == read(GOLDEN_DIRECTORY / 'notes.html')


def test_pdf_text_matches_golden(rendered: render_notes.RenderedNotes) -> None:
  assert pdf_inspection.extract_text(rendered.pdf) == read(
    GOLDEN_DIRECTORY / 'notes.pdf.txt'
  )


def test_text_matches_golden(rendered: render_notes.RenderedNotes) -> None:
  assert read(rendered.text) == read(GOLDEN_DIRECTORY / 'notes.txt')


# --- list markers ---


def test_list_markers_follow_depth() -> None:
  """Each depth takes its own marker, and the deepest rung repeats below."""
  plain = (
    '- a\n'
    '  - b\n'
    '    - c\n'
    '      - d\n'
    '        - e\n'
    '          - f\n'
    '            - g\n'
    '              - h\n'
    '                - i\n'
    '                  - j\n'
    '                    - k\n'
    '                      - l\n'
    '                        - m\n'
  )
  assert render_notes.apply_list_markers(plain) == (
    '○ a\n'
    '  ● b\n'
    '    □ c\n'
    '      ▪ d\n'
    '        ◦ e\n'
    '          • f\n'
    '            △ g\n'
    '              ▲ h\n'
    '                ▽ i\n'
    '                  ▼ j\n'
    '                    ▷ k\n'
    '                      ▶ l\n'
    '                        ▶ m\n'
  )


# --- warnings ---


def test_a_weasyprint_warning_fails_the_render(tmp_path: Path) -> None:
  """WeasyPrint only warns about an undecodable image and lays it out anyway."""
  html = tmp_path / 'notes.html'
  html.write_text(
    '<img src="data:image/png;base64,not-base64">', encoding='utf-8'
  )
  pdf = tmp_path / 'notes.pdf'

  with pytest.raises(RuntimeError, match='WeasyPrint warned'):
    render_notes.render_pdf(html, pdf)

  assert not pdf.exists(), 'the rejected layout reached the output file'


# --- stylesheet coupling ---


def test_text_marker_ladder_tracks_the_stylesheet() -> None:
  """notes.css owns the list-marker ladder; the text rendering must follow."""
  # The markers come back in the order the stylesheet declares them, which is
  # depth order: each rule nests one `ul` deeper than the rule above it.
  markers = re.findall(
    r'list-style-type: "(.) ";', read(render_notes.STYLESHEET)
  )
  assert tuple(markers) == render_notes.LIST_MARKERS
