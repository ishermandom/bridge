# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Each Lua filter on small inputs, one filter at a time, through pandoc.

The `pandoc` fixture dedents each input's Markdown first, so a test can write a
multi-line input indented in a triple-quoted string.
"""

import json
import subprocess
import textwrap
from collections.abc import Iterator
from pathlib import Path

import pytest

FILTERS = Path(__file__).resolve().parent / 'filters'
RUNNER_SCRIPT = Path(__file__).resolve().parent / 'filters_test_runner.lua'


class Pandoc:
  """One `pandoc lua` process, applying a single filter per request.

  Launching pandoc takes ~26ms, many times what any of these filters takes, so
  the module's tests share one process rather than each launching its own.
  `filters_test_runner.lua` is the other end, and its header describes the
  exchange.

  The filters run through pandoc's Lua API rather than `--lua-filter`, with the
  same output; `render_notes_test.py` runs them the command line's way, over the
  whole sample document.
  """

  def __init__(self) -> None:
    self._process = subprocess.Popen(
      ['pandoc', 'lua', str(RUNNER_SCRIPT)],
      stdin=subprocess.PIPE,
      stdout=subprocess.PIPE,
      text=True,
      encoding='utf-8',
    )
    # Popen types both streams as optional; with PIPE, both are always there.
    assert self._process.stdin and self._process.stdout
    self._requests = self._process.stdin
    self._replies = self._process.stdout

  def output(self, markdown: str, filter_name: str, to: str = 'html') -> str:
    """Run one filter over `markdown` and return pandoc's output."""
    match self._request(markdown, filter_name, to):
      case {'output': str(output)}:
        return output
      case reply:
        pytest.fail(f'{filter_name} failed on {markdown!r}: {reply}')

  def error(self, markdown: str, filter_name: str) -> str:
    """Run one filter over `markdown`, expecting failure; return the error."""
    match self._request(markdown, filter_name, 'html'):
      case {'error': str(error)}:
        return error
      case reply:
        pytest.fail(
          f'{filter_name} should have failed on {markdown!r}: {reply}'
        )

  def close(self) -> None:
    """End the process; closing its input ends its request loop."""
    self._requests.close()
    self._process.wait(timeout=5)

  def _request(self, markdown: str, filter_name: str, to: str) -> object:
    """Send one request and return the decoded reply."""
    request = {
      'filter': str(FILTERS / filter_name),
      'format': to,
      'markdown': textwrap.dedent(markdown),
    }
    self._requests.write(json.dumps(request) + '\n')
    self._requests.flush()
    reply = self._replies.readline()
    if not reply:
      pytest.fail(
        f'pandoc lua exited (status {self._process.poll()}) instead of '
        f'answering {request}'
      )
    decoded: object = json.loads(reply)
    return decoded


@pytest.fixture(scope='module')
def pandoc() -> Iterator[Pandoc]:
  """The module's one pandoc process, ended after its last test."""
  process = Pandoc()
  yield process
  process.close()


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
  pandoc: Pandoc, bid: str, symbol: str, suit_class: str
) -> None:
  html = pandoc.output(f'Bid {bid}.', 'bids.lua')
  assert (
    f'<span class="bid">{bid[0]}<span class="strain suit {suit_class}">'
    f'{symbol}</span></span>.'
  ) in html


def test_notrump_bid_keeps_its_letters(pandoc: Pandoc) -> None:
  html = pandoc.output('2NT', 'bids.lua')
  assert (
    '<span class="bid">2<span class="strain notrump">NT</span></span>' in html
  )


@pytest.mark.parametrize(
  'token', ['15S', '8S', '8NT', '4Sx', '1ST', 'S4', '5S4H']
)
def test_non_bids_are_untouched(pandoc: Pandoc, token: str) -> None:
  assert '<span' not in pandoc.output(token, 'bids.lua')


@pytest.mark.parametrize('bid', ['2N', '2n', '2nt', '2Nt', '1N-2S', '4N+1'])
def test_wrong_notrump_spelling_fails_the_render(
  pandoc: Pandoc, bid: str
) -> None:
  error = pandoc.error(f'then {bid}: to play', 'bids.lua')
  assert 'notrump must always be spelled NT' in error


