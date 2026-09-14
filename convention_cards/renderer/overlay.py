# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

"""Draws entered content onto a transparent, card-sized overlay page.

The overlay carries only the user's entries — text in the entry palette, X marks
across checkboxes, rings around lead-chart cards — and is later merged on top of
the untouched base card page.

Every length and font size here is in PDF points (1/72 inch), and positions use
the card page's own coordinates (see `geometry.CardField`).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from io import BytesIO

from reportlab.lib.colors import Color, HexColor
from reportlab.pdfgen.canvas import Canvas

from renderer.fitting import FittedText, fit_text, line_advance
from renderer.fonts import SUIT_SIZE_FACTOR, EntryFonts
from renderer.geometry import CARD_HEIGHT, CARD_WIDTH, CardField, FieldKind
from renderer.lead_charts import CharBox
from renderer.markup import Suit, TextRun, parse_suit_markup
from renderer.rule_positions import RULE_TOPS
from renderer.vocabulary import (
  CheckPlacement,
  CirclePlacement,
  Placement,
  TextPlacement,
)

# Below this size the printed card stops being legible at the table, so text
# that cannot fit at or above it is a hard error rather than shrinking further.
DEFAULT_SIZE_FLOOR = 7.0

# Breathing room between an entry and its field's left/right edges.
_TEXT_INSET = 1.0

# Extra height, above the field's rectangle, that a wrapped entry may use.
# Entries grow upward: the bottom line stays on the field's rule and each extra
# line stacks above it. So the fitter lets the lines span the field's height
# plus this much, rising into the space between the field and the row printed
# above — the way a person squeezes a second line in above the rule. Stacked
# rows' form fields commonly sit 2-4pt apart.
_VERTICAL_BLEED = 2.5

# Gap between an entry's baseline — the line its letters sit on, with descenders
# dipping below — and the top of the rule beneath it (see `rule_positions`).
# Sitting directly on the rule reads as merged with it; this sliver keeps
# entries scannable while still writing on the line the way a hand fills a
# blank.
_BASELINE_CLEARANCE = 1.0


@dataclass(frozen=True)
class FieldExpansion:
  """Unprinted space around a form field that its entry may spill into."""

  extra_width: float = 0.0
  extra_height: float = 0.0


# The form's rectangles end where their printed blanks end, but a few blanks
# border genuinely empty artwork that entries may spill into. Amounts are
# measured from the blank card, stopping ~2pt short of the nearest printed ink:
#
# - The aligned "Other" blanks on the four 1NT response rows run right into the
#   blank gutter before the second 1NT panel (fields end at x=425.3; the panel's
#   printed labels start at x=445.2).
# - `LS.t.8` (honor-lead "Varies") wraps upward into the open band right of the
#   printed "Honor Leads:" label (the field above starts 11.9pt up).
# - `1H1S.t.16` (the majors "Other" blank) ends at x=420.5; the row's next
#   printed ink, the after-overcall raise labels, starts at x=440.1.
FIELD_EXPANSIONS: Mapping[str, FieldExpansion] = {
  '1NT.t.11': FieldExpansion(extra_width=18.0),
  '1NT.t.14': FieldExpansion(extra_width=18.0),
  '1NT.t.17': FieldExpansion(extra_width=18.0),
  '1NT.t.20': FieldExpansion(extra_width=18.0),
  '1H1S.t.16': FieldExpansion(extra_width=17.6),
  'LS.t.8': FieldExpansion(extra_height=8.0),
}

# Blanks in the page's right column stop ~4pt short of the card's outer border
# (left edge x=575.25, measured from the blank artwork) with nothing printed in
# between, so entries there may run toward the border, keeping just under a
# point of daylight before it. Membership is geometric rather than a per-field
# list: right-column text fields all end past x=570.5, and no other text field
# ends within 5pt of that.
_RIGHT_COLUMN_MIN_X = 570.0
_RIGHT_COLUMN_TEXT_LIMIT_X = 574.3


@dataclass(frozen=True)
class RuleExtension:
  """How to continue a printed underline when an entry overflows past it."""

  printed_end_x: float
  extended_end_x: float
  color: Color


# The printed underlines' thickness: the underscore glyphs these rows print are
# 0.38pt from top to bottom, read from their outlines.
_RULE_BAR_THICKNESS = 0.38

# Extensions start under the printed bar's last fraction of a point, so
# antialiasing can never open a seam between old ink and new.
_RULE_SEAM_OVERLAP = 0.3

_1NT_RULE_RED = HexColor(0xFF0000)

# The card prints the `_RULE_EXTENSIONS` blanks' underlines as rows of
# underscore glyphs, so an entry spilling into a `FIELD_EXPANSIONS` gutter runs
# past the underline's end and looks unanchored. When that happens, the
# underline is continued with a bar matching the printed one. Each bar hangs
# from its field's measured rule top (`rule_positions`), and printed right ends
# are read from the underscore glyphs' outlines; each panel keeps its own red —
# the 1NT rows print pure red, the majors row the darker ED1C24. Extension
# targets: the four 1NT rows share one right edge just short of the second 1NT
# panel's labels (x=445.2), so the aligned column stays aligned; the majors row
# stops 2pt short of the after-overcall raise labels (x=440.1).
#
# Right-column entries can also overhang their rules (toward
# `_RIGHT_COLUMN_TEXT_LIMIT_X`), but only by ~4pt — about half a character — too
# little to warrant continuing the line there.
_RULE_EXTENSIONS: Mapping[str, RuleExtension] = {
  '1NT.t.11': RuleExtension(
    printed_end_x=424.78,
    extended_end_x=443.2,
    color=_1NT_RULE_RED,
  ),
  '1NT.t.14': RuleExtension(
    printed_end_x=424.83,
    extended_end_x=443.2,
    color=_1NT_RULE_RED,
  ),
  '1NT.t.17': RuleExtension(
    printed_end_x=424.79,
    extended_end_x=443.2,
    color=_1NT_RULE_RED,
  ),
  '1NT.t.20': RuleExtension(
    printed_end_x=424.78,
    extended_end_x=443.2,
    color=_1NT_RULE_RED,
  ),
  '1H1S.t.16': RuleExtension(
    printed_end_x=420.30,
    extended_end_x=438.1,
    color=HexColor(0xED1C24),
  ),
}

# Families whose rules extend together: when any member's entry overflows its
# printed end, every member's underline — blank rows included — extends to the
# family's shared right edge. A column of aligned blanks reads better with one
# right edge than with a mix of printed and extended ends.
_RULE_EXTENSION_FAMILIES: Sequence[Sequence[str]] = (
  ('1NT.t.11', '1NT.t.14', '1NT.t.17', '1NT.t.20'),
  ('1H1S.t.16',),
)

# How far an X mark's strokes stay inside the checkbox rectangle.
_CHECK_INSET_RATIO = 0.15
_CHECK_STROKE_WIDTH = 0.8

# How far a lead ring's stroke sits outside its character's box. The ring is a
# rounded rectangle rather than an ellipse: with the ~2pt of room between
# neighboring chart cards, an ellipse tight enough to fit crosses its own
# glyph's corners, while straight sides clear them at modest padding. The
# vertical rows have more room than the horizontal gaps, so padding is
# asymmetric.
_RING_X_PADDING = 1.2
_RING_Y_PADDING = 1.5

# The chart prints its characters at uneven distances, so full padding would
# leave some rings crowding a neighbor. The ring backs off symmetrically — both
# sides shrink to whatever the tighter side allows, keeping
# `_RING_NEIGHBOR_CLEARANCE` of daylight to a neighboring character but never
# less than `_RING_MIN_X_PADDING` of glyph padding — so the glyph always sits
# exactly centered in its ring. Centering the glyph in the ring outranks evening
# out the daylight around it: uneven gaps are the artwork's own spacing, whereas
# a slid ring reads as missing its target.
_RING_MIN_X_PADDING = 0.8
_RING_NEIGHBOR_CLEARANCE = 0.9

# Many ringed characters are x's, the lead chart's stand-in for any low card,
# and a square ring around an x would look like one of the card's checkboxes
# marked with an X. Draw corners that are round enough to read as a hand-drawn
# oval instead.
_RING_CORNER_RADIUS = 2.6
_RING_STROKE_WIDTH = 0.6


@dataclass(frozen=True)
class Palette:
  """Colors for entries and the four suit symbols."""

  entry: Color
  spades: Color
  hearts: Color
  diamonds: Color
  clubs: Color

  def for_run(self, run: TextRun) -> Color:
    """Pick a run's color: suit runs by suit, plain text in entry color."""
    match run.suit:
      case None:
        return self.entry
      case Suit.SPADES:
        return self.spades
      case Suit.HEARTS:
        return self.hearts
      case Suit.DIAMONDS:
        return self.diamonds
      case Suit.CLUBS:
        return self.clubs


