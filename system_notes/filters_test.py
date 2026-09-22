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


# --- headings ---


def test_empty_link_is_filled_with_the_section_title() -> None:
  html = pandoc('# Openings {#openings}\n\nSee [](#openings).', 'headings.lua')
  assert '<a href="#openings" class="xref">Openings</a>' in html


def test_link_with_its_own_text_keeps_it_and_is_still_a_reference() -> None:
  html = pandoc('# Stayman {#stayman}\n\n[the relay](#stayman)', 'headings.lua')
  assert '<a href="#stayman" class="xref">the relay</a>' in html


@pytest.mark.parametrize('link', ['[](#missing)', '[see](#missing)'])
def test_unknown_target_fails_the_render(link: str) -> None:
  stderr = failing_pandoc(f'# A {{#a}}\n\n{link}', 'headings.lua')
  assert 'unknown cross-reference target: #missing' in stderr


@pytest.mark.parametrize(
  'document', ['## B {#b}\n\n# A {#a}', '# A {#a}\n\n### C {#c}']
)
def test_skipped_heading_level_fails_the_render(document: str) -> None:
  assert 'levels must not skip' in failing_pandoc(document, 'headings.lua')


def test_copied_titles_drop_links_and_footnotes() -> None:
  document = '# A [B](#b)^[note] {#a}\n\n# B {#b}\n\n[](#a)'
  html = pandoc(document, 'headings.lua')
  assert '<a href="#a" class="xref">A B</a>' in html
  assert html.count('class="footnote-ref"') == 1


# --- nowrap ---


# The first token's range is spelled with an en dash (U+2013), which nowrap.lua
# matches with a pattern of its own. The escape keeps it from reading as the
# plain hyphen in the token beside it.
@pytest.mark.parametrize('token', ['15\u201317', '5-3-3-2', 'P/C', 'NS/JNS'])
def test_notation_token_is_wrapped(token: str) -> None:
  assert f'<span class="nowrap">{token}</span>' in pandoc(token, 'nowrap.lua')


@pytest.mark.parametrize(
  'word', ['four-card', 'lead-directing', 'and/or', 'opener/responder', 'plain']
)
def test_prose_is_left_breakable(word: str) -> None:
  assert 'nowrap' not in pandoc(word, 'nowrap.lua')


# --- shorthand ---


@pytest.mark.parametrize(
  'token', ['M', 'OM', '2M', 'W2M', 'Q3M', '4cM', '4+OM']
)
def test_major_placeholder_is_bolded(token: str) -> None:
  assert f'{token[:-1]}<strong>M</strong>' in pandoc(token, 'shorthand.lua')


@pytest.mark.parametrize(
  'token', ['Major', 'IMP', 'm', 'Om', 'system', 'BAM', 'PROGRAM']
)
def test_other_tokens_are_untouched(token: str) -> None:
  assert '<strong>' not in pandoc(token, 'shorthand.lua')


def test_each_token_in_a_run_is_judged_alone() -> None:
  html = pandoc('Q3M/Q4M=cue', 'shorthand.lua')
  assert 'Q3<strong>M</strong>/Q4<strong>M</strong>=cue' in html


def test_plain_text_keeps_shorthand_as_typed() -> None:
  assert pandoc('OM and 4cM', 'shorthand.lua', to='plain').strip() == (
    'OM and 4cM'
  )


# --- sections ---

DOCUMENT = """\
# First {#first}

Intro.

## Nested {#nested}

::: {.note}
## Aside {#aside}

Body.
:::

# Second {#second}

More.
"""


def test_each_top_level_section_is_wrapped_whole() -> None:
  html = pandoc(DOCUMENT, 'sections.lua')
  assert html.count('<div class="sections">') == 1
  assert html.count('<div class="section">') == 2
  assert '<div class="section">\n<h1 id="first">First</h1>' in html
  # 3, not 4: pandoc writes the author's .note div, which opens with a heading,
  # as <section>, so only the three raw wrappers close with </div>.
  assert html.count('</div>') == 3


def test_nested_headings_and_author_divs_are_left_alone() -> None:
  html = pandoc(DOCUMENT, 'sections.lua')
  first_section = html.index('<div class="section">')
  second_heading = html.index('<h1 id="second">')
  assert first_section < html.index('<h2 id="nested">') < second_heading
  assert 'class="note"' in html


def test_plain_text_gets_no_wrappers() -> None:
  assert '<div' not in pandoc(DOCUMENT, 'sections.lua', to='plain')