# Algebra and a URL path both put a lowercase `n` after a digit with a joining
# `-` or `+` beside it, which is what excuses the spelling; `2nd` is turned away
# by the word boundary instead.
@pytest.mark.parametrize(
  'text',
  ['rule of 2n+1', 'notes/weak-2n-openings', '2nd seat', '1+2n boards'],
)
def test_lowercase_n_in_non_notation_text_is_left_alone(
  pandoc: Pandoc, text: str
) -> None:
  assert '<span' not in pandoc.output(text, 'bids.lua')


def test_an_en_dash_separates_two_bids(pandoc: Pandoc) -> None:
  # An en dash joins the calls of a written auction, and is the character whose
  # lead byte drove bids.lua to spell its patterns out in ASCII ranges.
  en_dash = '\N{EN DASH}'
  html = pandoc.output(f'1NT{en_dash}2S', 'bids.lua')
  assert html.count('<span class="strain') == 2
  assert f'NT</span></span>{en_dash}<span class="bid">2<span' in html


@pytest.mark.parametrize('shorthand', ['!S', '!s'])
def test_explicit_shorthand_marks_a_suit_outside_a_bid(
  pandoc: Pandoc, shorthand: str
) -> None:
  html = pandoc.output(f'a {shorthand} lead', 'bids.lua')
  assert 'a <span class="strain suit spade">♠</span> lead' in html


def test_explicit_shorthand_needs_a_word_boundary(pandoc: Pandoc) -> None:
  assert '<span' not in pandoc.output('Really!Stayman', 'bids.lua')


def test_plain_text_keeps_bids_as_typed(pandoc: Pandoc) -> None:
  text = pandoc.output('2H or 2NT: to play', 'bids.lua', to='plain')
  assert text.strip() == '2H or 2NT: to play'


def test_plain_text_reduces_explicit_shorthand_to_its_letter(
  pandoc: Pandoc,
) -> None:
  text = pandoc.output('a !h lead, then !S', 'bids.lua', to='plain')
  assert text.strip() == 'a H lead, then S'


# --- metadata ---


@pytest.mark.parametrize(
  'front_matter', ['date: 2026-08-26', 'title: ""', "title: ''"]
)
def test_missing_or_empty_title_fails_the_render(
  pandoc: Pandoc, front_matter: str
) -> None:
  error = pandoc.error(f'---\n{front_matter}\n---\n\nBody.', 'metadata.lua')
  assert 'non-empty `title`' in error


# --- headings ---


def test_empty_link_is_filled_with_the_section_title(pandoc: Pandoc) -> None:
  html = pandoc.output(
    '# Openings {#openings}\n\nSee [](#openings).', 'headings.lua'
  )
  assert '<a href="#openings" class="xref">Openings</a>' in html


def test_link_with_its_own_text_keeps_it_and_is_still_a_reference(
  pandoc: Pandoc,
) -> None:
  html = pandoc.output(
    '# Stayman {#stayman}\n\n[the relay](#stayman)', 'headings.lua'
  )
  assert '<a href="#stayman" class="xref">the relay</a>' in html


@pytest.mark.parametrize('link', ['[](#missing)', '[see](#missing)'])
def test_unknown_target_fails_the_render(pandoc: Pandoc, link: str) -> None:
  error = pandoc.error(f'# A {{#a}}\n\n{link}', 'headings.lua')
  assert 'unknown cross-reference target: #missing' in error


@pytest.mark.parametrize(
  'document', ['## B {#b}\n\n# A {#a}', '# A {#a}\n\n### C {#c}']
)
def test_skipped_heading_level_fails_the_render(
  pandoc: Pandoc, document: str
) -> None:
  assert 'levels must not skip' in pandoc.error(document, 'headings.lua')


def test_copied_titles_drop_links_and_footnotes(pandoc: Pandoc) -> None:
  document = '# A [B](#b)^[note] {#a}\n\n# B {#b}\n\n[](#a)'
  html = pandoc.output(document, 'headings.lua')
  assert '<a href="#a" class="xref">A B</a>' in html
  assert html.count('class="footnote-ref"') == 1


def test_text_before_the_first_top_level_heading_fails(pandoc: Pandoc) -> None:
  error = pandoc.error('Preamble.\n\n# A {#a}', 'headings.lua')
  assert 'before the first top-level heading' in error


def test_a_comment_may_stand_before_the_first_top_level_heading(
  pandoc: Pandoc,
) -> None:
  html = pandoc.output('<!-- maintainer notes -->\n\n# A {#a}', 'headings.lua')
  assert '<!-- maintainer notes -->' in html
  assert '<h1 id="a">A</h1>' in html


