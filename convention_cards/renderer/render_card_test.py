# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

"""End-to-end tests: JSON in, ACBL card PDF out.

The pixel tests rasterize through pypdfium2: the blank card must match the
original exactly — the core pixel-perfection guarantee — and entries must land
where they belong. The placement checks render onto a base card with the real
card's fields but none of its artwork, so the card's printing can neither hide
an entry nor pass for one; the golden test covers where entries land among the
artwork.
"""

import functools
import json
from collections.abc import Mapping
from io import BytesIO, StringIO
from pathlib import Path
from typing import NamedTuple

import pypdfium2
import pytest
from bridgodex_key import BridgodexKey
from PIL import Image, ImageChops
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, NullObject

from renderer.fonts import register_entry_fonts
from renderer.geometry import CARD_HEIGHT, CARD_WIDTH
from renderer.overlay import DEFAULT_SIZE_FLOOR
from renderer.regenerate_goldens import (
  FULL_EXPORT_GOLDEN_PATH,
  renderable_full_export,
)
from renderer.regenerate_goldens import (
  rasterize as rasterize_at_golden_scale,
)
from renderer.render_card import (
  DEFAULT_BASE_PDF_PATH,
  BaseCard,
  RenderResult,
  load_base_card,
  main,
  render_card,
)
from renderer.rule_positions import RULE_TOPS
from renderer.vocabulary import UNRENDERED_KEYS, VOCABULARY

_BASE_PDF_BYTES = DEFAULT_BASE_PDF_PATH.read_bytes()

# Parsed once and shared, as `BaseCard` allows: parsing the card costs several
# times what a render does.
_BASE_CARD = load_base_card(BytesIO(_BASE_PDF_BYTES))

# The real card's fields over an empty page. A render onto it holds only what
# the entries draw, with none of the card's printed artwork around them. It also
# runs several times faster than a render onto the real card, so tests that need
# nothing from the artwork render here.
_CARD_WITHOUT_ARTWORK = BaseCard(
  page=PdfWriter().add_blank_page(CARD_WIDTH, CARD_HEIGHT),
  fields=_BASE_CARD.fields,
)

_FONTS = register_entry_fonts()

# 300 dpi, per spec.md #ink-resolution.
_RASTER_SCALE = 300 / 72


class _Box(NamedTuple):
  """A box on the card page, in points, with the origin at its bottom-left."""

  left: float
  bottom: float
  right: float
  top: float


_WHOLE_PAGE = _Box(0, 0, CARD_WIDTH, CARD_HEIGHT)


def _field_box(name: str) -> _Box:
  """The rectangle of one of the card's form fields."""
  field = _BASE_CARD.fields[name]
  return _Box(
    field.left,
    field.bottom,
    field.left + field.width,
    field.bottom + field.height,
  )


def _rasterize_ink(pdf_bytes: bytes, box: _Box = _WHOLE_PAGE) -> Image.Image:
  """Render one box of a PDF's single page on a transparent background.

  Only what the page draws is opaque, so a pixel's alpha says whether any ink
  landed there, whatever its color; on white, white ink would vanish. Use this
  on renders onto `_CARD_WITHOUT_ARTWORK`, to find what the entries drew: on the
  real card, the printed artwork would count as ink too.

  Form widgets are left out. A small box renders in a fraction of the time the
  whole page takes.

  To compare whole cards, use `rasterize_at_golden_scale` instead: it renders on
  white, the paper the card prints on, so the image shows the page as a reader
  sees it.
  """
  document = pypdfium2.PdfDocument(pdf_bytes)
  try:
    page = document[0]
    # PDFium crops by how far to cut in from each edge of the page.
    crop = (
      box.left,
      box.bottom,
      page.get_width() - box.right,
      page.get_height() - box.top,
    )
    bitmap = page.render(
      scale=_RASTER_SCALE,
      crop=crop,
      may_draw_forms=False,
      fill_color=(255, 255, 255, 0),
    )
    return bitmap.to_pil()
  finally:
    document.close()


def _ink_bounds(pdf_bytes: bytes) -> _Box | None:
  """The box around all the ink on a PDF's page, or None if there is none."""
  pixels = _rasterize_ink(pdf_bytes).getchannel('A').getbbox()
  if not pixels:
    return None
  # Pixel rows count down from the page's top edge, and points count up from its
  # bottom edge.
  left, top, right, bottom = pixels
  return _Box(
    left / _RASTER_SCALE,
    CARD_HEIGHT - bottom / _RASTER_SCALE,
    right / _RASTER_SCALE,
    CARD_HEIGHT - top / _RASTER_SCALE,
  )


