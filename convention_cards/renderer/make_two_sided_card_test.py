# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

"""Tests for the two-sided print-sheet tool's browserless pieces.

The Chromium conversion itself is exercised by regenerating the real card; these
tests cover the input guard and the sheet composition.
"""

from io import BytesIO

import pypdfium2
import pytest
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from renderer.make_two_sided_card import (
  PAGE_HEIGHT,
  compose_sheet,
  convert_html_card,
)


def _make_pdf_with_mark(
  page_size: tuple[int, int], mark_box: tuple[float, float, float, float]
) -> bytes:
  """A one-page PDF of the given size with one black rectangle on it."""
  buffer = BytesIO()
  page = canvas.Canvas(buffer, pagesize=page_size)
  page.setFillColorRGB(0, 0, 0)
  left, bottom, width, height = mark_box
  page.rect(left, bottom, width, height, stroke=0, fill=1)
  page.save()
  return buffer.getvalue()


def _ink_box(
  pdf_bytes: bytes, page_index: int, floor: float = 0
) -> tuple[float, ...]:
  """A letter page's ink bounding box in PDF points, origin bottom-left.

  `floor` crops away everything below that y before measuring, so a test can
  isolate ink above the cut guide.
  """
  document = pypdfium2.PdfDocument(pdf_bytes)
  try:
    image = document[page_index].render(scale=2, may_draw_forms=False).to_pil()
  finally:
    document.close()
  if floor:
    image = image.crop((0, 0, image.width, round((PAGE_HEIGHT - floor) * 2)))
  box = image.convert('L').point(lambda value: value < 240).getbbox()
  assert box is not None
  left, top, right, bottom = box
  return (left / 2, PAGE_HEIGHT - bottom / 2, right / 2, PAGE_HEIGHT - top / 2)


# --- HTML guard ---


def test_unrecognized_font_stack_is_rejected_by_name() -> None:
  html = '<style>#card { font-family: sans-serif; }</style>\n<main>card</main>'

  # The stack check precedes any browser launch, so this stays browserless.
  with pytest.raises(ValueError, match='font-family'):
    convert_html_card(html)


# --- sheet composition ---


def _compose_marked_sheet() -> bytes:
  """Compose from synthetic inputs, each carrying one locating mark.

  The ACBL stand-in marks its bottom-left corner; the HTML stand-in marks the
  card content's top-left corner (the 12.96pt hard margin inside the page's
  top-left, where the real body's padding places it).
  """
  acbl_pdf = _make_pdf_with_mark((576, 612), (0, 0, 20, 10))
  html_pdf = _make_pdf_with_mark((612, 792), (12.96, 769.04, 20, 10))
  return compose_sheet(acbl_pdf, html_pdf)


def test_composition_yields_two_letter_pages() -> None:
  sheet = _compose_marked_sheet()

  pages = PdfReader(BytesIO(sheet)).pages
  assert len(pages) == 2
  assert all(page.mediabox.width == 612 for page in pages)
  assert all(page.mediabox.height == 792 for page in pages)


def test_front_lays_the_acbl_card_upright_above_the_cut() -> None:
  sheet = _compose_marked_sheet()

  # Look above the dashed guide, so the mark alone shapes the ink box.
  left, bottom, right, top = _ink_box(sheet, 0, floor=190)

  # The card prints upright at ~95.8%: its bottom-left corner mark (20 wide x 10
  # tall) lands at the content band's bottom-left — x from 30.2, where the
  # leftover width splits evenly between the two sides, and y from 192.96, the
  # cut allowance above the cut — spanning 19.2 x 9.6.
  assert left == pytest.approx(30.2, abs=0.5)
  assert right == pytest.approx(49.4, abs=0.5)
  assert bottom == pytest.approx(192.96, abs=0.5)
  assert top == pytest.approx(202.5, abs=0.5)


def test_back_carries_the_html_page_unmoved() -> None:
  sheet = _compose_marked_sheet()

  left, bottom, right, top = _ink_box(sheet, 1)

  # The HTML card sits in its page's top band, which coincides with the piece's
  # band on the sheet — so the mark at the card content's top-left corner stays
  # exactly where the conversion drew it: (12.96, 769.04) up to (32.96, 779.04).
  assert left == pytest.approx(12.96, abs=0.5)
  assert right == pytest.approx(32.96, abs=0.5)
  assert bottom == pytest.approx(769.04, abs=0.5)
  assert top == pytest.approx(779.04, abs=0.5)


def test_front_holds_the_hard_margin_around_a_full_bleed_acbl_render() -> None:
  acbl_pdf = _make_pdf_with_mark((576, 612), (0, 0, 576, 612))
  html_pdf = _make_pdf_with_mark((612, 792), (12.96, 769.04, 20, 10))

  sheet = compose_sheet(acbl_pdf, html_pdf)
  left, bottom, right, top = _ink_box(sheet, 0)

  # A card inked to the very edge of its box scales to ~95.8% and hangs upright
  # from the top hard margin, its height spanning the budget down to the cut
  # allowance; the inset guide's ends, at 12.96 and 599.04, hold the widest ink,
  # and its dashes below the cut hold the lowest.
  assert left == pytest.approx(12.96, abs=0.5)
  assert right == pytest.approx(599.04, abs=0.5)
  assert top == pytest.approx(779.04, abs=0.5)
  assert bottom == pytest.approx(185, abs=1)


def test_a_wrong_sized_acbl_render_is_rejected() -> None:
  letter_pdf = _make_pdf_with_mark((612, 792), (0, 0, 10, 10))

  with pytest.raises(ValueError, match='expected 576 x 612'):
    compose_sheet(letter_pdf, letter_pdf)
