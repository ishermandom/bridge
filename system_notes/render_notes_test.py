# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""The fixture rendered end to end: goldens and embedded fonts."""

import re
import shutil
import struct
import subprocess
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


# --- fonts ---


def test_pdf_embeds_exactly_the_chosen_font_families(
  rendered: render_notes.RenderedNotes,
) -> None:
  families = pdf_inspection.embedded_font_families(rendered.pdf)
  assert families == render_notes.CHOSEN_FONT_FAMILIES


def test_a_font_fallback_fails_the_render(tmp_path: Path) -> None:
  # A code span has no family in the stylesheet, so it falls back to whatever
  # monospace the machine offers — never one of the chosen families.
  source = tmp_path / 'notes.md'
  source.write_text(
    '---\ntitle: Notes\n---\n\n# A {#a}\n\nUse `code` here.\n',
    encoding='utf-8',
  )
  with pytest.raises(RuntimeError, match='outside'):
    render_notes.render(source)


def _italic_angle(font: Path) -> float:
  """The italic angle, in degrees, from the font's `post` table.

  A hand parse rather than a font library: the font file's sfnt layout is frozen
  — a `uint16` table count at offset 4, then 16-byte records of tag, checksum,
  offset, and length from offset 12 — and the angle sits at offset 4 of the
  `post` table as a signed 16.16 fixed-point number.
  """
  data = font.read_bytes()
  if data[:4] == b'ttcf':
    raise ValueError(
      f'{font} is a TrueType Collection; this parse reads single-font files'
    )
  (table_count,) = struct.unpack_from('>H', data, 4)
  for index in range(table_count):
    tag, _, offset, _ = struct.unpack_from('>4sIII', data, 12 + 16 * index)
    if tag == b'post':
      (angle,) = struct.unpack_from('>i', data, offset + 4)
      return float(angle) / 65536
  raise ValueError(f'{font} has no post table')


def test_suit_skew_tracks_the_body_font_italic_angle() -> None:
  """Changing the body font must carry the suit skew along with it.

  Suit symbols lean inside italic text through an explicit `skewX` angle in the
  stylesheet, chosen to match the body font's italic angle. A future body face
  (`tasks.md` #serif-alternatives) ships an angle of its own, so this test reads
  both and fails until the stylesheet follows.
  """
  stylesheet = read(render_notes.STYLESHEET)
  body_rule = re.search(r'body \{(?P<declarations>[^}]*)\}', stylesheet)
  assert body_rule, 'no body rule in the stylesheet'
  family = re.search(
    r'font-family: "(?P<family>[^"]+)"', body_rule['declarations']
  )
  assert family, 'no quoted font family in the body rule'
  skew = re.search(
    r'\.suit \{\s*transform: skewX\((?P<degrees>-?[0-9.]+)deg\)', stylesheet
  )
  assert skew, 'no suit skew in the stylesheet'

  matched_font = subprocess.run(
    ['fc-match', '-f', '%{family}\t%{file}', f'{family["family"]}:italic'],
    capture_output=True,
    text=True,
    encoding='utf-8',
    check=True,
  ).stdout
  matched_family, _, font_file = matched_font.partition('\t')
  # A font can carry several family names; fc-match then reports them
  # comma-joined.
  assert family['family'] in matched_family.split(','), (
    f'no installed italic for the body font: fontconfig offered '
    f'{matched_family!r}'
  )

  angle = _italic_angle(Path(font_file))
  # The tolerance lets the stylesheet round the angle to a whole degree.
  assert abs(float(skew['degrees']) - angle) <= 0.75, (
    f'the stylesheet skews suits {skew["degrees"]}° but '
    f'{matched_family} Italic leans at {angle:.2f}°'
  )


# --- stylesheet coupling ---


def test_text_marker_ladder_tracks_the_stylesheet() -> None:
  """notes.css owns the list-marker ladder; the text rendering must follow."""
  # The markers come back in the order the stylesheet declares them, which is
  # depth order: each rule nests one `ul` deeper than the rule above it.
  markers = re.findall(
    r'list-style-type: "(.) ";', read(render_notes.STYLESHEET)
  )
  assert tuple(markers) == render_notes.LIST_MARKERS
