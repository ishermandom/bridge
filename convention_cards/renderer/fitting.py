# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

"""Shrink-and-wrap sizing for entries.

An entry renders at its field's default size when it fits on one line. When it
doesn't, the fitter wraps the text at word boundaries — onto at most a few lines
— and takes the largest font size at which the wrapped lines fit the field's
rectangle. A small upward bleed into the gap between the card's ruled rows is
allowed, the way a person squeezes a second line above the rule. Text that
cannot fit even at the size floor raises an error.

Glyph widths scale linearly with font size, so each token is measured once at
size 1 and every candidate size reuses those unit widths.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

from renderer.markup import TextRun

# Measures one run's width in points at a given font size.
RunWidthMeasurer = Callable[[TextRun, float], float]

# Baseline-to-baseline distance between stacked lines, as a multiple of the font
# size — tight enough to cram lines into a blank, loose enough that ascenders
# and descenders don't collide.
_LINE_ADVANCE_RATIO = 1.12

# Binary-search precision for the width-limited font size, in points.
_SIZE_PRECISION = 0.01


@dataclass(frozen=True)
class FittedText:
  """A fitting solution: the font size and the wrapped lines of runs."""

  font_size: float
  lines: tuple[tuple[TextRun, ...], ...]


def fit_text(
  runs: Sequence[TextRun],
  measure: RunWidthMeasurer,
  available_width: float,
  available_height: float,
  default_size: float,
  size_floor: float,
  field_name: str,
) -> FittedText:
  """Fit the runs into a field, wrapping onto extra lines when needed.

  `available_height` already includes any bleed allowance. Line counts are tried
  in increasing order and the largest workable font size wins, so a single line
  at the default size stays the common case; at equal size fewer lines win,
  since a tie does not replace the earlier fit.

  Raises:
    ValueError: if the runs cannot fit the field even wrapped at `size_floor`.
  """
  tokens = _tokenize(runs, measure)

  best: FittedText | None = None
  line_count = 0
  while True:
    line_count += 1
    # At size s, the first line needs s of height and each line after it one
    # more line advance, so the available height caps the size.
    height_cap = available_height / (1 + (line_count - 1) * _LINE_ADVANCE_RATIO)
    largest_usable = min(default_size, height_cap)
    if largest_usable < size_floor:
      break

    size = _width_limited_size(
      tokens, available_width, line_count, largest_usable, size_floor
    )
    if size is not None and (best is None or size > best.font_size):
      best = FittedText(size, _wrap(tokens, available_width, size))

  if best is None:
    text = ''.join(run.text for run in runs)
    raise ValueError(
      f'field {field_name!r}: {text!r} does not fit even wrapped at the'
      f' {size_floor:g}pt floor'
    )
  return best


@dataclass(frozen=True)
class _Token:
  """One unbreakable word, or one space, with its width at size 1.

  A word may span several runs, mixing plain text and suit symbols (`3♣`).
  """

  runs: tuple[TextRun, ...]
  unit_width: float
  is_space: bool


def _tokenize(
  runs: Sequence[TextRun], measure: RunWidthMeasurer
) -> tuple[_Token, ...]:
  """Split runs at spaces into word and space tokens, measured at size 1.

  A line may break only at a space, so words are delimited by spaces alone, not
  by run boundaries: a suit symbol and the text touching it (`3!c`, `!c's`) form
  one word.
  """
  # Split the whole entry at every space, as `str.split(' ')` would split its
  # text: each item of `words` gathers the pieces between two neighboring
  # spaces, across run boundaries, and is empty where spaces sit side by side.
  # `replace` keeps each piece's suit.
  words: list[list[TextRun]] = [[]]
  for run in runs:
    for index, piece in enumerate(run.text.split(' ')):
      if index > 0:
        words.append([])
      if piece:
        words[-1].append(replace(run, text=piece))

  space = TextRun(' ')
  space_token = _Token((space,), measure(space, 1.0), is_space=True)
  tokens: list[_Token] = []
  for index, word in enumerate(words):
    if index > 0:
      tokens.append(space_token)
    if word:
      unit_width = sum(measure(run, 1.0) for run in word)
      tokens.append(_Token(tuple(word), unit_width, is_space=False))
  return tuple(tokens)


def _fits(
  tokens: Sequence[_Token],
  available_width: float,
  font_size: float,
  line_count: int,
) -> bool:
  """Does a greedy wrap at this size need at most `line_count` lines?

  A line must also genuinely fit the width: the wrapper forces an unbreakable
  word wider than the field onto a line of its own, and that line overflows, so
  the size doesn't fit.
  """
  unit_line_width = available_width / font_size
  lines = _wrap_unit_widths(tokens, unit_line_width)
  return len(lines) <= line_count and all(
    sum(token.unit_width for token in line) <= unit_line_width for line in lines
  )


def _width_limited_size(
  tokens: Sequence[_Token],
  available_width: float,
  line_count: int,
  largest_usable: float,
  size_floor: float,
) -> float | None:
  """The largest size in [floor, largest_usable] wrapping into the lines.

  Returns None when even the floor size doesn't fit. Shrinking only ever helps
  the fit, so binary search applies.
  """
  if _fits(tokens, available_width, largest_usable, line_count):
    return largest_usable
  if not _fits(tokens, available_width, size_floor, line_count):
    return None

  low, high = size_floor, largest_usable
  while high - low > _SIZE_PRECISION:
    middle = (low + high) / 2
    if _fits(tokens, available_width, middle, line_count):
      low = middle
    else:
      high = middle
  return low


def _wrap_unit_widths(
  tokens: Sequence[_Token], unit_line_width: float
) -> list[list[_Token]]:
  """Greedy word wrap in size-1 units; spaces at line breaks vanish."""
  lines: list[list[_Token]] = [[]]
  current_width = 0.0

  for token in tokens:
    if current_width + token.unit_width <= unit_line_width or not lines[-1]:
      lines[-1].append(token)
      current_width += token.unit_width
    elif token.is_space:
      # A break lands here: the space becomes the line ending.
      lines.append([])
      current_width = 0.0
    else:
      # Break before the word: drop the old line's now-trailing spaces, then
      # start a fresh line holding just the word.
      while lines[-1] and lines[-1][-1].is_space:
        lines[-1].pop()
      lines.append([token])
      current_width = token.unit_width
  return lines


def _wrap(
  tokens: Sequence[_Token], available_width: float, font_size: float
) -> tuple[tuple[TextRun, ...], ...]:
  """The final wrapped lines as run tuples, trimmed of edge spaces.

  Adjacent plain-text runs merge back into one run per stretch — one drawn
  string instead of a string per word — so runs split only where the font
  changes (at suit symbols).
  """
  lines = _wrap_unit_widths(tokens, available_width / font_size)
  merged_lines: list[tuple[TextRun, ...]] = []
  for line in lines:
    while line and line[0].is_space:
      line.pop(0)
    while line and line[-1].is_space:
      line.pop()

    merged: list[TextRun] = []
    for token in line:
      for run in token.runs:
        if merged and not merged[-1].suit and not run.suit:
          merged[-1] = TextRun(merged[-1].text + run.text)
        else:
          merged.append(run)
    merged_lines.append(tuple(merged))
  return tuple(merged_lines)


def line_advance(font_size: float) -> float:
  """Baseline-to-baseline distance between stacked lines, in points."""
  return font_size * _LINE_ADVANCE_RATIO
