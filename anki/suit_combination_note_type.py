# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""The `Suit combination` note type: its fields, card template, and styling.

The card's layout is specified in `anki/spec.md` #suit-combination-card.

Anki matches a re-imported note type to the collection's copy by its:
 * ID
 * field names
 * field order
 * template name

Changing any of these here alone imports a second copy instead. The ID never
changes. A field must be renamed or moved in Anki first, then here, as
documented in `flashcards/spec.md` #note-type-evolution.

The template's markup and the styling are free to change.
"""

import enum

import genanki

# Drawn at random once, from the range genanki's README suggests:
# https://github.com/kerrickstaley/genanki#models
_NOTE_TYPE_ID = 1191707489


class Field(enum.StrEnum):
  """A field of the note type.

  Each member's value is the field's name, and the members are declared in the
  note type's field order.
  """

  # Both holdings and the target on one line, for Anki's card browser to sort
  # and search by; the card itself doesn't show it.
  SUIT_COMBINATION = 'Suit combination'
  NORTH_HOLDING = 'North holding'
  SOUTH_HOLDING = 'South holding'
  TRICKS_TARGET = 'Target # of tricks'
  # The constraints the best line assumes, such as limited entries, written as
  # sentences; empty when the row assumes the defaults. Every kind of constraint
  # shares this one field, so adding a kind never changes the note type.
  CONSTRAINTS = 'Constraints'
  SUCCESS_PERCENT = 'Success %'
  BEST_LINE = 'Best line'
  REMARKS = 'Remarks'
  SOURCE = 'Source'


# A question naming the target, then the combination on a line of its own,
# North's holding first, then any constraints. The target also fills the
# `data-tricks` attribute, which the styling reads to pick "trick" or "tricks".
_FRONT = """\
<p class="question">
  How would you play this suit combination for
  <span class="tricks" data-tricks="{{Target # of tricks}}">{{Target # of tricks}}</span>?
</p>
<p class="combination">{{North holding}} &ndash; {{South holding}}</p>
{{#Constraints}}<p class="constraints">{{Constraints}}</p>{{/Constraints}}
"""

# The front again, then the best line with its chance of success, the remarks,
# and the source. A blank Remarks or Source leaves out its whole section.
_BACK = """\
{{FrontSide}}
<hr id="answer">
<div class="solution">
  <div class="best-line">
    <div class="line">{{Best line}}</div>
    <div class="success">{{Success %}}%</div>
  </div>
  {{#Remarks}}<div class="remarks">{{Remarks}}</div>{{/Remarks}}
  {{#Source}}<p class="source">Source: {{Source}}</p>{{/Source}}
</div>
"""

_STYLE = """\
/* Anki's stock size and alignment, in each platform's own interface font. No
   colors are set, so the card follows Anki's light and dark themes alike. */
.card {
  font-family: system-ui, sans-serif;
  font-size: 20px;
  line-height: 1.5;
  text-align: center;
}

.combination {
  font-size: 1.6em;
  font-weight: bold;
}

/* Underlined, so the target stands out when scanning the card, and kept on one
   line, so a line never breaks between the count and its noun. */
.tricks {
  text-decoration: underline;
  white-space: nowrap;
}

/* Templates can't branch on a field's value, so the noun comes from here. */
.tricks::after {
  content: ' tricks';
}

.tricks[data-tricks='1']::after {
  content: ' trick';
}

/* Left-aligned text in a centered column: centered lists and paragraphs are
   hard to follow. */
.solution {
  max-width: 32em;
  margin: 0 auto;
  text-align: left;
}

.solution p,
.solution ul {
  margin: 0.5em 0;
}

.solution ul {
  padding-left: 1.5em;
}

.best-line {
  display: flex;
  gap: 1em;
  align-items: baseline;
}

.best-line .line {
  flex: 1;
}

.success {
  font-weight: bold;
  white-space: nowrap;
}

.remarks {
  margin-top: 1em;
}

/* Faded by opacity rather than a gray, which would clash with one theme. */
.source {
  margin-top: 1.5em;
  font-size: 0.85em;
  opacity: 0.6;
}
"""


def make_note_type() -> genanki.Model:
  """The note type, ready to hold notes in a package."""
  return genanki.Model(
    model_id=_NOTE_TYPE_ID,
    name='Suit combination',
    fields=[{'name': field.value} for field in Field],
    templates=[{'name': 'Suit combination', 'qfmt': _FRONT, 'afmt': _BACK}],
    css=_STYLE,
  )
