# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

"""Tests for field geometry read from the real ACBL card."""

import functools
from collections.abc import Mapping
from io import BytesIO

import pytest
from reportlab.pdfgen.canvas import Canvas

from renderer.geometry import CardField, FieldKind, load_card_fields
from renderer.private_paths import discover_private_assets

_BASE_PDF_PATH = discover_private_assets().base_acbl_card_pdf


@functools.cache
def _load_real_card() -> Mapping[str, CardField]:
  """The real card's fields, loaded once and shared across these tests."""
  return load_card_fields(BytesIO(_BASE_PDF_PATH.read_bytes()))


def test_every_widget_on_the_card_is_loaded() -> None:
  fields = _load_real_card()

  # The official card defines 148 text fields and 207 checkboxes.
  kinds = [field.kind for field in fields.values()]
  assert kinds.count(FieldKind.TEXT) == 148
  assert kinds.count(FieldKind.CHECKBOX) == 207


def test_the_name_field_has_its_known_geometry() -> None:
  field = _load_real_card()['Name.t.1']

  assert field.kind is FieldKind.TEXT
  assert field.default_font_size == 10.0
  assert field.bottom == pytest.approx(594.32, abs=0.01)
  assert field.left == pytest.approx(332.64, abs=0.01)
  assert field.width == pytest.approx(238.32, abs=0.01)
  assert field.height == pytest.approx(13.86, abs=0.01)


def test_checkboxes_carry_no_font_size() -> None:
  field = _load_real_card()['D.c.1']

  assert field.kind is FieldKind.CHECKBOX
  assert field.default_font_size is None


def test_a_wrong_sized_base_pdf_is_rejected() -> None:
  buffer = BytesIO()
  canvas = Canvas(buffer, pagesize=(100, 100))
  canvas.showPage()  # an untouched canvas would save zero pages
  canvas.save()

  with pytest.raises(ValueError, match='expected'):
    load_card_fields(BytesIO(buffer.getvalue()))
