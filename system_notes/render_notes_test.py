# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""The fixture rendered end to end: goldens, embedded fonts, page references."""

import html
import re
import shutil
import string
import struct
import subprocess
from pathlib import Path
from typing import Literal

import pytest
from fontTools.ttLib import TTFont

from system_notes import pdf_inspection, print_layout, render_notes

FIXTURE = Path(__file__).resolve().parent / 'fixture'
GOLDEN_DIRECTORY = FIXTURE / 'golden'

# A cross-reference link in the rendered HTML: its target id and its text, which
# may hold strain spans. The class list may carry author classes beside `xref`;
# DOTALL because pandoc wraps long link text across lines.
CROSS_REFERENCE_LINK = re.compile(
  r'<a href="#(?P<target>[^"]+)" class="(?:[^"]* )?xref(?: [^"]*)?">'
  r'(?P<text>.*?)</a>',
  re.DOTALL,
)
# Any tag carrying the xref class, for checking the regex above misses none.
XREF_CLASS = re.compile(r'class="[^"]*\bxref\b[^"]*"')
# A heading in the rendered HTML, by id and title. A reference's text is the
# author's own words, so its page has to be looked up through the heading it
# targets; the bookmarks that carry pages are keyed by title, and this joins the
# two.
HEADING = re.compile(
  r'<h(?P<level>[123]) id="(?P<id>[^"]+)"[^>]*>(?P<title>.*?)</h(?P=level)>',
  re.DOTALL,
)
HTML_TAG = re.compile(r'<[^>]+>')
WHITESPACE = re.compile(r'\s+')


def stripped_text(markup: str) -> str:
  """The visible text of a markup fragment, with every space removed.

  A reference may wrap across lines, and `pdftotext` sets a space beside the
  inline-block suit symbols, so neither side of a comparison can keep its
  spacing.
  """
  return WHITESPACE.sub('', html.unescape(HTML_TAG.sub('', markup)))


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


# fontconfig's names for a face's slant, as a pattern like `Family:italic` asks.
type Slant = Literal['roman', 'italic']


def _installed_body_font(slant: Slant) -> Path:
  """The font file fontconfig serves for the stylesheet's body family.

  `slant` is fontconfig's name for the upright or the italic face. A fallback to
  another family fails here, since a test reading it would check the wrong face.
  """
  stylesheet = read(render_notes.STYLESHEET)
  body_rule = re.search(r'body \{(?P<declarations>[^}]*)\}', stylesheet)
  assert body_rule, 'no body rule in the stylesheet'
  family = re.search(
    r'font-family: "(?P<family>[^"]+)"', body_rule['declarations']
  )
  assert family, 'no quoted font family in the body rule'

  matched_font = subprocess.run(
    ['fc-match', '-f', '%{family}\t%{file}', f'{family["family"]}:{slant}'],
    capture_output=True,
    text=True,
    encoding='utf-8',
    check=True,
  ).stdout
  matched_family, _, font_file = matched_font.partition('\t')
  # A font can carry several family names; fc-match then reports them
  # comma-joined.
  assert family['family'] in matched_family.split(','), (
    f'no installed {slant} face for the body font: fontconfig offered '
    f'{matched_family!r}'
  )
  return Path(font_file)


def test_suit_skew_tracks_the_body_font_italic_angle() -> None:
  """Changing the body font must carry the suit skew along with it.

  Suit symbols lean inside italic text through an explicit `skewX` angle in the
  stylesheet, chosen to match the body font's italic angle. A future body face
  (`tasks.md` #serif-alternatives) ships an angle of its own, so this test reads
  both and fails until the stylesheet follows.
  """
  skew = re.search(
    r'\.suit \{\s*transform: skewX\((?P<degrees>-?[0-9.]+)deg\)',
    read(render_notes.STYLESHEET),
  )
  assert skew, 'no suit skew in the stylesheet'

  italic = _installed_body_font('italic')
  angle = _italic_angle(italic)
  # The tolerance lets the stylesheet round the angle to a whole degree.
  assert abs(float(skew['degrees']) - angle) <= 0.75, (
    f'the stylesheet skews suits {skew["degrees"]}° but {italic.name} leans at '
    f'{angle:.2f}°'
  )


def test_no_digit_is_wider_than_the_page_number_stand_in() -> None:
  """The probe's `88` must stay at least as wide as any real page number.

  `print_layout.PROBE_STYLESHEET` measures every page number as `88`, which errs
  safely only while no digit in the body font is wider than `8`. A future body
  face (`tasks.md` #serif-alternatives) may size its digits unevenly, so this
  test fails until the stand-in follows. Both faces count: the table of contents
  prints its numbers upright, and a cross-reference prints its in italic.
  """
  slants: tuple[Slant, ...] = ('roman', 'italic')
  for slant in slants:
    face = TTFont(_installed_body_font(slant))
    glyph_names = face.getBestCmap()
    # The `hmtx` table pairs each glyph's advance width with its left side
    # bearing; the advance is the room the glyph takes on the line.
    widths = {
      digit: face['hmtx'][glyph_names[ord(digit)]][0] for digit in string.digits
    }
    assert widths['8'] == max(widths.values()), (
      f'a {slant} digit is wider than the stand-in `8`: {widths}'
    )


# --- stylesheet coupling ---