# Four-color suits in the "gentle" palette (spec.md #appearance): near-equal
# perceived lightness, so no suit fades ahead of the others in a black-and-white
# print. Hearts and clubs keep their longtime hues, spades brighten to the
# hearts' level, and diamonds darken to a printable amber. Derivation and the
# explored alternatives: `palette_specimen.py`. Entries default to black:
# colored text halftones to a lighter gray and costs contrast.
#
# A hand-built HTML card in bridge-private's `convention_cards/` directory
# mirrors these suit colors; when changing the palette, update that card's
# `suit-symbol` rules in the same breath.
DEFAULT_PALETTE = Palette(
  entry=HexColor(0x000000),
  spades=HexColor(0x1F4AFF),
  hearts=HexColor(0xC6102D),
  diamonds=HexColor(0xBA6B16),
  clubs=HexColor(0x00843D),
)

# The open red suits' outlines are thickened with a fill-plus-stroke, as a
# fraction of the symbol's drawing size. The diamond's ratio runs 0.01 higher:
# its simpler shape holds weight better, and its shorter perimeter deposits less
# ink, so the boost evens the two suits' visual weight.
_SUIT_STROKE_RATIOS: Mapping[Suit, float] = {
  Suit.HEARTS: 0.08,
  Suit.DIAMONDS: 0.09,
}


