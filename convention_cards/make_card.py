# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

"""Merge a BridgeWinners convention card with a fold-over reminder strip.

Reads a BridgeWinners convention card PDF and a reminders text file, produces a
print-ready PDF suitable for printing on US Letter paper.

Layout of the output page (8.5" x 11"):
  - Top 2.5" (180pt): reminders strip — fold this behind the card and tuck
                        it into the holder so it is hidden away.
  - Bottom 8.5" (612pt): convention card scaled to 93%.

The right 0.5" (beyond the 8" cut guide) is trimmed off when inserting the card
into the holder.

Usage:
    python3 make_card.py CARD.pdf reminders.txt OUTPUT.pdf
"""

import argparse
import pathlib
from io import BytesIO

from pypdf import PdfReader, PdfWriter, Transformation
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

# ---------------------------------------------------------------------------
# Page geometry (PDF points; origin at bottom-left of page)
# ---------------------------------------------------------------------------

PAGE_W = 612  # 8.5"
PAGE_H = 792  # 11"
STRIP_H = 180  # top 2.5" reminders strip
FOLD_LINE_Y = PAGE_H - STRIP_H  # y-coordinate of fold/cut guide
CUT_GUIDE_X = 576  # 8" from left; vertical right-edge trim guide

# ---------------------------------------------------------------------------
# Scale and positioning of the convention card (in page-space coordinates)
#
# merge_transformed_page operates in page space, so TX/TY are straightforward:
#
# - Card top (original page_y = 792) → FOLD_LINE_Y = 612
# - Card left (original page_x = 0) → LEFT_MARGIN_PT = 0.2" = 14.4pt
#
# TY_page = FOLD_LINE_Y - SCALE * PAGE_H = 612 - 0.93*792 ≈ -124.6 TX_page and
# TY_page can be tuned independently; 1pt ≈ 1/72".
# ---------------------------------------------------------------------------

SCALE = 0.905
LEFT_MARGIN_PT = 14.4  # 0.2" — notes strip left margin
TX_page = 2  # card horizontal offset from left edge
TY_page = -85  # card vertical offset; tune if card is misaligned

# ---------------------------------------------------------------------------
# Reminders strip typography
# ---------------------------------------------------------------------------

ITEM_FONT = 'Helvetica'
ITEM_FONT_BOLD = 'Helvetica-Bold'
ITEM_FONT_SIZE = 6.5
SECTION_FONT_SIZE = 7.5  # section headers — larger than bullet items
SECTION_COLOR = 0.45  # gray level for section headers (0=black, 1=white)
SECTION_GAP = 4  # extra pt above a header (except first in column)
ITEM_LEADING = 9  # pt between baselines
MARGIN_TOP = 20  # pt from page top to first baseline
COL_GAP = 14  # pt between the two reminder columns
BULLET = '• '
BULLET_W = stringWidth(BULLET, ITEM_FONT, ITEM_FONT_SIZE)


# ---------------------------------------------------------------------------


def load_reminders(path: pathlib.Path) -> list[str]:
  """Read non-empty reminder lines from a plain-text file.

  Lines starting with '#' are section headers; others are bullet items. Leading
  '- ' is stripped from bullet lines. '**text**' markup is preserved for inline
  bold rendering.
  """
  lines = []
  for raw in path.read_text(encoding='utf-8').splitlines():
    stripped = raw.strip()
    if not stripped:
      continue
    if stripped.startswith('#'):
      lines.append(stripped)
    else:
      lines.append(stripped.lstrip('-').strip())
  return lines


def _is_section_header(line: str) -> bool:
  """True if line is a section header (starts with '#')."""
  return line.startswith('#')


# ---------------------------------------------------------------------------
# Inline bold markup: **text**
# ---------------------------------------------------------------------------


def _parse_markup(text: str) -> list[tuple[str, bool]]:
  """Split text on **...** spans into (segment, is_bold) pairs."""
  segments = []
  parts = text.split('**')
  for i, part in enumerate(parts):
    if part:
      segments.append((part, i % 2 == 1))
  return segments


def _draw_markup(
  c: canvas.Canvas,
  segments: list[tuple[str, bool]],
  x: float,
  y: float,
  font_size: float,
) -> float:
  """Draw mixed plain/bold segments starting at (x, y); return ending x."""
  for seg, is_bold in segments:
    font = ITEM_FONT_BOLD if is_bold else ITEM_FONT
    c.setFont(font, font_size)
    c.drawString(x, y, seg)
    x += stringWidth(seg, font, font_size)
  return x