def _has_ink(pdf_bytes: bytes, box: _Box) -> bool:
  """Whether a PDF's page draws anything inside `box`."""
  alpha = _rasterize_ink(pdf_bytes, box).getchannel('A')
  return alpha.getbbox() is not None


def _page_text(pdf_bytes: bytes) -> str:
  """Extract the text of a PDF's single page."""
  document = pypdfium2.PdfDocument(pdf_bytes)
  try:
    return document[0].get_textpage().get_text_range()
  finally:
    document.close()


def _render(
  settings: Mapping[str, object],
  notes: str = '',
  base_card: BaseCard = _BASE_CARD,
) -> RenderResult:
  """Run the renderer over `base_card`, by default the real card."""
  card_json = StringIO(json.dumps({'settings': settings, 'notes': notes}))
  return render_card(card_json, base_card, _FONTS)


def _render_without_artwork(settings: Mapping[str, object]) -> bytes:
  """Render the given settings onto `_CARD_WITHOUT_ARTWORK`, returning the PDF.

  Most callers, such as ink checks, just need the PDF bytes. Any test that also
  needs the render result, such as which entries were resized, should call
  `_render` directly.
  """
  return _render(settings, base_card=_CARD_WITHOUT_ARTWORK).pdf


@functools.cache
def _blank_card_pdf() -> bytes:
  """The rendered blank card, computed once and shared."""
  return _render({}).pdf


# --- pixel fidelity ---


def test_blank_card_matches_the_original_pixel_for_pixel() -> None:
  difference = ImageChops.difference(
    rasterize_at_golden_scale(_blank_card_pdf()),
    rasterize_at_golden_scale(_BASE_PDF_BYTES),
  )
  assert difference.getbbox() is None


def test_the_base_card_stays_blank_across_renders() -> None:
  # Every render shares one parsed base card, so a render that drew on it would
  # leak into every later one.
  before = _render({}).pdf
  _render({'names': {'names': 'First Last'}})

  assert _render({}).pdf == before


def test_an_entry_draws_only_inside_its_field() -> None:
  ink = _ink_bounds(_render_without_artwork({'names': {'names': 'First Last'}}))

  # A point of slack at each edge covers antialiasing and glyph overshoot.
  field = _field_box('Name.t.1')
  assert ink is not None
  assert ink.left >= field.left - 1
  assert ink.right <= field.right + 1
  assert ink.bottom >= field.bottom - 1
  assert ink.top <= field.top + 1


# --- form stripping ---


def test_output_carries_no_form_machinery() -> None:
  original = PdfReader(BytesIO(_BASE_PDF_BYTES))
  output = PdfReader(BytesIO(_blank_card_pdf()))

  # The original card carries both pieces, so the checks can see them.
  assert '/AcroForm' in original.root_object
  assert '/Annots' in original.pages[0]
  assert '/AcroForm' not in output.root_object
  assert '/Annots' not in output.pages[0]


# --- the overlay's form XObject ---


def test_a_base_card_already_using_the_overlays_name_is_rejected() -> None:
  # The overlay joins the card page's resources under the name /CardOverlay, so
  # a page already using that name is refused rather than overwritten.
  page = PdfWriter().add_blank_page(CARD_WIDTH, CARD_HEIGHT)
  page[NameObject('/Resources')] = DictionaryObject(
    {
      NameObject('/XObject'): DictionaryObject(
        {NameObject('/CardOverlay'): NullObject()}
      )
    }
  )
  base_card = BaseCard(page=page, fields=_BASE_CARD.fields)

  with pytest.raises(ValueError, match='CardOverlay'):
    render_card(StringIO('{"settings": {}}'), base_card, _FONTS)


# --- text entries and resizing ---


def test_a_fitting_entry_keeps_its_default_size() -> None:
  result = _render(
    {'names': {'names': 'First Last'}}, base_card=_CARD_WITHOUT_ARTWORK
  )

  assert result.resized == ()
  assert 'First Last' in _page_text(result.pdf)


def test_an_oversized_entry_shrinks_and_is_listed_as_resized() -> None:
  # Long enough to overflow the 238pt Name field at 10pt even in a condensed
  # face, short enough to still fit above the size floor.
  long_names = (
    'First Last, Second Partner, Third Person, Fourth Friend,'
    ' and every convention they have ever loved'
  )

  result = _render({'names': {'names': long_names}})

  assert len(result.resized) == 1
  entry = result.resized[0]
  assert entry.field_name == 'Name.t.1'
  assert entry.default_size == 10.0
  assert entry.fitted_size < 10.0
  assert entry.text == long_names


