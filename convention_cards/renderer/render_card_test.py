# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

"""End-to-end tests: JSON in, ACBL card PDF out.

The pixel tests rasterize through pypdfium2: the blank card must match the
original exactly — the core pixel-perfection guarantee — and entries must change
pixels without disturbing anything else.
"""

import json
from collections.abc import Mapping
from io import BytesIO, StringIO
from pathlib import Path

import pypdfium2
import pytest
from bridgodex_key import BridgodexKey
from PIL import Image, ImageChops
from pypdf import PdfReader
from pypdf.generic import DictionaryObject

from renderer.fonts import register_entry_fonts
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
  RenderResult,
  main,
  render_card,
)
from renderer.vocabulary import UNRENDERED_KEYS, VOCABULARY

_BASE_PDF_BYTES = DEFAULT_BASE_PDF_PATH.read_bytes()

_FONTS = register_entry_fonts()

_RASTER_SCALE = 300 / 72  # 300 dpi


def _rasterize(pdf_bytes: bytes) -> Image.Image:
  """Render a PDF's single page to an image, ignoring form widgets."""
  document = pypdfium2.PdfDocument(pdf_bytes)
  try:
    page = document[0]
    return page.render(scale=_RASTER_SCALE, may_draw_forms=False).to_pil()
  finally:
    document.close()


def _render(
  settings: Mapping[str, object],
  notes: str = '',
) -> RenderResult:
  """Run the renderer over the real base card with the given settings."""
  card_json = StringIO(json.dumps({'settings': settings, 'notes': notes}))
  return render_card(card_json, BytesIO(_BASE_PDF_BYTES), _FONTS)


# --- pixel fidelity ---


def test_blank_card_matches_the_original_pixel_for_pixel() -> None:
  result = _render({})

  difference = ImageChops.difference(
    _rasterize(result.pdf), _rasterize(_BASE_PDF_BYTES)
  )
  assert difference.getbbox() is None


def test_an_entry_changes_pixels_only_inside_its_field() -> None:
  blank = _rasterize(_render({}).pdf)
  named = _rasterize(_render({'names': {'names': 'First Last'}}).pdf)

  changed = ImageChops.difference(blank, named).getbbox()
  assert changed is not None

  # The Name field spans x in [332.6, 571.0], y in [594.3, 608.2] (PDF points,
  # origin bottom-left). In image coordinates (origin top-left), that is y in
  # [612 - 608.2, 612 - 594.3] scaled to pixels.
  left, top, right, bottom = changed
  assert left >= 332 * _RASTER_SCALE
  assert right <= 572 * _RASTER_SCALE
  assert top >= (612 - 609) * _RASTER_SCALE
  assert bottom <= (612 - 594) * _RASTER_SCALE


# --- form stripping ---


def test_output_carries_no_form_machinery() -> None:
  reader = PdfReader(BytesIO(_render({}).pdf))

  root = reader.trailer['/Root'].get_object()
  assert isinstance(root, DictionaryObject)
  assert '/AcroForm' not in root
  assert '/Annots' not in reader.pages[0]


# --- text entries and resizing ---


def test_a_fitting_entry_keeps_its_default_size() -> None:
  result = _render({'names': {'names': 'First Last'}})

  assert result.resized == ()
  assert 'First Last' in PdfReader(BytesIO(result.pdf)).pages[0].extract_text()


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
  blank = _rasterize(_render({}).pdf)
  long_names = 'First Last, Second Partner, and their many conventions' * 2
  wrapped = _rasterize(_render({'names': {'names': long_names}}).pdf)

  changed = ImageChops.difference(blank, wrapped).getbbox()
  assert changed is not None

  # The Name field spans y in [594.3, 608.2]pt plus a small upward bleed, so ink
  # may start no higher than ~611pt. Baselines sit on the field's rule, so
  # descenders dip a couple of points below it — but no line may stack far
  # outside the field in either direction.
  _left, top, _right, bottom = changed
  assert top >= (612 - 611) * _RASTER_SCALE
  assert bottom <= (612 - 590) * _RASTER_SCALE