def _render_column(
  c: canvas.Canvas,
  items: list[str],
  x: float,
  y_start: float,
  y_min: float,
  col_width: float,
) -> None:
  """Render one column of reminder items (with markup) onto the canvas."""
  avail = col_width - BULLET_W
  y = y_start

  for idx, item in enumerate(items):
    if y < y_min:
      break

    if _is_section_header(item):
      if idx > 0:  # gap above all but the first header in column
        y -= SECTION_GAP
      if y < y_min:
        break
      header_text = item.lstrip('#').strip()
      c.setFont(ITEM_FONT, SECTION_FONT_SIZE)
      c.setFillColorRGB(SECTION_COLOR, SECTION_COLOR, SECTION_COLOR)
      c.drawString(x, y, header_text)
      c.setFillColorRGB(0, 0, 0)
      y -= ITEM_LEADING
      continue

    # Word-wrap bullet items respecting **bold** markup and actual glyph widths.
    segments = _parse_markup(item)

    # Build a flat list of (word_or_space, is_bold) tokens.
    tokens = []
    for seg, is_bold in segments:
      words = seg.split(' ')
      for j, w in enumerate(words):
        if w:
          tokens.append((w, is_bold))
        if j < len(words) - 1:
          tokens.append((' ', is_bold))

    # Pack tokens into display lines greedily.
    wrapped = []
    cur: list[tuple[str, bool]] = []
    cur_w = 0.0

    for tok, is_bold in tokens:
      font = ITEM_FONT_BOLD if is_bold else ITEM_FONT
      tw = stringWidth(tok, font, ITEM_FONT_SIZE)
      if cur_w + tw > avail and cur and tok.strip():
        wrapped.append(cur)
        cur = [(tok, is_bold)]
        cur_w = tw
      else:
        cur.append((tok, is_bold))
        cur_w += tw
    if cur:
      wrapped.append(cur)

    for i, line_segs in enumerate(wrapped):
      if y < y_min:
        break
      while line_segs and line_segs[0][0] == ' ':
        line_segs.pop(0)
      while line_segs and line_segs[-1][0] == ' ':
        line_segs.pop()
      lx = x + BULLET_W
      if i == 0:
        c.setFont(ITEM_FONT, ITEM_FONT_SIZE)
        c.drawString(x, y, BULLET)
      _draw_markup(c, line_segs, lx, y, ITEM_FONT_SIZE)
      y -= ITEM_LEADING


def build_overlay(reminders: list[str]) -> BytesIO:
  """Render the reminders strip and guide lines as a PDF overlay."""
  buf = BytesIO()
  c = canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H))

  # Guide lines
  c.setStrokeColorRGB(0.45, 0.45, 0.45)
  c.setLineWidth(0.6)
  c.setDash(5, 4)
  c.line(0, FOLD_LINE_Y, PAGE_W, FOLD_LINE_Y)
  c.line(CUT_GUIDE_X, 0, CUT_GUIDE_X, PAGE_H)
  c.setDash()

  c.setFont(ITEM_FONT, 5.5)
  c.setFillColorRGB(0.55, 0.55, 0.55)
  c.drawRightString(CUT_GUIDE_X - 2, FOLD_LINE_Y + 3, 'v fold here')
  c.drawString(CUT_GUIDE_X + 2, 40, '< cut')

  # Two-column reminder layout
  c.setFillColorRGB(0, 0, 0)
  col_w = (CUT_GUIDE_X - LEFT_MARGIN_PT - COL_GAP) / 2
  col_x = [LEFT_MARGIN_PT, LEFT_MARGIN_PT + col_w + COL_GAP]
  y_start = PAGE_H - MARGIN_TOP - SECTION_FONT_SIZE
  y_min = FOLD_LINE_Y + 5

  # Split at a section boundary nearest the midpoint.
  mid = len(reminders) // 2
  split = next(
    (
      i
      for i in range(mid, min(mid + 4, len(reminders)))
      if _is_section_header(reminders[i])
    ),
    mid,
  )

  for items, cx in zip(
    [reminders[:split], reminders[split:]], col_x, strict=True
  ):
    _render_column(c, items, cx, y_start, y_min, col_w)

  c.save()
  buf.seek(0)
  return buf


def make_print_card(
  src: pathlib.Path,
  reminders_path: pathlib.Path,
  dst: pathlib.Path,
) -> None:
  """Scale the convention card, overlay the reminders strip, write output."""
  reminders = load_reminders(reminders_path)

  reader = PdfReader(src)
  card_page = reader.pages[0]

  writer = PdfWriter()
  out_page = writer.add_blank_page(PAGE_W, PAGE_H)

  # merge_transformed_page works in page space, avoiding the card PDF's internal
  # y-flipping CTM.
  ctm = Transformation(ctm=(SCALE, 0, 0, SCALE, TX_page, TY_page))
  out_page.merge_transformed_page(card_page, ctm)

  overlay_page = PdfReader(build_overlay(reminders)).pages[0]
  out_page.merge_page(overlay_page)

  writer.write(dst)
  print(f'Written: {dst}')


def _parse_args() -> argparse.Namespace:
  """Parse the card/reminders/output file paths from the command line."""
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('card', type=pathlib.Path, help='BridgeWinners card PDF')
  parser.add_argument(
    'reminders', type=pathlib.Path, help='Reminders text file'
  )
  parser.add_argument('output', type=pathlib.Path, help='Print-ready PDF path')
  return parser.parse_args()


if __name__ == '__main__':
  args = _parse_args()
  make_print_card(src=args.card, reminders_path=args.reminders, dst=args.output)