@dataclass(frozen=True)
class ResizedField:
  """One field whose entry had to shrink below the field's default size."""

  field_name: str
  default_size: float
  fitted_size: float
  line_count: int
  text: str


@dataclass(frozen=True)
class OverlayResult:
  """The overlay page, plus every entry that had to shrink to fit its field."""

  pdf: bytes
  resized: tuple[ResizedField, ...]


def build_overlay(
  placements: Sequence[Placement],
  fields: Mapping[str, CardField],
  fonts: EntryFonts,
  palette: Palette,
  size_floor: float,
) -> OverlayResult:
  """Draw every placement onto a fresh card-sized overlay page.

  Raises:
    ValueError: if `fields` lacks a field the placements name or holds it as the
      wrong kind, or if an entry cannot fit its field.
  """
  buffer = BytesIO()
  canvas = Canvas(buffer, pagesize=(CARD_WIDTH, CARD_HEIGHT))
  resized: list[ResizedField] = []

  _draw_rule_extensions(canvas, placements, fields, fonts, size_floor)

  for placement in placements:
    match placement:
      case TextPlacement():
        field = _field_for(fields, placement.target.field_name)
        _draw_text(
          canvas, field, placement.text, fonts, palette, size_floor, resized
        )
      case CheckPlacement():
        field = _field_for(fields, placement.target.field_name)
        _draw_check_mark(canvas, field, palette)
      case CirclePlacement():
        _draw_lead_ring(
          canvas, placement.target.boxes, placement.card_position, palette
        )

  # End the page explicitly: `save` emits a page only if something was drawn on
  # it, and a card with no entries still needs an overlay page to merge.
  canvas.showPage()
  canvas.save()
  return OverlayResult(pdf=buffer.getvalue(), resized=tuple(resized))


def _field_for(fields: Mapping[str, CardField], name: str) -> CardField:
  """Look up a vocabulary-named form field, failing loudly if absent."""
  field = fields.get(name)
  if field is None:
    raise ValueError(
      f'vocabulary names field {name!r}, which the base PDF does not define'
    )
  return field


