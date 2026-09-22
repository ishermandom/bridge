# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Each Lua filter on small inputs, one filter at a time, through pandoc."""

import subprocess
from pathlib import Path

import pytest

FILTERS = Path(__file__).resolve().parent / 'filters'


def pandoc(markdown: str, filter_name: str, to: str = 'html') -> str:
  """Run pandoc on `markdown` with one filter and return the output."""
  return subprocess.run(
    [
      'pandoc',
      '--wrap=none',
      '--lua-filter',
      str(FILTERS / filter_name),
      '--to',
      to,
    ],
    input=markdown,
    capture_output=True,
    text=True,
    encoding='utf-8',
    check=True,
  ).stdout


def failing_pandoc(markdown: str, filter_name: str) -> str:
  """Run pandoc on `markdown` expecting the filter to fail; return stderr."""
  completed = subprocess.run(
    ['pandoc', '--lua-filter', str(FILTERS / filter_name)],
    input=markdown,
    capture_output=True,
    text=True,
    encoding='utf-8',
  )
  assert completed.returncode != 0, 'the filter should have failed'
  return completed.stderr


# --- bids ---


@pytest.mark.parametrize(
  ('bid', 'symbol', 'suit_class'),
  [
    ('4S', '♠', 'spade'),
    ('2H', '♥', 'heart'),
    ('3D', '♦', 'diamond'),
    ('1C', '♣', 'club'),
  ],
)
def test_plain_bid_gets_its_suit_symbol(
  bid: str, symbol: str, suit_class: str
) -> None:
  html = pandoc(f'Bid {bid}.', 'bids.lua')
  assert (
    f'<span class="bid">{bid[0]}<span class="strain suit {suit_class}">'
    f'{symbol}</span></span>.'
  ) in html


def test_notrump_bid_keeps_its_letters() -> None:
  html = pandoc('2NT', 'bids.lua')
  assert (
    '<span class="bid">2<span class="strain notrump">NT</span></span>' in html
  )


@pytest.mark.parametrize(
  'token', ['15S', '8S', '8NT', '4Sx', '1ST', 'S4', '5S4H']
)
def test_non_bids_are_untouched(token: str) -> None:
  assert '<span' not in pandoc(token, 'bids.lua')


@pytest.mark.parametrize('bid', ['2N', '2n', '2nt', '2Nt', '1N-2S', '4N+1'])
def test_wrong_notrump_spelling_fails_the_render(bid: str) -> None:
  stderr = failing_pandoc(f'then {bid}: to play', 'bids.lua')
  assert 'notrump must always be spelled NT' in stderr


# Algebra and a URL path both put a lowercase `n` after a digit with a joining
# `-` or `+` beside it, which is what excuses the spelling; `2nd` is turned away
# by the word boundary instead.
@pytest.mark.parametrize(
  'text',
  ['rule of 2n+1', 'notes/weak-2n-openings', '2nd seat', '1+2n boards'],
)
def test_lowercase_n_in_non_notation_text_is_left_alone(text: str) -> None:
  assert '<span' not in pandoc(text, 'bids.lua')


def test_an_en_dash_separates_two_bids() -> None:
  # An en dash joins the calls of a written auction, and is the character whose
  # lead byte drove bids.lua to spell its patterns out in ASCII ranges.
  en_dash = '\u2013'
  html = pandoc(f'1NT{en_dash}2S', 'bids.lua')
  assert html.count('<span class="strain') == 2
  assert f'NT</span></span>{en_dash}<span class="bid">2<span' in html


@pytest.mark.parametrize('shorthand', ['!S', '!s'])
def test_explicit_shorthand_marks_a_suit_outside_a_bid(shorthand: str) -> None:
  html = pandoc(f'a {shorthand} lead', 'bids.lua')
  assert 'a <span class="strain suit spade">♠</span> lead' in html


def test_explicit_shorthand_needs_a_word_boundary() -> None:
  assert '<span' not in pandoc('Really!Stayman', 'bids.lua')


def test_plain_text_keeps_bids_as_typed() -> None:
  assert pandoc('2H or 2NT: to play', 'bids.lua', to='plain').strip() == (
    '2H or 2NT: to play'
  )


def test_plain_text_reduces_explicit_shorthand_to_its_letter() -> None:
  assert pandoc('a !h lead, then !S', 'bids.lua', to='plain').strip() == (
    'a H lead, then S'
  )


# --- metadata ---


@pytest.mark.parametrize(
  'front_matter', ['date: 2026-08-26', 'title: ""', "title: ''"]
)
def test_missing_or_empty_title_fails_the_render(front_matter: str) -> None:
  stderr = failing_pandoc(f'---\n{front_matter}\n---\n\nBody.', 'metadata.lua')
  assert 'non-empty `title`' in stderr