def test_print_geometry_tracks_the_stylesheet() -> None:
  """notes.css owns the print geometry; the packer's copies must follow."""
  stylesheet = read(render_notes.STYLESHEET)
  assert 'size: letter' in stylesheet, 'the @page size is not letter'
  margins = re.search(
    r'margin: (?P<top>[\d.]+)in (?P<side>[\d.]+)in (?P<bottom>[\d.]+)in;',
    stylesheet,
  )
  assert margins, 'no three-value @page margin in the stylesheet'
  content_height = (11 - float(margins['top']) - float(margins['bottom'])) * 72
  assert content_height == print_layout.PAGE_CONTENT_HEIGHT

  probe_margin = re.search(
    r'margin: 0 (?P<side>[\d.]+)in', print_layout.PROBE_STYLESHEET
  )
  assert probe_margin, 'no horizontal margin in the probe stylesheet'
  assert probe_margin['side'] == margins['side']

  column = re.search(
    r'\.print-column \{\s*width: (?P<width>[\d.]+)in', stylesheet
  )
  assert column, 'no .print-column width in the stylesheet'
  probe_width = re.search(
    r'> \.section \{\s*width: (?P<width>[\d.]+)in',
    print_layout.PROBE_STYLESHEET,
  )
  assert probe_width, 'no .section width in the probe stylesheet'
  assert probe_width['width'] == column['width']

  # The probe pins reference text to a two-digit stand-in; it must track the
  # real reference format, or every atom carrying references measures short.
  reference = re.search(
    r'a\.xref::after \{\s*content: "(?P<prefix>[^"]*)" '
    r'target-counter\(attr\(href\), page\) "(?P<suffix>[^"]*)";',
    stylesheet,
  )
  assert reference, 'no printed-reference format in the stylesheet'
  stand_in = f"content: '{reference['prefix']}88{reference['suffix']}'"
  assert stand_in in print_layout.PROBE_STYLESHEET

  # The values must also cohere: two columns and their gutter fill the content
  # width exactly, and the wide-body column gap matches the gutter.
  gap = re.search(r'column-gap: (?P<gap>[\d.]+)in', stylesheet)
  assert gap, 'no wide-body column gap in the stylesheet'
  content_width = 8.5 - 2 * float(margins['side'])
  gutter = content_width - 2 * float(column['width'])
  assert round(gutter, 4) == float(gap['gap'])


def test_text_marker_ladder_tracks_the_stylesheet() -> None:
  """notes.css owns the list-marker ladder; the text rendering must follow."""
  # The markers come back in the order the stylesheet declares them, which is
  # depth order: each rule nests one `ul` deeper than the rule above it.
  markers = re.findall(
    r'list-style-type: "(.) ";', read(render_notes.STYLESHEET)
  )
  assert tuple(markers) == render_notes.LIST_MARKERS


# --- page references ---


def _heading_pages_by_stripped_key(pdf: Path) -> dict[str, int]:
  """Each heading's printed page, keyed by its title with spacing removed.

  WeasyPrint writes one PDF bookmark per heading, carrying the page. Dropping
  the spacing lets a title that wrapped in the PDF match the HTML's.
  """
  pages: dict[str, int] = {}
  for title, page in pdf_inspection.heading_pages(pdf).items():
    key = WHITESPACE.sub('', title)
    # Two distinct titles must not meet at one key, or a reference could be
    # checked against the wrong heading's page.
    assert key not in pages, f'titles collide when stripped: {title!r}'
    pages[key] = page
  return pages


def _reference_targets(document: str) -> dict[str, str]:
  """Each cross-reference's printed text, by the heading id it points at."""
  links = list(CROSS_REFERENCE_LINK.finditer(document))
  assert links, 'the fixture should contain cross-references'
  assert len(links) == len(XREF_CLASS.findall(document)), (
    'some cross-reference eluded CROSS_REFERENCE_LINK'
  )
  targets: dict[str, str] = {}
  for link in links:
    text = stripped_text(link['text'])
    # A reference is found in the PDF by its text alone, so one wording must not
    # lead to two headings, whose pages would differ.
    assert targets.setdefault(text, link['target']) == link['target'], (
      f'reference {text!r} points at two headings'
    )
  return targets


def test_every_printed_page_reference_is_correct(
  rendered: render_notes.RenderedNotes,
) -> None:
  """Each cross-reference's "(p. N)" names the page of the heading it targets.

  The references are enumerated from the HTML, so every one is checked. A
  reference's text is the author's own words, so the heading comes from the
  link's target id, and the page from that heading's PDF bookmark.
  """
  document = read(rendered.html)
  heading_pages = _heading_pages_by_stripped_key(rendered.pdf)
  titles = {
    heading['id']: stripped_text(heading['title'])
    for heading in HEADING.finditer(document)
  }
  targets = _reference_targets(document)
  pdf_text = WHITESPACE.sub('', pdf_inspection.extract_text(rendered.pdf))

  # Longest first, each consumed once checked: a short reference can appear as
  # the tail of a longer one ('Stayman' inside 'Garbage Stayman'), so a checked
  # one must not match again.
  for text in sorted(targets, key=len, reverse=True):
    title = titles[targets[text]]
    assert title in heading_pages, f'no bookmark for heading {title!r}'
    reference = re.compile(re.escape(text) + r'\(p\.(\d+)\)')
    printed_pages = reference.findall(pdf_text)
    assert printed_pages, f'reference {text!r} is not printed with a page'
    assert {int(page) for page in printed_pages} == {heading_pages[title]}, (
      f'{text!r} is printed with pages {printed_pages} but {title!r} is on '
      f'page {heading_pages[title]}'
    )
    pdf_text = reference.sub('', pdf_text)