def _draw_lead_ring(
  canvas: Canvas,
  boxes: Sequence[CharBox],
  card_position: int,
  palette: Palette,
) -> None:
  """Ring one printed lead-chart card, centered on it exactly.

  `card_position` is 1-based from the left of the printed holding. Both sides
  share one padding — the tighter side's allowance, per the `_RING_*` constants
  — so the glyph sits centered in its ring.
  """
  left, bottom, right, top = boxes[card_position - 1]
  previous = boxes[card_position - 2] if card_position >= 2 else None
  following = boxes[card_position] if card_position < len(boxes) else None

  padding = min(
    _ring_side_padding(left - previous[2] if previous else None),
    _ring_side_padding(following[0] - right if following else None),
  )

  canvas.setStrokeColor(palette.entry)
  canvas.setLineWidth(_RING_STROKE_WIDTH)
  canvas.roundRect(
    left - padding,
    bottom - _RING_Y_PADDING,
    (right - left) + 2 * padding,
    (top - bottom) + 2 * _RING_Y_PADDING,
    _RING_CORNER_RADIUS,
  )


def _ring_side_padding(neighbor_gap: float | None) -> float:
  """One side's horizontal padding, backing off from a close neighbor."""
  if neighbor_gap is None:
    return _RING_X_PADDING
  cleared = neighbor_gap - _RING_NEIGHBOR_CLEARANCE
  return max(_RING_MIN_X_PADDING, min(_RING_X_PADDING, cleared))


def _right_column_allowance(field: CardField) -> float:
  """Extra entry width for a blank ending at the page's right column edge.

  The fitting budget already spends `_TEXT_INSET` inside the field's right edge,
  so the allowance runs from that inset edge out to the text limit.
  """
  field_right = field.left + field.width
  if field_right < _RIGHT_COLUMN_MIN_X:
    return 0.0
  return _RIGHT_COLUMN_TEXT_LIMIT_X - (field_right - _TEXT_INSET)


def _fit_field_text(
  field: CardField, value: str, fonts: EntryFonts, size_floor: float
) -> FittedText:
  """Fit one entry into its field's budget, expansions and all."""
  if field.kind is not FieldKind.TEXT or field.default_font_size is None:
    raise ValueError(
      f'field {field.name!r} is not a text field but received text'
    )
  expansion = FIELD_EXPANSIONS.get(field.name, FieldExpansion())
  # Inset from both side edges, then widened by any unprinted room to the right.
  available_width = (
    field.width
    - 2 * _TEXT_INSET
    + expansion.extra_width
    + _right_column_allowance(field)
  )
  # The field's own height, plus room above it for wrapped lines.
  available_height = field.height + _VERTICAL_BLEED + expansion.extra_height
  return fit_text(
    parse_suit_markup(value),
    fonts.run_width,
    available_width=available_width,
    available_height=available_height,
    default_size=field.default_font_size,
    size_floor=size_floor,
    field_name=field.name,
  )


def _overflows_printed_rule(
  field: CardField, value: str, fonts: EntryFonts, size_floor: float
) -> bool:
  """Whether an entry's ink runs past its field's printed underline end."""
  extension = _RULE_EXTENSIONS[field.name]
  fitted = _fit_field_text(field, value, fonts, size_floor)
  widest_line = max(
    sum(fonts.run_width(run, fitted.font_size) for run in line)
    for line in fitted.lines
  )
  return field.left + _TEXT_INSET + widest_line > extension.printed_end_x


def _draw_rule_extensions(
  canvas: Canvas,
  placements: Sequence[Placement],
  fields: Mapping[str, CardField],
  fonts: EntryFonts,
  size_floor: float,
) -> None:
  """Continue printed underlines beneath entries that overflow them.

  Extension is per family: when any member's entry overflows its printed end,
  every member's underline — blank rows included — extends to the family's
  shared right edge, keeping the aligned column on a single edge. Drawn before
  all entries so descenders cross the bars the way they cross the printed rules;
  fitting an entry twice (here and at draw time) is cheap, the fitter being a
  pure function.
  """
  texts = {
    placement.target.field_name: placement.text
    for placement in placements
    if isinstance(placement, TextPlacement)
  }
  for family in _RULE_EXTENSION_FAMILIES:
    if not any(
      name in texts
      and _overflows_printed_rule(
        _field_for(fields, name), texts[name], fonts, size_floor
      )
      for name in family
    ):
      continue
    for name in family:
      extension = _RULE_EXTENSIONS[name]
      start = extension.printed_end_x - _RULE_SEAM_OVERLAP
      canvas.setFillColor(extension.color)
      canvas.rect(
        start,
        RULE_TOPS[name] - _RULE_BAR_THICKNESS,
        extension.extended_end_x - start,
        _RULE_BAR_THICKNESS,
        stroke=0,
        fill=1,
      )


