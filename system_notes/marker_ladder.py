# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Read the list-marker ladder as the stylesheet declares it.

`notes.css` gives each list depth its marker through a rule that nests one more
`ul` per depth, and each rule restates only what changes from the depth above. A
rule's selector matches its own depth and every depth below, and outranks the
rules above it, so each depth takes every property from the deepest rule at or
above it that sets one. Reading the ladder replays that cascade over the rules
tinycss2, the CSS parser WeasyPrint itself uses, finds in the stylesheet.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import tinycss2
from tinycss2.ast import (
  Declaration,
  DimensionToken,
  Node,
  ParseError,
  QualifiedRule,
  StringToken,
)


@dataclass(frozen=True)
class MarkerStyle:
  """A list marker's font and placement at one depth.

  `font_size` is in the body's em; `left` and `vertical_align` are in the
  marker's own em, as CSS measures them.
  """

  font_family: str
  font_size: float
  left: float
  vertical_align: float


def marker_styles(stylesheet: str) -> Mapping[str, MarkerStyle]:
  """Each depth's list marker, by its character, outermost depth first."""
  values: dict[str, Sequence[Node]] = {}
  styles: dict[str, MarkerStyle] = {}
  # Parsing from a string drops every comment.
  for rule in tinycss2.parse_stylesheet(
    stylesheet, skip_comments=True, skip_whitespace=True
  ):
    if isinstance(rule, ParseError):
      raise ValueError(f'the stylesheet does not parse: {rule.message}')
    if not isinstance(rule, QualifiedRule):
      # At-rules such as @media hold no marker rules.
      continue
    depth = _marker_depth(tinycss2.serialize(rule.prelude))
    if not depth:
      continue
    if depth != len(styles) + 1:
      raise ValueError(
        f'a depth-{depth} marker rule follows the depth-{len(styles)} rule'
      )

    for item in tinycss2.parse_blocks_contents(
      rule.content, skip_comments=True, skip_whitespace=True
    ):
      if isinstance(item, ParseError):
        raise ValueError(
          f'the depth-{depth} marker rule does not parse: {item.message}'
        )
      if isinstance(item, Declaration):
        values[item.lower_name] = item.value

    character = _string(values, 'content')
    if character in styles:
      raise ValueError(f'depth {depth} repeats the marker {character}')
    styles[character] = MarkerStyle(
      font_family=_string(values, 'font-family'),
      # No size set means the body's own; no offset set leaves the glyph where
      # its font draws it.
      font_size=_em_length(values, 'font-size', default=1),
      left=_em_length(values, 'left', default=0),
      vertical_align=_em_length(values, 'vertical-align', default=0),
    )
  return styles


def _marker_depth(selector: str) -> int | None:
  """The list depth a marker rule's selector styles, or None for other rules.

  A marker rule's selector reads `ul > li::before`, with one more `ul` for each
  depth past the first.
  """
  words = selector.split()
  ancestors = words[:-2]
  if (
    words[-2:] != ['>', 'li::before']
    or not ancestors
    or any(word != 'ul' for word in ancestors)
  ):
    return None
  return len(ancestors)


def _string(values: Mapping[str, Sequence[Node]], property_name: str) -> str:
  """A property's quoted string value, such as a marker or a font family."""
  token = _only_token(values, property_name)
  if not isinstance(token, StringToken):
    raise ValueError(
      f'expected a quoted string for {property_name}, got '
      f'{tinycss2.serialize([token])!r}'
    )
  return token.value


def _em_length(
  values: Mapping[str, Sequence[Node]], property_name: str, default: float
) -> float:
  """A property's length in em, as a number, or `default` when it is unset."""
  if property_name not in values:
    return default
  token = _only_token(values, property_name)
  if not isinstance(token, DimensionToken) or token.lower_unit != 'em':
    raise ValueError(
      f'expected a length in em for {property_name}, got '
      f'{tinycss2.serialize([token])!r}'
    )
  return float(token.value)


def _only_token(
  values: Mapping[str, Sequence[Node]], property_name: str
) -> Node:
  """The single token a property's value holds, apart from whitespace."""
  if property_name not in values:
    raise ValueError(f'no marker rule sets {property_name}')
  tokens = [
    token for token in values[property_name] if token.type != 'whitespace'
  ]
  if len(tokens) != 1:
    raise ValueError(
      f'expected one value for {property_name}, got '
      f'{tinycss2.serialize(values[property_name])!r}'
    )
  return tokens[0]
