# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for rendering an input file's Markdown text as card HTML."""

import textwrap

from markdown_rendering import render_markdown

# --- Markdown ---


def test_text_becomes_a_paragraph() -> None:
  assert render_markdown('Low to the Q') == '<p>Low to the Q</p>\n'


def test_blank_text_renders_empty() -> None:
  assert render_markdown('') == ''


def test_single_line_break_stays_a_line_break() -> None:
  markdown = textwrap.dedent("""\
    Low to the K
    then low to the Q
  """)

  expected_html = textwrap.dedent("""\
    <p>Low to the K<br />
    then low to the Q</p>
  """)

  assert render_markdown(markdown) == expected_html


def test_list_can_follow_a_line_of_text_directly() -> None:
  markdown = textwrap.dedent("""\
    Either:
    * Cash the A
    * Cash the K
  """)

  expected_html = textwrap.dedent("""\
    <p>Either:</p>
    <ul>
    <li>Cash the A</li>
    <li>Cash the K</li>
    </ul>
  """)

  assert render_markdown(markdown) == expected_html


def test_html_shows_as_typed() -> None:
  # Escaped, so the card shows the characters rather than reading them as
  # markup.
  assert render_markdown('<b>KQ</b> onside') == (
    '<p>&lt;b&gt;KQ&lt;/b&gt; onside</p>\n'
  )


# --- callouts ---


def test_callout_is_italic_with_a_bold_label() -> None:
  assert render_markdown('Tip: Count the cases') == (
    '<p><em><strong>Tip:</strong> Count the cases</em></p>\n'
  )


def test_callout_italicizes_its_whole_paragraph() -> None:
  markdown = textwrap.dedent("""\
    Note: Lead *low*
    then finesse

    The next paragraph is plain
  """)

  expected_html = textwrap.dedent("""\
    <p><em><strong>Note:</strong> Lead <em>low</em><br />
    then finesse</em></p>
    <p>The next paragraph is plain</p>
  """)

  assert render_markdown(markdown) == expected_html


def test_label_word_without_its_colon_makes_no_callout() -> None:
  assert render_markdown('Note that the 9 matters') == (
    '<p>Note that the 9 matters</p>\n'
  )


def test_label_past_the_paragraph_start_makes_no_callout() -> None:
  assert render_markdown('See Tip: below') == '<p>See Tip: below</p>\n'


def test_unknown_label_makes_no_callout() -> None:
  assert render_markdown('Hint: Count') == '<p>Hint: Count</p>\n'
