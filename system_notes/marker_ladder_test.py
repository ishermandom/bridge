# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""The marker ladder read from small stylesheets written in place."""

import pytest

from system_notes import marker_ladder
from system_notes.marker_ladder import MarkerStyle


def test_a_depth_without_a_size_or_offsets_takes_the_defaults() -> None:
  stylesheet = """
ul > li::before {
  font-family: "Source Sans 3";
  content: "○";
}
"""

  styles = marker_ladder.marker_styles(stylesheet)

  # The body's own size, and the glyph where its font draws it.
  assert styles == {
    '○': MarkerStyle(
      font_family='Source Sans 3', font_size=1, left=0, vertical_align=0
    )
  }


def test_a_depth_keeps_what_its_rule_does_not_restate() -> None:
  stylesheet = """
ul > li::before {
  font-family: "Source Sans 3";
  content: "○";
}
ul ul > li::before {
  font-size: 1.1em;
  left: 0.004em;
  vertical-align: -0.045em;
  content: "▷";
}
ul ul ul > li::before {
  left: 0.017em;
  content: "▶";
}
"""

  styles = marker_ladder.marker_styles(stylesheet)

  # ▶ restates only its offset across: its family comes from the first depth,
  # its size and offset up from the second.
  assert styles['▶'] == MarkerStyle(
    font_family='Source Sans 3',
    font_size=1.1,
    left=0.017,
    vertical_align=-0.045,
  )


def test_the_ladder_runs_outermost_depth_first() -> None:
  stylesheet = """
ul > li::before {
  font-family: "Source Sans 3";
  content: "○";
}
ul ul > li::before {
  content: "●";
}
ul ul ul > li::before {
  content: "□";
}
"""

  styles = marker_ladder.marker_styles(stylesheet)

  assert list(styles) == ['○', '●', '□']


def test_a_declaration_inside_a_comment_is_ignored() -> None:
  stylesheet = """
ul > li::before {
  font-family: "Source Sans 3";
  /* left: 0.5em; */
  content: "○";
}
"""

  styles = marker_ladder.marker_styles(stylesheet)

  assert styles['○'].left == 0


def test_other_rules_are_ignored() -> None:
  stylesheet = """
ul {
  font-size: 2em;
}
ul > li::before {
  font-family: "Source Sans 3";
  content: "○";
}
ol > li::before {
  left: 0.5em;
}
"""

  styles = marker_ladder.marker_styles(stylesheet)

  assert styles['○'] == MarkerStyle(
    font_family='Source Sans 3', font_size=1, left=0, vertical_align=0
  )


def test_a_rule_out_of_depth_order_is_rejected() -> None:
  stylesheet = """
ul > li::before {
  font-family: "Source Sans 3";
  content: "○";
}
ul ul ul > li::before {
  content: "□";
}
"""

  with pytest.raises(ValueError, match='depth-3'):
    marker_ladder.marker_styles(stylesheet)


def test_a_marker_repeated_at_a_second_depth_is_rejected() -> None:
  stylesheet = """
ul > li::before {
  font-family: "Source Sans 3";
  content: "○";
}
ul ul > li::before {
  font-size: 1.1em;
}
"""

  with pytest.raises(ValueError, match='repeats'):
    marker_ladder.marker_styles(stylesheet)


def test_a_length_outside_em_is_rejected() -> None:
  stylesheet = """
ul > li::before {
  font-family: "Source Sans 3";
  left: 1px;
  content: "○";
}
"""

  with pytest.raises(ValueError, match="'1px'"):
    marker_ladder.marker_styles(stylesheet)
