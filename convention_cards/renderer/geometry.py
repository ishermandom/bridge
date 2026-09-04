# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

"""Field geometry read from the ACBL card's own fillable form.

The official card PDF is a form whose widgets sit exactly where entered content
belongs, so the form doubles as a geometry database: each widget supplies a
name, a rectangle, a kind, and (for text fields) a default font size. The
renderer never fills the form — it draws its own overlay at these rectangles
(see `spec.md`).
"""

import enum
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import BinaryIO

from pypdf import PdfReader
from pypdf.generic import ArrayObject, DictionaryObject

# The card page's size in PDF points (8" x 8.5"). The loader verifies the base
# PDF against these, so a revised ACBL card fails loudly rather than rendering a
# misaligned overlay.
CARD_WIDTH = 576.0
CARD_HEIGHT = 612.0

# A /DA (default appearance) string names a font and size, e.g. '/ArialMT 10 Tf
# 0 g'. Only the size matters here: it becomes the entry's starting font size
# before any shrink-to-fit.
_DA_FONT_NAME = r'/\S+'
_DA_FONT_SIZE = r'(?P<size>\d+(?:\.\d+)?)'
_DA_PATTERN = re.compile(rf'{_DA_FONT_NAME}\s+{_DA_FONT_SIZE}\s+Tf')


class FieldKind(enum.Enum):
  """What a form field holds — decides how the overlay draws into it."""

  TEXT = enum.auto()
  CHECKBOX = enum.auto()


_KIND_BY_FIELD_TYPE = {
  '/Tx': FieldKind.TEXT,
  '/Btn': FieldKind.CHECKBOX,
}


@dataclass(frozen=True)
class CardField:
  """One form widget: where it sits and how entries into it start out.

  Every measurement is in PDF points (1/72 inch). Positions use the card page's
  own coordinates, which the overlay's canvas shares: the origin is the page's
  bottom-left corner, and y grows upward. `bottom` and `left` place the widget
  rectangle's bottom-left corner; `width` and `height` give its extent.

  `default_font_size` is the size parsed from the field's /DA string — the size
  an entry starts at before shrink-to-fit. Checkboxes hold no text, so theirs is
  None.
  """

  name: str
  kind: FieldKind
  bottom: float
  left: float
  width: float
  height: float
  default_font_size: float | None


def load_card_fields(base_pdf: BinaryIO) -> Mapping[str, CardField]:
  """Read every form widget on the card into a name -> CardField mapping.

  Raises:
    ValueError: if the PDF's page or form doesn't match the card this module
      expects.
  """
  reader = PdfReader(base_pdf)
  page = reader.pages[0]

  size = page.mediabox
  if (float(size.width), float(size.height)) != (CARD_WIDTH, CARD_HEIGHT):
    raise ValueError(
      f'base PDF page is {size.width} x {size.height} pt,'
      f' expected {CARD_WIDTH} x {CARD_HEIGHT}'
    )

  annotations = _resolved(page, '/Annots')
  if not isinstance(annotations, ArrayObject):
    raise ValueError('base PDF page has no annotation array')

  fields: dict[str, CardField] = {}
  for reference in annotations:
    widget = reference.get_object()
    if not isinstance(widget, DictionaryObject):
      raise ValueError(f'annotation is not a dictionary: {widget!r}')
    if widget.get('/Subtype') != '/Widget':
      continue

    field = _read_widget(widget)
    if field.name in fields:
      raise ValueError(f'duplicate field name {field.name!r}')
    fields[field.name] = field

  if not fields:
    raise ValueError('base PDF has no form widgets')
  return fields


def _read_widget(widget: DictionaryObject) -> CardField:
  """Build one CardField from a widget annotation dictionary."""
  name = _qualified_name(widget)

  field_type = str(_inherited(widget, '/FT'))
  kind = _KIND_BY_FIELD_TYPE.get(field_type)
  if kind is None:
    raise ValueError(f'field {name!r} has unsupported type {field_type}')

  rect = _resolved(widget, '/Rect')
  if not isinstance(rect, ArrayObject) or len(rect) != 4:
    raise ValueError(f'field {name!r} has no valid /Rect')
  left, bottom, right, top = (float(value) for value in rect)

  default_font_size = (
    _default_font_size(widget, name) if kind is FieldKind.TEXT else None
  )

  return CardField(
    name=name,
    kind=kind,
    bottom=bottom,
    left=left,
    width=right - left,
    height=top - bottom,
    default_font_size=default_font_size,
  )


def _default_font_size(widget: DictionaryObject, name: str) -> float:
  """Parse the text size out of the field's /DA appearance string."""
  appearance = _inherited(widget, '/DA')
  match = _DA_PATTERN.search(str(appearance)) if appearance else None
  if match is None:
    raise ValueError(f'field {name!r} has no font size in /DA {appearance!r}')
  return float(match.group('size'))


def _qualified_name(widget: DictionaryObject) -> str:
  """Join the widget's partial names up the parent chain, e.g. 'Name.t.1'."""
  parts: list[str] = []
  node: DictionaryObject | None = widget
  while node is not None:
    partial = node.get('/T')
    if partial is not None:
      parts.append(str(partial))
    node = _parent(node)
  if not parts:
    raise ValueError('widget has no name anywhere in its parent chain')
  return '.'.join(reversed(parts))


def _inherited(widget: DictionaryObject, key: str) -> object | None:
  """Look up an inheritable field attribute, walking the parent chain."""
  node: DictionaryObject | None = widget
  while node is not None:
    if key in node:
      return node[key]
    node = _parent(node)
  return None


def _resolved(container: DictionaryObject, key: str) -> object | None:
  """Fetch a dictionary entry, or None if absent, resolving indirect references.

  A PDF entry can hold an indirect reference: a pointer to an object stored
  elsewhere in the file. pypdf follows the pointer when an entry is read as
  `container[key]`, but `container.get(key)` returns the pointer itself. This
  helper keeps `.get`'s None for a missing key and follows the pointer by hand.
  """
  value = container.get(key)
  return None if value is None else value.get_object()


def _parent(node: DictionaryObject) -> DictionaryObject | None:
  """Resolve the node's /Parent, if any, to its dictionary."""
  reference = node.get('/Parent')
  if reference is None:
    return None
  parent = reference.get_object()
  if not isinstance(parent, DictionaryObject):
    raise ValueError(f'field parent is not a dictionary: {parent!r}')
  return parent
