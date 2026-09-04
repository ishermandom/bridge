# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

"""Tests for shrink-and-wrap fitting."""

import pytest

from renderer.fitting import FittedText, fit_text
from renderer.markup import Suit, TextRun


def _one_point_per_character(run: TextRun, font_size: float) -> float:
  """Fake measurer: each character is one point wide per point of size."""
  return len(run.text) * font_size


def _fit(
  text: str,
  available_width: float,
  available_height: float = 12.0,
  size_floor: float = 4.0,
) -> FittedText:
  """Fit one plain run at default size 10 with unit glyph metrics.

  With one point per character per point of size, the geometry is easy to reason
  about: a line of N characters at size s is N*s wide and s tall, and stacked
  baselines advance by 1.12*s.
  """
  return fit_text(
    (TextRun(text),),
    _one_point_per_character,
    available_width=available_width,
    available_height=available_height,
    default_size=10.0,
    size_floor=size_floor,
    field_name='F',
  )


# --- single-line fits ---


def test_fitting_text_keeps_the_default_size_on_one_line() -> None:
  # 5 characters at size 10 measure 50pt, within 60pt.
  fitted = _fit('abcde', available_width=60.0)

  assert fitted.font_size == 10.0
  assert fitted.lines == ((TextRun('abcde'),),)


def test_unbreakable_text_shrinks_on_one_line() -> None:
  # No spaces, so wrapping can't help: 10 characters into 50pt shrink to size 5
  # exactly (width-limited, above the floor).
  fitted = _fit('abcdefghij', available_width=50.0)

  assert fitted.font_size == pytest.approx(5.0, abs=0.02)
  assert len(fitted.lines) == 1


# --- wrapping ---


def test_wrappable_text_prefers_two_larger_lines_over_one_tiny_line() -> None:
  # 'aaaa bbbb' on one line (9 chars) into 25pt would need size ~2.8; wrapped as
  # 'aaaa' / 'bbbb' (4 chars a line), the size is capped by height: two lines at
  # size s span s*(1 + 1.12) <= 12, so s ~ 5.66.
  fitted = _fit('aaaa bbbb', available_width=25.0)

  assert fitted.font_size == pytest.approx(12.0 / 2.12, abs=0.02)
  assert fitted.lines == (
    (TextRun('aaaa'),),
    (TextRun('bbbb'),),
  )


def test_the_break_space_disappears_at_the_line_edge() -> None:
  fitted = _fit('aa bb cc', available_width=26.0)

  # 'aa bb' packs onto the first line; the space before 'cc' vanishes.
  assert fitted.lines == (
    (TextRun('aa bb'),),
    (TextRun('cc'),),
  )


def test_a_suit_symbol_never_separates_from_its_neighbors() -> None:
  # 'ab 3!c' parses into runs 'ab 3' + club symbol. At size 10 a line holds 4.5
  # characters, so breaking by width alone would split '3' from its club; the
  # only legal break is the space.
  fitted = fit_text(
    (TextRun('ab 3'), TextRun('♣', Suit.CLUBS)),
    _one_point_per_character,
    available_width=45.0,
    available_height=30.0,
    default_size=10.0,
    size_floor=4.0,
    field_name='F',
  )

  assert fitted.font_size == 10.0
  assert fitted.lines == (
    (TextRun('ab'),),
    (TextRun('3'), TextRun('♣', Suit.CLUBS)),
  )


# --- failure ---


def test_text_too_long_even_wrapped_is_rejected_naming_the_field() -> None:
  # Height allows two lines above the floor, but 100 characters need far more
  # than two lines at any size >= 4.
  with pytest.raises(ValueError, match="field 'F'"):
    _fit('word ' * 20, available_width=50.0)


def test_an_unbreakable_word_wider_than_the_field_is_rejected() -> None:
  with pytest.raises(ValueError, match='does not fit'):
    _fit('x' * 40, available_width=50.0)


def test_a_short_field_cannot_grow_extra_lines() -> None:
  # Height 4.5 fits one floor-size line but never two, so wrappable text that
  # needs two lines fails.
  with pytest.raises(ValueError, match='does not fit'):
    _fit('aaaa bbbb', available_width=25.0, available_height=4.5)
