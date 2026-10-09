# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Utility to render an input file's Markdown text as HTML for an Anki card.

The rules are in `anki/spec.md` #text-formatting: CommonMark, with single line
breaks kept and custom styling for callouts.
"""

import functools

from markdown_it import MarkdownIt
from markdown_it.renderer import RendererHTML
from markdown_it.rules_core import StateCore
from markdown_it.token import Token

# A paragraph opening with one of these labels is a callout, shown in italics
# with the label also in bold.
_CALLOUT_LABELS = ('Note:', 'Tip:')


def render_markdown(text: str) -> str:
  """The HTML for `text`, or an empty string when `text` is empty."""
  parser = _parser()
  # Note: `MarkdownIt.render` would parse and render in one call, but it returns
  # `Any`, since its renderer is pluggable; calling the HTML renderer directly
  # keeps the result typed. `env` carries everything parsing collects, such as
  # link reference definitions, through to rendering.
  env: dict[str, object] = {}
  tokens = parser.parse(text, env)
  return _html_renderer().render(tokens, parser.options, env)


# Building the parser and the renderer costs a few times what rendering one cell
# does, so each is built on first use and shared after that.


@functools.cache
def _parser() -> MarkdownIt:
  """The Markdown parser for card text."""
  parser = MarkdownIt(
    'commonmark',
    {
      # Render a single line break as `<br />`; plain CommonMark would show it
      # as a space.
      'breaks': True,
      # Show HTML typed into a cell as text, per `anki/spec.md`
      # #text-formatting.
      'html': False,
    },
  )
  # `push` adds the rule at the end of the core chain, after every built-in
  # rule, so the callout check sees each paragraph's text in its final form.
  parser.core.ruler.push('style_callouts', _style_callouts)
  return parser


@functools.cache
def _html_renderer() -> RendererHTML:
  """The renderer that turns the parser's tokens into HTML."""
  return RendererHTML()


def _style_callouts(state: StateCore) -> None:
  """Italicize each callout paragraph, bolding the label."""
  for position, token in enumerate(state.tokens):
    # A paragraph's text sits in the inline token right after its
    # `paragraph_open` token.
    if token.type != 'paragraph_open':
      continue
    inline = state.tokens[position + 1]
    children = inline.children
    if not children or children[0].type != 'text':
      continue
    opening_text = children[0].content
    label = next(
      (
        candidate
        for candidate in _CALLOUT_LABELS
        if opening_text.startswith(candidate)
      ),
      None,
    )
    if not label:
      continue

    children[0].content = opening_text.removeprefix(label)
    inline.children = [
      Token(type='em_open', tag='em', nesting=1),
      Token(type='strong_open', tag='strong', nesting=1),
      Token(type='text', tag='', nesting=0, content=label),
      Token(type='strong_close', tag='strong', nesting=-1),
      *children,
      Token(type='em_close', tag='em', nesting=-1),
    ]