def test_an_overflowing_entry_wraps_onto_extra_lines() -> None:
  # Too long for one Name-field line even at the floor, so the fitter wraps —
  # and the wrapped size beats the old single-line minimum.
  long_names = 'First Last, Second Partner, and their many conventions' * 2

  result = _render({'names': {'names': long_names}})

  entry = result.resized[0]
  assert entry.line_count >= 2
  assert entry.fitted_size >= DEFAULT_SIZE_FLOOR


def test_wrapped_lines_stay_within_the_field_and_its_bleed() -> None:
  long_names = 'First Last, Second Partner, and their many conventions' * 2
  ink = _ink_bounds(_render_without_artwork({'names': {'names': long_names}}))

  # Wrapped lines may rise into the field's 2.5pt upward bleed, plus half a
  # point for antialiasing. Baselines sit on the field's rule, so descenders dip
  # a few points below the field — but no line may stack far outside it in
  # either direction.
  field = _field_box('Name.t.1')
  assert ink is not None
  assert ink.top <= field.top + 3
  assert ink.bottom >= field.bottom - 4


def _has_rule_extension(pdf_bytes: bytes, field_name: str) -> bool:
  """Whether a render carries a 1NT row's underline out to the shared edge.

  Looks for red in a strip hanging from the row's rule top, just short of the
  1NT panel's shared right edge at x=443.2, where an extension ends. Entry text
  may reach the strip too, but draws in the entry color, never red, as long as
  it holds no red suit symbol.
  """
  rule_top = RULE_TOPS[field_name]
  strip = _rasterize_ink(
    pdf_bytes, _Box(438, rule_top - 1, 443, rule_top + 0.5)
  )
  data = strip.convert('RGB').tobytes()
  return any(
    data[index] > 180 and data[index + 1] < 90 and data[index + 2] < 90
    for index in range(0, len(data), 3)
  )


def test_an_entry_overflowing_its_rule_extends_the_underline() -> None:
  long_entry = _render_without_artwork(
    {'1_no_trump': {'2d_other': 'tfr, then asking'}}
  )

  # The 1NT "Other" row's printed underline ends at x=424.8; the entry above
  # overflows it, so the underline must continue to the shared right edge.
  assert _has_rule_extension(long_entry, '1NT.t.11')


# One overflowing entry must extend the underlines of the whole 1NT family — a
# fitting sibling and a blank row alike — so the aligned column keeps a single
# right edge.
_ONE_OVERFLOWING_1NT_ENTRY = {
  '1_no_trump': {'2h_other': 'tfr, then asking', '2d_other': 'short'}
}


def test_a_sibling_overflow_extends_a_fitting_rows_rule() -> None:
  extended = _render_without_artwork(_ONE_OVERFLOWING_1NT_ENTRY)

  # The fitting 'short' entry's row.
  assert _has_rule_extension(extended, '1NT.t.11')


def test_a_sibling_overflow_extends_a_blank_rows_rule() -> None:
  extended = _render_without_artwork(_ONE_OVERFLOWING_1NT_ENTRY)

  # A row with no entry at all.
  assert _has_rule_extension(extended, '1NT.t.17')


def test_a_fitting_entry_leaves_its_printed_rule_alone() -> None:
  short_entry = _render_without_artwork({'1_no_trump': {'2d_other': 'short'}})
  long_entry = _render_without_artwork(
    {'1_no_trump': {'2d_other': 'tfr, then asking'}}
  )

  # A fitting entry must not draw anything in the gutter around its row's rule,
  # from its field's right edge to just past the shared right edge at x=443.2:
  # no extension, no stray ink. An overflowing entry in the same row does draw
  # there, so the probe can see what it's looking for.
  rule_top = RULE_TOPS['1NT.t.11']
  field = _field_box('1NT.t.11')
  gutter = _Box(field.right, rule_top - 2.5, 444, rule_top + 2.5)
  assert _has_ink(long_entry, gutter)
  assert not _has_ink(short_entry, gutter)


def test_an_unfittable_entry_is_rejected_naming_the_field() -> None:
  with pytest.raises(ValueError, match=r'Name\.t\.1'):
    _render({'names': {'names': 'too long ' * 60}})


def test_font_subfont_without_font_is_rejected() -> None:
  # argparse exits before any file access, so no input files are needed.
  with pytest.raises(SystemExit):
    main(['card.json', 'out.pdf', '--font-subfont', '1'])


def test_the_size_floor_argument_reaches_the_fitting_engine() -> None:
  # This text overflows the default floor; an explicit lower floor must let it
  # render instead of raising.
  overflowing_settings = {'names': {'names': 'too long ' * 60}}
  card_json = StringIO(
    json.dumps({'settings': overflowing_settings, 'notes': ''})
  )

  result = render_card(card_json, _CARD_WITHOUT_ARTWORK, _FONTS, size_floor=0.2)

  assert result.resized[0].field_name == 'Name.t.1'