# --- nowrap ---


# The first token's range is spelled with an en dash (U+2013), which nowrap.lua
# matches with a pattern of its own. The escape keeps it from reading as the
# plain hyphen in the token beside it.
@pytest.mark.parametrize(
  'token', ['15\N{EN DASH}17', '5-3-3-2', 'P/C', 'NS/JNS']
)
def test_notation_token_is_wrapped(pandoc: Pandoc, token: str) -> None:
  html = pandoc.output(token, 'nowrap.lua')
  assert f'<span class="nowrap">{token}</span>' in html


@pytest.mark.parametrize(
  'word', ['four-card', 'lead-directing', 'and/or', 'opener/responder', 'plain']
)
def test_prose_is_left_breakable(pandoc: Pandoc, word: str) -> None:
  assert 'nowrap' not in pandoc.output(word, 'nowrap.lua')


# --- shorthand ---


@pytest.mark.parametrize(
  'token', ['M', 'OM', '2M', 'W2M', 'Q3M', '4cM', '4+OM']
)
def test_major_placeholder_is_bolded(pandoc: Pandoc, token: str) -> None:
  html = pandoc.output(token, 'shorthand.lua')
  assert f'{token[:-1]}<strong>M</strong>' in html


@pytest.mark.parametrize(
  'token', ['Major', 'IMP', 'm', 'Om', 'system', 'BAM', 'PROGRAM']
)
def test_other_tokens_are_untouched(pandoc: Pandoc, token: str) -> None:
  assert '<strong>' not in pandoc.output(token, 'shorthand.lua')


def test_each_token_in_a_run_is_judged_alone(pandoc: Pandoc) -> None:
  html = pandoc.output('Q3M/Q4M=cue', 'shorthand.lua')
  assert 'Q3<strong>M</strong>/Q4<strong>M</strong>=cue' in html


def test_plain_text_keeps_shorthand_as_typed(pandoc: Pandoc) -> None:
  text = pandoc.output('OM and 4cM', 'shorthand.lua', to='plain')
  assert text.strip() == 'OM and 4cM'


# --- callouts ---


def test_italic_item_becomes_a_callout_inside_the_item_above_it(
  pandoc: Pandoc,
) -> None:
  html = pandoc.output(
    """
    - 3S=relay
      - _Note: always 3S_
    """,
    'callouts.lua',
  )
  assert html == (
    '<ul>\n'
    '<li>3S=relay\n'
    '<div class="callout">\n'
    '<em>Note: always 3S</em>\n'
    '</div></li>\n'
    '</ul>\n'
  )


def test_plain_text_gives_a_callout_no_marker(pandoc: Pandoc) -> None:
  text = pandoc.output(
    """
    - 3S=relay
      - _Note: always 3S_
    """,
    'callouts.lua',
    to='plain',
  )
  assert text.splitlines() == [
    '- 3S=relay',
    '  Note: always 3S',
  ]


@pytest.mark.parametrize(
  'markdown',
  [
    # Opens on an italic term, as a definition does.
    '- _Fast denies_: a direct 3NT denies a stopper\n',
    '- 3S=_relay_\n',
    # Holds a list of its own beside its paragraph.
    """
    - _Note: see below_
      - 3S=relay
    """,
  ],
)
def test_item_not_wholly_one_italic_paragraph_stays_a_list_item(
  pandoc: Pandoc, markdown: str
) -> None:
  assert 'callout' not in pandoc.output(markdown, 'callouts.lua')


@pytest.mark.parametrize(
  'markdown',
  [
    """
    - 3D=transfer
      - _Note: first_
      - 3S=min
    """,
    """
    - 3D=transfer
      - 3S=min
      - _Note: between_
      - 3NT=max
    """,
    """
    - 3D=transfer
      - 3S=min
      - _Note: last_
    """,
    """
    - 3D=transfer
      - _Note: one_
      - _Note: two_
    """,
  ],
  ids=['first', 'between', 'last', 'beside another callout'],
)
def test_callout_beside_other_items_fails_the_render(
  pandoc: Pandoc, markdown: str
) -> None:
  error = pandoc.error(markdown, 'callouts.lua')
  assert 'shares its list with other items' in error


def test_callout_nested_under_no_item_fails_the_render(pandoc: Pandoc) -> None:
  error = pandoc.error('- _Note: stray_\n', 'callouts.lua')
  assert 'is nested under no item' in error