def _draw_text(
  canvas: Canvas,
  field: CardField,
  value: str,
  fonts: EntryFonts,
  palette: Palette,
  size_floor: float,
  resized: list[ResizedField],
) -> None:
  """Draw one text entry into its field, shrinking and wrapping to fit."""
  fitted = _fit_field_text(field, value, fonts, size_floor)
  assert field.default_font_size is not None  # _fit_field_text validated
  if fitted.font_size < field.default_font_size:
    resized.append(
      ResizedField(
        field.name,
        field.default_font_size,
        fitted.font_size,
        len(fitted.lines),
        value,
      )
    )

  # The bottom line's baseline sits just above the field's printed rule. Any
  # further lines stack upward from there, bleeding into the inter-row gap.
  bottom_baseline = RULE_TOPS[field.name] + _BASELINE_CLEARANCE

  advance = line_advance(fitted.font_size)
  for line_index, line in enumerate(fitted.lines):
    baseline = bottom_baseline + (len(fitted.lines) - 1 - line_index) * advance
    x = field.left + _TEXT_INSET
    for run in line:
      if run.suit:
        _draw_suit_symbol(
          canvas, x, baseline, run, fonts, fitted.font_size, palette
        )
      else:
        canvas.setFont(fonts.text_font, fitted.font_size)
        canvas.setFillColor(palette.for_run(run))
        canvas.drawString(x, baseline, run.text)
      x += fonts.run_width(run, fitted.font_size)


def _draw_suit_symbol(
  canvas: Canvas,
  x: float,
  baseline: float,
  run: TextRun,
  fonts: EntryFonts,
  font_size: float,
  palette: Palette,
) -> None:
  """Draw one suit symbol, enlarged to cap height, open forms boosted.

  The symbol draws at `font_size * SUIT_SIZE_FACTOR`, stretched horizontally to
  fill the shared suit advance (`EntryFonts.suit_stretches`) so every suit's ink
  is equally wide; `EntryFonts.run_width` reports that same slot, so layout
  already accounts for it.
  """
  assert run.suit is not None  # only suit runs reach this drawing path
  color = palette.for_run(run)
  symbol_size = font_size * SUIT_SIZE_FACTOR
  stroke_ratio = _SUIT_STROKE_RATIOS.get(run.suit, 0.0)
  stretch = fonts.suit_stretches[run.suit]

  canvas.setFillColor(color)
  if stroke_ratio:
    canvas.setStrokeColor(color)
    canvas.setLineWidth(stroke_ratio * symbol_size)
    canvas.setLineJoin(1)

  text = canvas.beginText(x, baseline)
  text.setFont(fonts.symbol_font, symbol_size)
  # reportlab's `setHorizScale` emits its argument verbatim as the PDF `Tz`
  # operand, which is an absolute percent — pass 114 for a 14% stretch (ignore
  # the method's internal `100 +` bookkeeping).
  text.setHorizScale(100 * stretch)
  if stroke_ratio:
    text.setTextRenderMode(2)
  text.textOut(run.text)
  # Reset inside the text object: both settings are text state that outlives the
  # object, and on a fresh object reportlab skips emitting a value that matches
  # the default — so without the in-object reset they would leak into later
  # text.
  if stroke_ratio:
    text.setTextRenderMode(0)
  text.setHorizScale(100)
  canvas.drawText(text)


def _draw_check_mark(
  canvas: Canvas,
  field: CardField,
  palette: Palette,
) -> None:
  """Draw an X spanning the checkbox, slightly inset from its corners."""
  if field.kind is not FieldKind.CHECKBOX:
    raise ValueError(
      f'field {field.name!r} is not a checkbox but received a check mark'
    )

  inset = _CHECK_INSET_RATIO * min(field.width, field.height)
  left = field.left + inset
  right = field.left + field.width - inset
  bottom = field.bottom + inset
  top = field.bottom + field.height - inset

  canvas.setStrokeColor(palette.entry)
  canvas.setLineWidth(_CHECK_STROKE_WIDTH)
  canvas.line(left, bottom, right, top)
  canvas.line(left, top, right, bottom)