# --- input validation ---


def test_an_unknown_key_is_rejected_by_name() -> None:
  with pytest.raises(ValueError, match=r'majors\.mystery'):
    _render({'majors': {'mystery': 'on'}})


def test_a_non_string_text_value_is_rejected() -> None:
  with pytest.raises(ValueError, match=r'names\.names'):
    _render({'names': {'names': 7}})


def test_nonempty_notes_are_rejected() -> None:
  with pytest.raises(ValueError, match='notes'):
    _render({}, notes='remember to alert')


def test_unknown_top_level_keys_are_rejected() -> None:
  card_json = StringIO(json.dumps({'settings': {}, 'surprise': 1}))

  with pytest.raises(ValueError, match='surprise'):
    render_card(card_json, _BASE_CARD, _FONTS)


def test_an_unrendered_key_with_content_is_rejected() -> None:
  # Bridgodex offers 1_no_trump.2c_other but no card layout prints it; text
  # there would silently vanish, so the renderer refuses it.
  with pytest.raises(ValueError, match='never renders'):
    _render({'1_no_trump': {'2c_other': 'range ask'}})


def test_an_unrendered_key_with_an_empty_value_is_ignored() -> None:
  result = _render({'1_no_trump': {'2c_other': ''}})

  assert result.resized == ()


def test_a_checkbox_value_other_than_on_is_rejected() -> None:
  with pytest.raises(ValueError, match='drury_2c'):
    _render({'majors': {'drury_2c': 'off'}})


# --- lead-chart circles ---


def test_a_lead_circle_rings_the_selected_card() -> None:
  ink = _ink_bounds(
    _render_without_artwork({'leads_vs_suits': {'honor_leads_KQx': 2}})
  )

  # The Q of the printed KQx holding sits at x 29.4-33.8, y 34.3-41.0 (PDF
  # points); the ring hugs that box, so allow a few points of slack.
  assert ink is not None
  assert ink.left >= 26
  assert ink.right <= 37
  assert ink.bottom >= 31
  assert ink.top <= 44


def test_an_out_of_range_circle_position_is_rejected() -> None:
  # KQx has three cards, so position 4 is invalid.
  with pytest.raises(ValueError, match='honor_leads_KQx'):
    _render({'leads_vs_suits': {'honor_leads_KQx': 4}})


def test_a_boolean_circle_position_is_rejected() -> None:
  # JSON true must not sneak through as position 1 (bool subclasses int).
  with pytest.raises(ValueError, match='honor_leads_KQx'):
    _render({'leads_vs_suits': {'honor_leads_KQx': True}})


# --- the full vocabulary ---


def _full_export_settings() -> dict[str, dict[str, object]]:
  """Load the all-fields-set export fixture's settings."""
  fixture = Path(__file__).resolve().parent / 'testdata' / 'full_export.json'
  document = json.loads(fixture.read_text())
  assert isinstance(document, dict)
  settings = document['settings']
  assert isinstance(settings, dict)
  return settings


def test_the_fixture_covers_every_vocabulary_and_unrendered_key() -> None:
  # The fixture is the full Bridgodex export with every field set, so every key
  # the renderer knows about must appear in it — a missing key means the fixture
  # (or the vocabulary) has drifted.
  fixture_keys = {
    BridgodexKey(section_name, key)
    for section_name, section in _full_export_settings().items()
    for key in section
  }

  assert set(VOCABULARY) | UNRENDERED_KEYS <= fixture_keys


def test_the_full_export_renders_once_unrendered_keys_are_removed() -> None:
  settings = _full_export_settings()
  for setting in UNRENDERED_KEYS:
    settings[setting.section].pop(setting.key, None)

  result = _render(settings)

  # Spot check that entries actually landed on the card, using the fixture's
  # general-approach entry.
  text = _page_text(result.pdf)
  assert '2/1 game forcing, five-card majors' in text


def test_the_full_export_matches_its_committed_golden() -> None:
  # Pixel-level regression net over the whole card; regenerate with
  # `renderer.regenerate_goldens` after intentional rendering changes.
  result = render_card(StringIO(renderable_full_export()), _BASE_CARD, _FONTS)

  fresh = rasterize_at_golden_scale(result.pdf)
  golden = Image.open(FULL_EXPORT_GOLDEN_PATH).convert(fresh.mode)
  assert ImageChops.difference(fresh, golden).getbbox() is None
