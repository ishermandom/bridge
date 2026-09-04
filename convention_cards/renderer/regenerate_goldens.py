# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

"""Regenerate the committed golden rasters for the filled-card tests.

Run after any change that legitimately alters rendered output — vocabulary
growth, font or palette changes — then review the refreshed images before
committing them. The golden test compares against these pixel-for-pixel, so they
reproduce only on a machine with the same fonts installed (spec.md #testing).

Usage, run from `convention_cards/`:
    python3 -m renderer.regenerate_goldens
"""

import json
import sys
from io import BytesIO, StringIO
from pathlib import Path

import pypdfium2
from PIL import Image

from renderer.fonts import register_entry_fonts
from renderer.render_card import DEFAULT_BASE_PDF_PATH, render_card
from renderer.vocabulary import UNRENDERED_KEYS

_RENDERER_DIR = Path(__file__).resolve().parent

FULL_EXPORT_PATH = _RENDERER_DIR / 'testdata' / 'full_export.json'
FULL_EXPORT_GOLDEN_PATH = (
  _RENDERER_DIR / 'testdata' / 'goldens' / 'full_export.png'
)

# 150 dpi: fine enough to catch a one-point drift, small enough to commit.
GOLDEN_SCALE = 150 / 72


def renderable_full_export() -> str:
  """The full-export fixture as card JSON, with unrendered keys removed."""
  document = json.loads(FULL_EXPORT_PATH.read_text(encoding='utf-8'))
  for setting in UNRENDERED_KEYS:
    document['settings'].get(setting.section, {}).pop(setting.key, None)
  return json.dumps(document)


def rasterize(pdf_bytes: bytes) -> Image.Image:
  """Render a one-page PDF at the golden scale, ignoring form widgets."""
  document = pypdfium2.PdfDocument(pdf_bytes)
  try:
    return document[0].render(scale=GOLDEN_SCALE, may_draw_forms=False).to_pil()
  finally:
    document.close()


def main() -> int:
  """Render the fixture card and overwrite the committed golden raster."""
  result = render_card(
    StringIO(renderable_full_export()),
    BytesIO(DEFAULT_BASE_PDF_PATH.read_bytes()),
    register_entry_fonts(),
  )
  FULL_EXPORT_GOLDEN_PATH.parent.mkdir(exist_ok=True)
  rasterize(result.pdf).save(FULL_EXPORT_GOLDEN_PATH)
  print(f'Written: {FULL_EXPORT_GOLDEN_PATH}')
  return 0


if __name__ == '__main__':
  sys.exit(main())