def _has_red_bar_ink(card: Image.Image, bar_y: float) -> bool:
  """Whether the far-end extension strip around one bar height holds red ink.

  The strip (x in [438, 443]) sits past any entry text's reach, so only an
  underline extension can put ink there.
  """
  strip = card.convert('RGB').crop(
    (
      int(438 * _RASTER_SCALE),
      int((612 - bar_y - 0.6) * _RASTER_SCALE),
      int(443 * _RASTER_SCALE),
      int((612 - bar_y + 0.6) * _RASTER_SCALE),
    )
  )
  data = strip.tobytes()
  return any(
    data[index] > 180 and data[index + 1] < 90 and data[index + 2] < 90
    for index in range(0, len(data), 3)
  )


def test_an_entry_overflowing_its_rule_extends_the_underline() -> None:
  blank = _rasterize(_render({}).pdf)
  long_entry = _rasterize(
    _render({'1_no_trump': {'2d_other': 'tfr, then asking'}}).pdf
  )

  # The 1NT "Other" row's printed underline (bar y 274.6) ends at x=424.8; the
  # entry above overflows it, so the underline must continue toward the shared
  # right edge at x=443.2 — red ink in the far-end strip only an extension
  # reaches, absent from the blank card.
  assert _has_red_bar_ink(long_entry, bar_y=274.6)
  assert not _has_red_bar_ink(blank, bar_y=274.6)


# One overflowing entry must extend the underlines of the whole 1NT family — a
# fitting sibling and a blank row alike — so the aligned column keeps a single
# right edge.
_ONE_OVERFLOWING_1NT_ENTRY = {
  '1_no_trump': {'2h_other': 'tfr, then asking', '2d_other': 'short'}
}


def test_a_sibling_overflow_extends_a_fitting_rows_rule() -> None:
  extended = _rasterize(_render(_ONE_OVERFLOWING_1NT_ENTRY).pdf)

  # The fitting 'short' entry's row: field 1NT.t.11, bar at y=274.4-274.7.
  assert _has_red_bar_ink(extended, bar_y=274.6)


def test_a_sibling_overflow_extends_a_blank_rows_rule() -> None:
  extended = _rasterize(_render(_ONE_OVERFLOWING_1NT_ENTRY).pdf)

  # A row with no entry at all: field 1NT.t.17, bar at y=252.3-252.7.
  assert _has_red_bar_ink(extended, bar_y=252.5)


def test_a_fitting_entry_leaves_its_printed_rule_alone() -> None:
  blank = _rasterize(_render({}).pdf)
  short_entry = _rasterize(_render({'1_no_trump': {'2d_other': 'short'}}).pdf)

  # A fitting entry must not redraw anything in the gutter right of its field's
  # end (x=425.3): no extension, no stray ink.
  left = int(426 * _RASTER_SCALE)
  right = int(444 * _RASTER_SCALE)
  top = int((612 - 277) * _RASTER_SCALE)
  bottom = int((612 - 272) * _RASTER_SCALE)
  difference = ImageChops.difference(
    blank.crop((left, top, right, bottom)),
    short_entry.crop((left, top, right, bottom)),
  )
  assert difference.getbbox() is None


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

  result = render_card(
    card_json, BytesIO(_BASE_PDF_BYTES), _FONTS, size_floor=0.2
  )

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
    render_card(card_json, BytesIO(_BASE_PDF_BYTES), _FONTS)


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
  blank = _rasterize(_render({}).pdf)
  circled = _rasterize(_render({'leads_vs_suits': {'honor_leads_KQx': 2}}).pdf)

  changed = ImageChops.difference(blank, circled).getbbox()
  assert changed is not None

  # The Q of the printed KQx holding sits at x 29.4-33.8, y 34.3-41.0 (PDF
  # points); the ring hugs that box, so allow a few points of slack.
  left, top, right, bottom = changed
  assert left >= 26 * _RASTER_SCALE
  assert right <= 37 * _RASTER_SCALE
  assert top >= (612 - 44) * _RASTER_SCALE
  assert bottom <= (612 - 31) * _RASTER_SCALE


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
  text = PdfReader(BytesIO(result.pdf)).pages[0].extract_text()
  assert '2/1 game forcing, five-card majors' in text


def test_the_full_export_matches_its_committed_golden() -> None:
  # Pixel-level regression net over the whole card; regenerate with
  # `renderer.regenerate_goldens` after intentional rendering changes.
  result = render_card(
    StringIO(renderable_full_export()), BytesIO(_BASE_PDF_BYTES), _FONTS
  )

  fresh = rasterize_at_golden_scale(result.pdf)
  golden = Image.open(FULL_EXPORT_GOLDEN_PATH).convert(fresh.mode)
  assert ImageChops.difference(fresh, golden).getbbox() is None
